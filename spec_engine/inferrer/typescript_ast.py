"""
TypeScript AST schema inferrer.

Parses TypeScript interfaces and classes via a Node.js helper script that uses
ts-morph for full type resolution. Invokes the helper as a subprocess and
parses the resulting JSON Schema.

Maps TypeScript types to JSON Schema:
  string         → {type: string}
  number         → {type: number}
  boolean        → {type: boolean}
  T[]            → {type: array, items: <T schema>}
  string | null  → nullable string
  Date           → {type: string, format: date-time}
  Record<K, V>   → {type: object, additionalProperties: <V schema>}
"""

import json
import logging
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Set

from spec_engine.models import SchemaResult, Confidence
from spec_engine.inferrer.base import BaseInferrer
from spec_engine.config import Config

log = logging.getLogger(__name__)

_SCRIPT_PATH = Path(__file__).parent / "ts_schema.js"


class TypeScriptASTInferrer(BaseInferrer):
    """Infer JSON Schema from TypeScript files using the ts-morph Node.js helper."""

    def _find_type_file(self, type_name: str) -> Optional[Path]:
        """Find a .ts or .d.ts file that defines the given interface/class."""
        search_str = f"interface {type_name}"
        class_str = f"class {type_name}"
        type_str = f"type {type_name} ="

        candidates: List[Path] = []
        for ts_file in self.repo_path.rglob("*.ts"):
            if ts_file.name.endswith(".d.ts") and "node_modules" in str(ts_file):
                continue
            try:
                text = ts_file.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if search_str in text or class_str in text or type_str in text:
                candidates.append(ts_file)

        if not candidates:
            return None
        model_first = sorted(
            candidates,
            key=lambda c: 0 if ("model" in str(c).lower() or "dto" in str(c).lower()) else 1,
        )
        ranked = self._rank_candidates(model_first)
        return ranked[0] if ranked else None

    def _extract_fields(
        self, type_name: str, source_file: Path, visited: Set[str]
    ) -> SchemaResult:
        """Run the ts-morph helper and parse the resulting JSON Schema."""
        try:
            rel_path = str(source_file.relative_to(self.repo_path))
        except ValueError:
            rel_path = str(source_file)

        if not _SCRIPT_PATH.exists():
            return SchemaResult.empty(type_name, rel_path)

        try:
            result = subprocess.run(
                ["node", str(_SCRIPT_PATH), str(source_file), type_name],
                capture_output=True,
                text=True,
                timeout=30,
            )
        except FileNotFoundError:
            log.debug("TypeScriptASTInferrer: node not found")
            return SchemaResult.empty(type_name, rel_path)
        except subprocess.TimeoutExpired:
            log.debug("TypeScriptASTInferrer: timeout for %s", source_file)
            return SchemaResult.empty(type_name, rel_path)

        stdout = (result.stdout or "").strip()
        if not stdout:
            return SchemaResult.empty(type_name, rel_path)

        try:
            schema_dict = json.loads(stdout)
        except json.JSONDecodeError as e:
            log.debug("TypeScriptASTInferrer: JSON parse error: %s", e)
            return SchemaResult.empty(type_name, rel_path)

        if not schema_dict or not isinstance(schema_dict, dict):
            return SchemaResult.empty(type_name, rel_path)

        if "properties" not in schema_dict:
            return SchemaResult.empty(type_name, rel_path)

        confidence = Confidence.HIGH if schema_dict.get("properties") else Confidence.MEDIUM
        return SchemaResult(
            type_name=type_name,
            json_schema=schema_dict,
            confidence=confidence,
            source_file=rel_path,
        )
