"""
Go AST schema inferrer.

Parses Go struct definitions by scanning .go files with regex-based heuristics
augmented by struct tag parsing (json:"...", validate:"...").

Maps Go types to JSON Schema:
  string         → {type: string}
  int / int64    → {type: integer}
  float64        → {type: number}
  bool           → {type: boolean}
  []T            → {type: array, items: <T schema>}
  *T             → nullable T schema
  time.Time      → {type: string, format: date-time}

Struct tags parsed:
  json:"name,omitempty"    → field name + optional
  validate:"required"      → required field
  validate:"min=1,max=100" → minimum / maximum
"""

import json
import logging
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from spec_engine.models import SchemaResult, Confidence
from spec_engine.inferrer.base import BaseInferrer
from spec_engine.config import Config

log = logging.getLogger(__name__)

_GO_SOURCE = Path(__file__).parent / "go_schema.go"

# Go type → JSON Schema
_GO_TYPE_MAP: Dict[str, dict] = {
    "string": {"type": "string"},
    "bool": {"type": "boolean"},
    "int": {"type": "integer"},
    "int8": {"type": "integer"},
    "int16": {"type": "integer"},
    "int32": {"type": "integer"},
    "int64": {"type": "integer", "format": "int64"},
    "uint": {"type": "integer"},
    "uint8": {"type": "integer"},
    "uint16": {"type": "integer"},
    "uint32": {"type": "integer"},
    "uint64": {"type": "integer"},
    "float32": {"type": "number", "format": "float"},
    "float64": {"type": "number", "format": "double"},
    "byte": {"type": "integer"},
    "rune": {"type": "integer"},
    "Time": {"type": "string", "format": "date-time"},
}

# Regex patterns for Go struct parsing
_STRUCT_RE = re.compile(r"type\s+(\w+)\s+struct\s*\{([^}]*)\}", re.DOTALL)
_FIELD_RE = re.compile(r"^\s+(\w+)\s+(\*?)(\[\])?(\w+(?:\.\w+)?)\s*(?:`([^`]+)`)?\s*$", re.MULTILINE)
_JSON_TAG_RE = re.compile(r'json:"([^"]*)"')
_VALIDATE_TAG_RE = re.compile(r'validate:"([^"]*)"')


