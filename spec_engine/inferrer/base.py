"""
Base schema inferrer.

All language-specific inferrers inherit from BaseInferrer and must implement
_find_type_file() and _extract_fields(). The base class provides:
  - resolve_type() with cycle detection, registry cache, and generic unwrapping
  - _is_primitive() for Java/Python/Go/TypeScript primitive type mapping
  - _unwrap_generic() for stripping outer generic wrappers
"""

from abc import ABC, abstractmethod
import logging
import re
from pathlib import Path
from typing import Dict, List, Optional, Set

from spec_engine.models import SchemaResult, Confidence
from spec_engine.config import Config

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Primitive type map — covers Java, Python, Go, TypeScript
# ---------------------------------------------------------------------------

_PRIMITIVE_MAP: Dict[str, dict] = {
    # Strings
    "str": {"type": "string"},
    "String": {"type": "string"},
    "string": {"type": "string"},
    "char": {"type": "string"},
    "Character": {"type": "string"},
    # Integers
    "int": {"type": "integer"},
    "Integer": {"type": "integer"},
    "Long": {"type": "integer", "format": "int64"},
    "long": {"type": "integer", "format": "int64"},
    "Short": {"type": "integer"},
    "short": {"type": "integer"},
    "Byte": {"type": "integer"},
    "BigInteger": {"type": "integer"},
    "int8": {"type": "integer"},
    "int16": {"type": "integer"},
    "int32": {"type": "integer"},
    "int64": {"type": "integer", "format": "int64"},
    "uint": {"type": "integer"},
    "uint8": {"type": "integer"},
    "uint16": {"type": "integer"},
    "uint32": {"type": "integer"},
    "uint64": {"type": "integer"},
    "byte": {"type": "integer"},
    "rune": {"type": "integer"},
    # Numbers
    "float": {"type": "number", "format": "float"},
    "Float": {"type": "number", "format": "float"},
    "Double": {"type": "number", "format": "double"},
    "double": {"type": "number", "format": "double"},
    "float32": {"type": "number", "format": "float"},
    "float64": {"type": "number", "format": "double"},
    "number": {"type": "number"},
    "BigDecimal": {"type": "number"},
    "Decimal": {"type": "number"},
    # Booleans
    "bool": {"type": "boolean"},
    "Boolean": {"type": "boolean"},
    "boolean": {"type": "boolean"},
    # Dates
    "datetime": {"type": "string", "format": "date-time"},
    "date": {"type": "string", "format": "date"},
    "time": {"type": "string", "format": "time"},
    "Date": {"type": "string", "format": "date-time"},
    "LocalDate": {"type": "string", "format": "date"},
    "LocalDateTime": {"type": "string", "format": "date-time"},
    "ZonedDateTime": {"type": "string", "format": "date-time"},
    "OffsetDateTime": {"type": "string", "format": "date-time"},
    "Instant": {"type": "string", "format": "date-time"},
    # UUIDs
    "UUID": {"type": "string", "format": "uuid"},
    # Objects / null
    "object": {"type": "object"},
    "Object": {"type": "object"},
    "None": {"type": "null"},
    "Void": {"type": "null"},
    "void": {"type": "null"},
    "null": {"type": "null"},
    "undefined": {"type": "null"},
    # Misc
    "bytes": {"type": "string", "format": "binary"},
    "any": {},
    "unknown": {},
    "never": {},
}

# Types that wrap a single inner type (unwrap transparently)
_UNWRAP_SINGLE: Set[str] = {
    "Optional", "ResponseEntity", "CompletableFuture", "Future",
    "Mono", "Flux", "Promise", "Maybe", "Either", "Result",
}

# Array-like container types
_UNWRAP_ARRAY: Set[str] = {
    "List", "ArrayList", "LinkedList", "Set", "HashSet", "LinkedHashSet",
    "TreeSet", "SortedSet", "Collection", "Iterable", "Queue", "Deque",
    "ArrayDeque", "Stream", "Array",
}

