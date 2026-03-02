"""
Java AST schema inferrer.

Parses Java class files using the javalang library to extract fields, types,
and annotations. Maps Java/Jakarta validation annotations to JSON Schema:
  @NotNull       → required field
  @Size(min, max)→ minLength / maxLength
  @Min / @Max    → minimum / maximum
  @Pattern       → pattern
  @Email         → format: email
  @NotBlank      → minLength: 1

Supports: plain POJOs, Lombok @Data, Jackson @JsonProperty renaming.
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import javalang
import javalang.tree as jt

from spec_engine.models import SchemaResult, Confidence
from spec_engine.inferrer.base import BaseInferrer, _PRIMITIVE_MAP
from spec_engine.config import Config

log = logging.getLogger(__name__)

# Java/Jakarta constraint annotations → JSON Schema keys
_CONSTRAINT_MAP = {
    "NotNull": {},
    "NotBlank": {"minLength": 1},
    "NotEmpty": {"minLength": 1},
    "Email": {"format": "email"},
}

# Annotations that mark a field as required
_REQUIRED_ANNOTATIONS = {"NotNull", "NotBlank", "NotEmpty"}

# Annotations that remove a field from output
_IGNORE_ANNOTATIONS = {"JsonIgnore", "Transient"}

# Java type → JSON Schema
_JAVA_TYPE_MAP: Dict[str, dict] = {
    "String": {"type": "string"},
    "Integer": {"type": "integer"},
    "int": {"type": "integer"},
    "Long": {"type": "integer", "format": "int64"},
    "long": {"type": "integer", "format": "int64"},
    "Short": {"type": "integer"},
    "short": {"type": "integer"},
    "Byte": {"type": "integer"},
    "byte": {"type": "integer"},
    "Double": {"type": "number", "format": "double"},
    "double": {"type": "number", "format": "double"},
    "Float": {"type": "number", "format": "float"},
    "float": {"type": "number", "format": "float"},
    "Boolean": {"type": "boolean"},
    "boolean": {"type": "boolean"},
    "BigDecimal": {"type": "number"},
    "BigInteger": {"type": "integer"},
    "LocalDate": {"type": "string", "format": "date"},
    "LocalDateTime": {"type": "string", "format": "date-time"},
    "ZonedDateTime": {"type": "string", "format": "date-time"},
    "OffsetDateTime": {"type": "string", "format": "date-time"},
    "Instant": {"type": "string", "format": "date-time"},
    "UUID": {"type": "string", "format": "uuid"},
    "Object": {"type": "object"},
}


# ---------------------------------------------------------------------------
# Annotation value helpers (reuse logic from scanner)
# ---------------------------------------------------------------------------

def _strip_quotes(value: Any) -> str:
    s = str(value).strip()
    if s.startswith('"') and s.endswith('"'):
        return s[1:-1]
    return s


def _get_element_pairs(annotation: Any) -> list:
    """Return all ElementValuePair objects from annotation.element or annotation.elements."""
    pairs = []
    elem = getattr(annotation, "element", None)
    if isinstance(elem, list):
        pairs.extend(elem)
    pairs.extend(getattr(annotation, "elements", None) or [])
    return pairs


def _get_annotation_value(annotation: Any, key: Optional[str] = None) -> Optional[str]:
    if key is None:
        elem = getattr(annotation, "element", None)
        if elem is not None and not isinstance(elem, list):
            if hasattr(elem, "value"):
                return _strip_quotes(elem.value)
            return _strip_quotes(str(elem))
        val = _get_annotation_value(annotation, "value")
        return val
    else:
        for el in _get_element_pairs(annotation):
            if not hasattr(el, "name") or el.name != key:
                continue
            val = el.value
            if val is None:
                return None
            if hasattr(val, "member"):
                return str(val.member)
            if hasattr(val, "value"):
                return _strip_quotes(val.value)
            return _strip_quotes(str(val))
        return None


def _get_annotation_int(annotation: Any, key: str) -> Optional[int]:
    val = _get_annotation_value(annotation, key)
    if val is None:
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# JavaASTInferrer
# ---------------------------------------------------------------------------

class JavaASTInferrer(BaseInferrer):
    """Infer JSON Schema from Java classes using javalang."""

    def _find_type_file(self, type_name: str) -> Optional[Path]:
        """
        Find a .java file that defines the given type.
        Prefers paths containing model/dto/domain/entity.
        """
        candidates: List[Path] = []
        for java_file in self.repo_path.rglob(f"{type_name}.java"):
            candidates.append(java_file)

        if not candidates:
            return None

        priority_parts = {"dto", "request", "response", "model", "domain", "entity"}
        priority_order = list(priority_parts)

        def _priority(p: Path) -> int:
            parts_lower = {part.lower() for part in p.parts}
            for i, key in enumerate(priority_order):
                if key in parts_lower:
                    return i
            return len(priority_order)

        sorted_candidates = sorted(candidates, key=_priority)
        ranked = self._rank_candidates(sorted_candidates)
        return ranked[0] if ranked else None

    def _extract_fields(
        self, type_name: str, source_file: Path, visited: Set[str]
    ) -> SchemaResult:
        """Parse a Java source file and extract JSON Schema for the named type."""
        source = source_file.read_text(encoding="utf-8", errors="ignore")
        try:
            tree = javalang.parse.parse(source)
        except Exception as e:
            log.debug("JavaASTInferrer: parse error in %s: %s", source_file, e)
            return SchemaResult.empty(type_name, str(source_file))

        try:
            rel_path = str(source_file.relative_to(self.repo_path))
        except ValueError:
            rel_path = str(source_file)

        # Try class declaration
        for _, cls in tree.filter(jt.ClassDeclaration):
            if cls.name == type_name:
                return self._extract_class(cls, type_name, rel_path, visited, source_file)

        # Try enum declaration
        for _, enum in tree.filter(jt.EnumDeclaration):
            if enum.name == type_name:
                return self._extract_enum(enum, type_name, rel_path)

        return SchemaResult.empty(type_name, rel_path)

    def _extract_class(
        self,
        cls: jt.ClassDeclaration,
        type_name: str,
        rel_path: str,
        visited: Set[str],
        source_file: Path,
    ) -> SchemaResult:
        """Build JSON Schema from a Java class declaration."""
        properties: Dict[str, Any] = {}
        required: List[str] = []
        refs: List[str] = []
        all_high = True

        for field_decl in (cls.fields or []):
            field_anns = field_decl.annotations or []

            # Skip @JsonIgnore or @Transient
            ann_names = {a.name for a in field_anns}
            if ann_names & _IGNORE_ANNOTATIONS:
                continue

            # Field name (may be renamed by @JsonProperty)
            for declarator in (field_decl.declarators or []):
                raw_name = declarator.name
                field_name = self._json_property_name(field_anns, raw_name)

                # Type
                java_type = field_decl.type
                type_str = str(java_type.name) if java_type else "Object"
                args = getattr(java_type, "arguments", None)
                if args:
                    # Reconstruct generic type string
                    inner = ", ".join(str(a.type.name) if hasattr(a, "type") and a.type else "Object" for a in args)
                    type_str = f"{type_str}<{inner}>"

                # Build field schema
                field_schema, field_confidence = self._java_type_to_schema(type_str, visited)
                if field_confidence != Confidence.HIGH:
                    all_high = False

                # Apply constraint annotations
                constraints = self._get_constraints(field_anns)
                field_schema = {**field_schema, **constraints}

                # Check required
                is_optional = self._is_optional_type(type_str)
                if not is_optional and (ann_names & _REQUIRED_ANNOTATIONS):
                    required.append(field_name)

                properties[field_name] = field_schema

                # Track refs
                base_type = type_str.split("<")[0]
                if _JAVA_TYPE_MAP.get(base_type) is None and _PRIMITIVE_MAP.get(base_type) is None:
                    if base_type not in visited and base_type not in refs:
                        refs.append(base_type)

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

    def _extract_enum(
        self, enum: jt.EnumDeclaration, type_name: str, rel_path: str
    ) -> SchemaResult:
        """Build JSON Schema from a Java enum declaration."""
        enum_values: List[str] = []
        for constant in (enum.body.constants or []):
            enum_values.append(constant.name)

        if not enum_values:
            return SchemaResult.empty(type_name, rel_path)

        json_schema: Dict[str, Any] = {"type": "string", "enum": enum_values}
        return SchemaResult(
            type_name=type_name,
            json_schema=json_schema,
            confidence=Confidence.HIGH,
            source_file=rel_path,
        )

    def _java_type_to_schema(
        self, type_str: str, visited: Set[str]
    ) -> Tuple[dict, Confidence]:
        """Convert a Java type string to a JSON Schema dict."""
        type_str = type_str.strip()

        # Direct primitive/known type
        known = _JAVA_TYPE_MAP.get(type_str)
        if known is not None:
            return dict(known), Confidence.HIGH

        # Check base inferrer primitives
        prim = self._is_primitive(type_str)
        if prim is not None:
            return dict(prim), Confidence.HIGH

        # Generic types via resolve_type
        result = self.resolve_type(type_str, visited)
        if result.json_schema.get("$ref"):
            return result.json_schema, Confidence.HIGH
        if result.is_empty:
            base = type_str.split("<")[0]
            return {"$ref": f"#/components/schemas/{base}"}, Confidence.MEDIUM
        # Named type — wrap as $ref for components/schemas
        if result.json_schema.get("type") == "object" and "properties" in result.json_schema:
            base = type_str.split("<")[0]
            return {"$ref": f"#/components/schemas/{base}"}, result.confidence
        return result.json_schema, result.confidence

    def _is_optional_type(self, type_str: str) -> bool:
        """Return True if the type is Optional<T> (Java)."""
        return type_str.startswith("Optional<")

    def _json_property_name(self, annotations: List[Any], default: str) -> str:
        """Return @JsonProperty value if present, else default."""
        for ann in annotations:
            if ann.name == "JsonProperty":
                val = _get_annotation_value(ann)
                if val:
                    return val
        return default

    def _get_constraints(self, annotations: List[Any]) -> Dict[str, Any]:
        """Extract JSON Schema constraints from Jakarta/Jackson annotations."""
        constraints: Dict[str, Any] = {}
        for ann in annotations:
            name = ann.name
            if name == "Size":
                mn = _get_annotation_int(ann, "min")
                mx = _get_annotation_int(ann, "max")
                if mn is not None:
                    constraints["minLength"] = mn
                if mx is not None:
                    constraints["maxLength"] = mx
            elif name == "Min":
                val = _get_annotation_int(ann, "value")
                if val is None:
                    val = _get_annotation_int(ann, None)
                if val is not None:
                    constraints["minimum"] = val
            elif name == "Max":
                val = _get_annotation_int(ann, "value")
                if val is None:
                    val = _get_annotation_int(ann, None)
                if val is not None:
                    constraints["maximum"] = val
            elif name == "Pattern":
                val = _get_annotation_value(ann, "regexp")
                if val is None:
                    val = _get_annotation_value(ann)
                if val:
                    constraints["pattern"] = val
            elif name == "Email":
                constraints["format"] = "email"
            elif name == "NotBlank":
                if "minLength" not in constraints:
                    constraints["minLength"] = 1
            elif name == "Positive":
                constraints["minimum"] = 1
            elif name == "PositiveOrZero":
                constraints["minimum"] = 0
            elif name == "Negative":
                constraints["maximum"] = -1
            elif name == "NegativeOrZero":
                constraints["maximum"] = 0
        return constraints