class GoASTInferrer(BaseInferrer):
    """Infer JSON Schema from Go structs using go/ast subprocess or regex fallback."""

    def __init__(self, repo_path: str, config: Config) -> None:
        super().__init__(repo_path, config)
        self._ast_binary: Optional[Path] = self._compile_ast_tool()

    def _compile_ast_tool(self) -> Optional[Path]:
        """Compile go_schema.go to a temporary binary. Returns None if Go unavailable."""
        if not _GO_SOURCE.exists():
            return None
        try:
            with tempfile.NamedTemporaryFile(suffix="", delete=False, prefix="go_schema_tool_") as f:
                binary_path = Path(f.name)
            result = subprocess.run(
                ["go", "build", "-o", str(binary_path), str(_GO_SOURCE)],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                binary_path.unlink(missing_ok=True)
                return None
            return binary_path
        except (FileNotFoundError, subprocess.TimeoutExpired, Exception):
            return None

    def _find_type_file(self, type_name: str) -> Optional[Path]:
        """Find a .go file that defines the given struct."""
        search_str = f"type {type_name} struct"
        candidates: List[Path] = []
        for go_file in self.repo_path.rglob("*.go"):
            try:
                text = go_file.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if search_str in text:
                candidates.append(go_file)
        if not candidates:
            return None
        model_first = sorted(candidates, key=lambda c: 0 if "model" in str(c).lower() else 1)
        ranked = self._rank_candidates(model_first)
        return ranked[0] if ranked else None

    def _extract_fields(
        self, type_name: str, source_file: Path, visited: Set[str]
    ) -> SchemaResult:
        """Extract JSON Schema from a Go struct via subprocess or regex."""
        try:
            rel_path = str(source_file.relative_to(self.repo_path))
        except ValueError:
            rel_path = str(source_file)

        if self._ast_binary is not None:
            result = self._extract_with_binary(type_name, source_file, rel_path, visited)
            if result is not None:
                return result

        return self._extract_with_regex(type_name, source_file, rel_path, visited)

    def _extract_with_binary(
        self, type_name: str, source_file: Path, rel_path: str, visited: Set[str]
    ) -> Optional[SchemaResult]:
        """Use the compiled Go binary to extract the schema."""
        if self._ast_binary is None:
            return None
        try:
            result = subprocess.run(
                [str(self._ast_binary), str(source_file), type_name],
                capture_output=True,
                text=True,
                timeout=15,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return None

        stdout = (result.stdout or "").strip()
        if not stdout:
            return None

        try:
            schema_dict = json.loads(stdout)
        except json.JSONDecodeError:
            return None

        if not schema_dict or not isinstance(schema_dict, dict) or "properties" not in schema_dict:
            return None

        return SchemaResult(
            type_name=type_name,
            json_schema=schema_dict,
            confidence=Confidence.HIGH,
            source_file=rel_path,
        )

    def _extract_with_regex(
        self, type_name: str, source_file: Path, rel_path: str, visited: Set[str]
    ) -> SchemaResult:
        """Regex-based Go struct parsing fallback."""
        source = source_file.read_text(encoding="utf-8", errors="ignore")

        # Find the struct definition
        struct_match = None
        for m in _STRUCT_RE.finditer(source):
            if m.group(1) == type_name:
                struct_match = m
                break

        if not struct_match:
            return SchemaResult.empty(type_name, rel_path)

        struct_body = struct_match.group(2)
        properties: Dict[str, Any] = {}
        required: List[str] = []

        for line in struct_body.splitlines():
            line = line.strip()
            if not line or line.startswith("//"):
                continue

            field_m = re.match(
                r"^(\w+)\s+(\*?)(\[\])?(\w+(?:\.\w+)?)\s*(?:`([^`]+)`)?\s*$",
                line
            )
            if not field_m:
                continue

            field_go_name = field_m.group(1)
            is_pointer = bool(field_m.group(2))
            is_slice = bool(field_m.group(3))
            type_name_raw = field_m.group(4)
            tag_raw = field_m.group(5) or ""

            # Skip unexported
            if not field_go_name[0].isupper():
                continue

            # Parse json tag
            json_name = field_go_name[0].lower() + field_go_name[1:]  # default camelCase
            omitempty = False
            json_m = _JSON_TAG_RE.search(tag_raw)
            if json_m:
                parts = json_m.group(1).split(",")
                if parts[0] and parts[0] != "-":
                    json_name = parts[0]
                if len(parts) > 1 and "omitempty" in parts[1:]:
                    omitempty = True
                if parts[0] == "-":
                    continue  # json:"-" → skip

            # Parse validate tag
            is_required = False
            min_val = None
            max_val = None
            val_m = _VALIDATE_TAG_RE.search(tag_raw)
            if val_m:
                for rule in val_m.group(1).split(","):
                    rule = rule.strip()
                    if rule == "required":
                        is_required = True
                    elif rule.startswith("min="):
                        try:
                            min_val = float(rule[4:])
                        except ValueError:
                            pass
                    elif rule.startswith("max="):
                        try:
                            max_val = float(rule[4:])
                        except ValueError:
                            pass

            # Build schema
            base_type = type_name_raw.split(".")[-1]  # time.Time → Time
            base_schema = _GO_TYPE_MAP.get(base_type) or _GO_TYPE_MAP.get(type_name_raw)
            if base_schema is None:
                # Complex type — use $ref
                base_schema = {"$ref": f"#/components/schemas/{base_type}"}

            if is_slice:
                schema: Dict[str, Any] = {"type": "array", "items": dict(base_schema)}
            else:
                schema = dict(base_schema)

            if is_pointer or omitempty:
                schema["nullable"] = True
            if min_val is not None:
                schema["minimum"] = min_val
            if max_val is not None:
                schema["maximum"] = max_val

            properties[json_name] = schema

            if is_required and not is_pointer and not omitempty:
                required.append(json_name)

        if not properties:
            return SchemaResult.empty(type_name, rel_path)

        json_schema: Dict[str, Any] = {"type": "object", "properties": properties}
        if required:
            json_schema["required"] = required

        return SchemaResult(
            type_name=type_name,
            json_schema=json_schema,
            confidence=Confidence.HIGH,
            source_file=rel_path,
        )