# Map-like container types
_MAP_TYPES: Set[str] = {
    "Map", "HashMap", "LinkedHashMap", "TreeMap", "ConcurrentHashMap",
    "SortedMap", "Record", "Dict",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _unwrap_generic(type_name: str) -> tuple[str, str]:
    """
    Strip the outermost generic wrapper from a type name.

    Returns (outer, inner) where inner is the content inside the outermost < >.
    Returns (type_name, "") if no generics found.

    Examples:
      "List<Account>"          → ("List", "Account")
      "Map<String, Account>"   → ("Map", "String, Account")
      "ResponseEntity<T>"      → ("ResponseEntity", "T")
      "String"                 → ("String", "")
    """
    t = type_name.strip()
    lt = t.find("<")
    if lt == -1:
        return t, ""
    if not t.endswith(">"):
        return t, ""
    outer = t[:lt].strip()
    inner = t[lt + 1:-1].strip()
    return outer, inner


def _split_top_level(s: str) -> List[str]:
    """
    Split a string on top-level commas (not inside < >, ( ), or [ ]).

    Used to extract individual type arguments from generic type strings.
    """
    parts: List[str] = []
    depth = 0
    current: List[str] = []
    for c in s:
        if c in "<([":
            depth += 1
            current.append(c)
        elif c in ">)]":
            depth -= 1
            current.append(c)
        elif c == "," and depth == 0:
            parts.append("".join(current).strip())
            current = []
        else:
            current.append(c)
    if current:
        parts.append("".join(current).strip())
    return parts


# ---------------------------------------------------------------------------
# BaseInferrer
# ---------------------------------------------------------------------------

class BaseInferrer(ABC):
    """Abstract base class for language-specific schema inferrers."""

    def __init__(self, repo_path: str, config: Config) -> None:
        self.repo_path = Path(repo_path)
        self.config = config
        self.schema_registry: Dict[str, SchemaResult] = {}

    def resolve_type(
        self,
        type_name: str,
        visited: Optional[Set[str]] = None,
    ) -> SchemaResult:
        """
        Resolve a type name to a SchemaResult with cycle detection.

        Steps:
          1. Unwrap outermost generic wrapper
          2. Handle array/map/single-value containers recursively
          3. Check primitives → return inline schema
          4. Cycle detection (visited set) → return $ref
          5. Registry cache → return cached result
          6. Find source file and extract fields
          7. Store in registry and return
        """
        if visited is None:
            visited = set()

        type_name = type_name.strip()
        if not type_name:
            return SchemaResult.empty("", "")

        # Step 1: unwrap generics
        outer, inner = _unwrap_generic(type_name)

        if inner:
            inner_parts = _split_top_level(inner)
            inner_type = inner_parts[0]

            # Array-like container
            if outer in _UNWRAP_ARRAY:
                inner_result = self.resolve_type(inner_type, visited)
                items_schema = self._ref_or_inline(inner_type, inner_result)
                return SchemaResult(
                    type_name=type_name,
                    json_schema={"type": "array", "items": items_schema},
                    confidence=inner_result.confidence,
                    source_file=inner_result.source_file,
                )

            # Map-like container
            if outer in _MAP_TYPES:
                val_type = inner_parts[1] if len(inner_parts) > 1 else inner_type
                val_result = self.resolve_type(val_type, visited)
                add_props = self._ref_or_inline(val_type, val_result)
                return SchemaResult(
                    type_name=type_name,
                    json_schema={"type": "object", "additionalProperties": add_props},
                    confidence=val_result.confidence,
                    source_file=val_result.source_file,
                )

            # Single-value wrapper → resolve inner transparently
            if outer in _UNWRAP_SINGLE:
                return self.resolve_type(inner_type, visited)

            # Unknown generic — resolve by outer name only
            type_name = outer

        # Step 2: primitives
        primitive = self._is_primitive(type_name)
        if primitive is not None:
            return SchemaResult(
                type_name=type_name,
                json_schema=primitive,
                confidence=Confidence.HIGH,
                source_file="",
            )

        # Step 3: cycle detection
        if type_name in visited:
            return SchemaResult(
                type_name=type_name,
                json_schema={"$ref": f"#/components/schemas/{type_name}"},
                confidence=Confidence.HIGH,
                source_file="",
            )

        # Step 4: registry cache
        if type_name in self.schema_registry:
            return self.schema_registry[type_name]

        # Step 5: find file and extract
        visited_copy = visited | {type_name}

        source_file = self._find_type_file(type_name)
        if source_file is None:
            result = SchemaResult.empty(type_name, "")
            self.schema_registry[type_name] = result
            return result

        result = self._extract_fields(type_name, source_file, visited_copy)
        self.schema_registry[type_name] = result
        return result

    def _rank_candidates(self, candidates: List[Path]) -> List[Path]:
        """
        Warn if multiple files define the same type; apply prefer_file glob.
        Returns candidates sorted so prefer_file matches come first.
        """
        import fnmatch
        if len(candidates) > 1:
            log.warning(
                "Type defined in %d files: %s — using %s. "
                "Set config.prefer_file to control selection.",
                len(candidates),
                [str(c) for c in candidates],
                candidates[0],
            )
        prefer = getattr(self.config, "prefer_file", "")
        if not prefer:
            return candidates
        preferred = [c for c in candidates if fnmatch.fnmatch(str(c), prefer)]
        rest = [c for c in candidates if c not in preferred]
        return preferred + rest

    def _ref_or_inline(self, type_name: str, result: SchemaResult) -> dict:
        """
        Return a $ref for named complex types, or inline schema for primitives/generics.
        """
        # Already a $ref — pass through
        if "$ref" in result.json_schema:
            return result.json_schema
        # Primitive — inline
        if self._is_primitive(type_name) is not None:
            return result.json_schema
        # Generic type — inline (can't $ref a generic name)
        if "<" in type_name:
            return result.json_schema
        # Named complex type (even if empty) — use $ref so OpenAPI spec can reference it
        return {"$ref": f"#/components/schemas/{type_name}"}

    def _is_primitive(self, type_name: str) -> Optional[dict]:
        """Return JSON Schema dict for a primitive type, or None if not primitive."""
        return _PRIMITIVE_MAP.get(type_name)

    @abstractmethod
    def _find_type_file(self, type_name: str) -> Optional[Path]:
        """Find the source file that defines the given type name. Returns None if not found."""

    @abstractmethod
    def _extract_fields(
        self, type_name: str, source_file: Path, visited: Set[str]
    ) -> SchemaResult:
        """Extract JSON Schema fields from the source file for the given type."""
