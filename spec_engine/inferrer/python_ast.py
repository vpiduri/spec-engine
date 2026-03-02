"""
Python AST schema inferrer.

Parses Pydantic v2 models using Python's built-in ast module. Extracts field
definitions, type annotations, Field() constraints, and model_config settings.

Maps Pydantic types to JSON Schema:
  str            → {type: string}
  int            → {type: integer}
  float          → {type: number}
  bool           → {type: boolean}
  List[T]        → {type: array, items: <T schema>}
  Optional[T]    → nullable variant of T schema
  datetime       → {type: string, format: date-time}
  UUID           → {type: string, format: uuid}
"""

import ast
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from spec_engine.models import SchemaResult, Confidence
from spec_engine.inferrer.base import BaseInferrer, _PRIMITIVE_MAP
from spec_engine.config import Config

log = logging.getLogger(__name__)

_MODEL_BASES = {"BaseModel", "Schema", "SQLModel", "BaseSettings"}

# Python type → JSON Schema (for direct field types)
_PY_TYPE_MAP: Dict[str, dict] = {
    "str": {"type": "string"},
    "int": {"type": "integer"},
    "float": {"type": "number"},
    "bool": {"type": "boolean"},
    "bytes": {"type": "string", "format": "binary"},
    "datetime": {"type": "string", "format": "date-time"},
    "date": {"type": "string", "format": "date"},
    "time": {"type": "string", "format": "time"},
    "UUID": {"type": "string", "format": "uuid"},
    "Decimal": {"type": "number"},
    "Any": {},
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ast_str(node: ast.expr) -> Optional[str]:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _ast_num(node: ast.expr) -> Optional[Any]:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        if isinstance(node.operand, ast.Constant) and isinstance(node.operand.value, (int, float)):
            return -node.operand.value
    return None


# ---------------------------------------------------------------------------
# PythonASTInferrer
# ---------------------------------------------------------------------------

class PythonASTInferrer(BaseInferrer):
    """Infer JSON Schema from Pydantic models using Python's ast module."""

    def _find_type_file(self, type_name: str) -> Optional[Path]:
        """
        Find the .py file defining `class {type_name}(...)`.
        Quick string scan before full parse. Prefers "model" in path.
        """
        search_str = f"class {type_name}("
        candidates: List[Path] = []
        for py_file in self.repo_path.rglob("*.py"):
            try:
                text = py_file.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if search_str in text:
                candidates.append(py_file)
        if not candidates:
            return None
        model_first = sorted(candidates, key=lambda c: 0 if "model" in str(c).lower() else 1)
        ranked = self._rank_candidates(model_first)
        return ranked[0] if ranked else None

    def _extract_fields(
        self, type_name: str, source_file: Path, visited: Set[str]
    ) -> SchemaResult:
        """Parse the Python file and extract the Pydantic model schema."""
        source = source_file.read_text(encoding="utf-8", errors="ignore")
        try:
            tree = ast.parse(source, filename=str(source_file))
        except SyntaxError as e:
            log.debug("PythonASTInferrer: parse error in %s: %s", source_file, e)
            return SchemaResult.empty(type_name, str(source_file))

        try:
            rel_path = str(source_file.relative_to(self.repo_path))
        except ValueError:
            rel_path = str(source_file)

        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef) or node.name != type_name:
                continue
            if not self._is_model_class(node):
                continue
            return self._extract_class_schema(node, type_name, rel_path, visited)

        return SchemaResult.empty(type_name, rel_path)

    def _is_model_class(self, node: ast.ClassDef) -> bool:
        """Return True if class inherits from a known model base."""
        for base in node.bases:
            name = None
            if isinstance(base, ast.Name):
                name = base.id
            elif isinstance(base, ast.Attribute):
                name = base.attr
            if name in _MODEL_BASES:
                return True
        return False

    def _extract_class_schema(
        self,
        node: ast.ClassDef,
        type_name: str,
        rel_path: str,
        visited: Set[str],
    ) -> SchemaResult:
        """Build JSON Schema from a Pydantic class definition."""
        properties: Dict[str, Any] = {}
        required: List[str] = []
        refs: List[str] = []
        all_high = True

        for stmt in node.body:
            if not isinstance(stmt, ast.AnnAssign):
                continue
            if not isinstance(stmt.target, ast.Name):
                continue
            field_name = stmt.target.id
            if field_name.startswith("_"):
                continue

            annotation = stmt.annotation
            default = stmt.value

            is_optional, base_type_name = self._parse_annotation(annotation)
            constraints = self._extract_field_constraints(default)
            field_schema, field_confidence = self._build_field_schema(
                base_type_name, visited
            )

            if field_confidence != Confidence.HIGH:
                all_high = False

            merged = {**field_schema}
            if is_optional:
                merged["nullable"] = True
            merged.update(constraints)
            properties[field_name] = merged

            # Determine required
            is_required = not is_optional and not self._has_default(default)
            if is_required:
                required.append(field_name)

            # Track refs to nested types
            if base_type_name and _PY_TYPE_MAP.get(base_type_name) is None:
                if base_type_name not in visited and base_type_name not in refs:
                    refs.append(base_type_name)

        if not properties:
            return SchemaResult.empty(type_name, rel_path)

        json_schema: Dict[str, Any] = {"type": "object", "properties": properties}
        if required:
            json_schema["required"] = required

        confidence = Confidence.HIGH if all_high else Confidence.MEDIUM
        return SchemaResult(
            type_name=type_name,
            json_schema=json_schema,
            confidence=confidence,
            source_file=rel_path,
            refs=refs,
        )

    def _has_default(self, default: Optional[ast.expr]) -> bool:
        """Return True if the field has a default value (not required)."""
        if default is None:
            return False
        # Field(...) with Ellipsis means required
        if isinstance(default, ast.Call):
            if default.args and isinstance(default.args[0], ast.Constant):
                if default.args[0].value is ...:
                    return False
            return True  # Field(some_default) → has default
        return True  # literal default

    def _parse_annotation(
        self, annotation: Optional[ast.expr]
    ) -> Tuple[bool, Optional[str]]:
        """
        Parse a type annotation, returning (is_optional, base_type_name).
        Handles: Name, Optional[T], List[T], Dict[K,V], Union[T, None], Attribute.
        """
        if annotation is None:
            return False, None
        if isinstance(annotation, ast.Name):
            return False, annotation.id
        if isinstance(annotation, ast.Attribute):
            return False, annotation.attr
        if isinstance(annotation, ast.Subscript):
            outer = self._outer_name(annotation.value)
            inner = annotation.slice
            if outer == "Optional":
                return True, self._inner_name(inner)
            if outer in ("List", "Sequence", "Set", "FrozenSet"):
                return False, self._inner_name(inner)
            if outer == "Union":
                elts = self._union_elts(inner)
                non_none = [e for e in elts if e not in ("None", "NoneType")]
                is_opt = len(non_none) < len(elts)
                return is_opt, (non_none[0] if non_none else None)
        return False, None

    def _outer_name(self, node: ast.expr) -> Optional[str]:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            return node.attr
        return None

    def _inner_name(self, node: ast.expr) -> Optional[str]:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            return node.attr
        if isinstance(node, ast.Constant):
            return str(node.value)
        if hasattr(ast, "Index") and isinstance(node, ast.Index):  # Python 3.8
            return self._inner_name(node.value)  # type: ignore[attr-defined]
        return None

    def _union_elts(self, node: ast.expr) -> List[str]:
        if isinstance(node, ast.Tuple):
            return [n for elt in node.elts if (n := self._inner_name(elt))]
        if hasattr(ast, "Index") and isinstance(node, ast.Index):  # Python 3.8
            return self._union_elts(node.value)  # type: ignore[attr-defined]
        n = self._inner_name(node)
        return [n] if n else []

    def _extract_field_constraints(
        self, default: Optional[ast.expr]
    ) -> Dict[str, Any]:
        """Extract constraints from Field(min_length=1, max_length=100, ...)."""
        if default is None or not isinstance(default, ast.Call):
            return {}
        func_name = None
        if isinstance(default.func, ast.Name):
            func_name = default.func.id
        elif isinstance(default.func, ast.Attribute):
            func_name = default.func.attr
        if func_name not in ("Field", "field"):
            return {}
        mapping = {
            "min_length": "minLength",
            "max_length": "maxLength",
            "pattern": "pattern",
            "regex": "pattern",
            "ge": "minimum",
            "le": "maximum",
            "gt": "exclusiveMinimum",
            "lt": "exclusiveMaximum",
            "min_items": "minItems",
            "max_items": "maxItems",
            "multiple_of": "multipleOf",
            "title": "title",
            "description": "description",
        }
        constraints: Dict[str, Any] = {}
        for kw in default.keywords:
            if kw.arg in mapping:
                num = _ast_num(kw.value)
                if num is not None:
                    constraints[mapping[kw.arg]] = num
                else:
                    s = _ast_str(kw.value)
                    if s is not None:
                        constraints[mapping[kw.arg]] = s
        return constraints

    def _build_field_schema(
        self,
        type_name: Optional[str],
        visited: Set[str],
    ) -> Tuple[dict, Confidence]:
        """Build a JSON Schema dict for a field type."""
        if type_name is None:
            return {}, Confidence.MEDIUM
        prim = _PY_TYPE_MAP.get(type_name)
        if prim is not None:
            return dict(prim), Confidence.HIGH
        # Complex / nested type
        result = self.resolve_type(type_name, visited)
        if result.json_schema.get("$ref"):
            return result.json_schema, Confidence.HIGH
        if result.is_empty:
            return {"$ref": f"#/components/schemas/{type_name}"}, Confidence.MEDIUM
        return {"$ref": f"#/components/schemas/{type_name}"}, result.confidence
