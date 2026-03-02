"""Tests for spec_engine/inferrer/base.py — BaseInferrer, cycle detection, _unwrap_generic."""

import pytest
from pathlib import Path
from typing import Optional, Set

from spec_engine.inferrer.base import (
    BaseInferrer,
    _unwrap_generic,
    _split_top_level,
    _PRIMITIVE_MAP,
    _UNWRAP_SINGLE,
    _UNWRAP_ARRAY,
)
from spec_engine.models import SchemaResult, Confidence
from spec_engine.config import Config


# ---------------------------------------------------------------------------
# Concrete stub inferrer for testing
# ---------------------------------------------------------------------------

class StubInferrer(BaseInferrer):
    """Concrete inferrer that returns pre-canned schemas for testing."""

    def __init__(self, repo_path, config, type_files=None, schemas=None):
        super().__init__(repo_path, config)
        self._type_files = type_files or {}   # type_name → Path
        self._schemas = schemas or {}          # type_name → SchemaResult

    def _find_type_file(self, type_name: str) -> Optional[Path]:
        return self._type_files.get(type_name)

    def _extract_fields(
        self, type_name: str, source_file: Path, visited: Set[str]
    ) -> SchemaResult:
        return self._schemas.get(
            type_name,
            SchemaResult.empty(type_name, str(source_file))
        )


# ---------------------------------------------------------------------------
# Tests for _unwrap_generic
# ---------------------------------------------------------------------------

class TestUnwrapGeneric:
    def test_no_generics_returns_unchanged(self):
        outer, inner = _unwrap_generic("String")
        assert outer == "String"
        assert inner == ""

    def test_simple_list(self):
        outer, inner = _unwrap_generic("List<Account>")
        assert outer == "List"
        assert inner == "Account"

    def test_optional(self):
        outer, inner = _unwrap_generic("Optional<String>")
        assert outer == "Optional"
        assert inner == "String"

    def test_map_two_args(self):
        outer, inner = _unwrap_generic("Map<String, Integer>")
        assert outer == "Map"
        assert inner == "String, Integer"

    def test_nested_generic(self):
        outer, inner = _unwrap_generic("List<Map<String, Account>>")
        assert outer == "List"
        assert inner == "Map<String, Account>"

    def test_response_entity(self):
        outer, inner = _unwrap_generic("ResponseEntity<AccountResponse>")
        assert outer == "ResponseEntity"
        assert inner == "AccountResponse"

    def test_no_closing_bracket(self):
        outer, inner = _unwrap_generic("List<Account")
        assert outer == "List<Account"
        assert inner == ""


class TestSplitTopLevel:
    def test_single_type(self):
        assert _split_top_level("String") == ["String"]

    def test_two_args(self):
        assert _split_top_level("String, Integer") == ["String", "Integer"]

    def test_nested_generics_preserved(self):
        result = _split_top_level("Map<String, Account>, Integer")
        assert result == ["Map<String, Account>", "Integer"]

    def test_triple_args(self):
        result = _split_top_level("A, B, C")
        assert result == ["A", "B", "C"]


# ---------------------------------------------------------------------------
# Tests for _is_primitive
# ---------------------------------------------------------------------------

class TestIsPrimitive:
    @pytest.fixture
    def inferrer(self):
        return StubInferrer("/tmp", Config())

    def test_java_string(self, inferrer):
        assert inferrer._is_primitive("String") == {"type": "string"}

    def test_python_int(self, inferrer):
        assert inferrer._is_primitive("int") == {"type": "integer"}

    def test_go_float64(self, inferrer):
        assert inferrer._is_primitive("float64") == {"type": "number", "format": "double"}

    def test_ts_boolean(self, inferrer):
        assert inferrer._is_primitive("boolean") == {"type": "boolean"}

    def test_uuid(self, inferrer):
        assert inferrer._is_primitive("UUID") == {"type": "string", "format": "uuid"}

    def test_unknown_returns_none(self, inferrer):
        assert inferrer._is_primitive("AccountRequest") is None

    def test_none_returns_none(self, inferrer):
        assert inferrer._is_primitive("None") == {"type": "null"}


# ---------------------------------------------------------------------------
# Tests for resolve_type — primitives
# ---------------------------------------------------------------------------

class TestResolveTypePrimitive:
    @pytest.fixture
    def inferrer(self):
        return StubInferrer("/tmp", Config())

    def test_resolves_string_primitive(self, inferrer):
        result = inferrer.resolve_type("String")
        assert result.json_schema == {"type": "string"}
        assert result.confidence == Confidence.HIGH

    def test_resolves_integer_primitive(self, inferrer):
        result = inferrer.resolve_type("Integer")
        assert result.json_schema["type"] == "integer"

    def test_resolves_python_str(self, inferrer):
        result = inferrer.resolve_type("str")
        assert result.json_schema == {"type": "string"}

    def test_resolves_empty_type_returns_empty(self, inferrer):
        result = inferrer.resolve_type("")
        assert result.is_empty


# ---------------------------------------------------------------------------
# Tests for resolve_type — generic unwrapping
# ---------------------------------------------------------------------------

class TestResolveTypeGenerics:
    @pytest.fixture
    def inferrer(self):
        return StubInferrer("/tmp", Config())

    def test_list_of_string(self, inferrer):
        result = inferrer.resolve_type("List<String>")
        assert result.json_schema["type"] == "array"
        assert result.json_schema["items"] == {"type": "string"}

    def test_optional_string_unwraps(self, inferrer):
        result = inferrer.resolve_type("Optional<String>")
        assert result.json_schema == {"type": "string"}

    def test_response_entity_unwraps(self, inferrer):
        result = inferrer.resolve_type("ResponseEntity<String>")
        assert result.json_schema == {"type": "string"}

    def test_map_returns_object(self, inferrer):
        result = inferrer.resolve_type("Map<String, Integer>")
        assert result.json_schema["type"] == "object"
        assert "additionalProperties" in result.json_schema

    def test_list_of_complex_type_returns_array_with_ref(self, inferrer):
        result = inferrer.resolve_type("List<Account>")
        assert result.json_schema["type"] == "array"
        items = result.json_schema["items"]
        assert items == {"$ref": "#/components/schemas/Account"} or \
               result.json_schema["items"].get("type") is not None


# ---------------------------------------------------------------------------
# Tests for cycle detection
# ---------------------------------------------------------------------------

class TestCycleDetection:
    def test_cycle_returns_ref_instead_of_infinite_recursion(self, tmp_path):
        # Create a schema that would cause a cycle: A has field of type A
        a_result = SchemaResult(
            type_name="A",
            json_schema={"type": "object", "properties": {}},
            confidence=Confidence.HIGH,
            source_file="A.java",
        )
        source_file = tmp_path / "A.java"
        source_file.write_text("class A {}")

        inferrer = StubInferrer(
            str(tmp_path),
            Config(),
            type_files={"A": source_file},
            schemas={"A": a_result},
        )

        # Simulate cycle: A is in visited when we try to resolve A
        result = inferrer.resolve_type("A", visited={"A"})
        assert result.json_schema == {"$ref": "#/components/schemas/A"}

    def test_registry_prevents_duplicate_resolution(self, tmp_path):
        source_file = tmp_path / "User.java"
        source_file.write_text("class User {}")
        user_schema = SchemaResult(
            type_name="User",
            json_schema={"type": "object", "properties": {"name": {"type": "string"}}},
            confidence=Confidence.HIGH,
            source_file="User.java",
        )
        inferrer = StubInferrer(
            str(tmp_path),
            Config(),
            type_files={"User": source_file},
            schemas={"User": user_schema},
        )

        r1 = inferrer.resolve_type("User")
        r2 = inferrer.resolve_type("User")  # Should hit cache
        assert r1 is r2  # Same object from registry

    def test_visited_set_is_not_mutated(self, tmp_path):
        """resolve_type must not mutate the visited set passed by caller."""
        source_file = tmp_path / "Node.java"
        source_file.write_text("class Node {}")
        node_schema = SchemaResult(
            type_name="Node",
            json_schema={"type": "object", "properties": {}},
            confidence=Confidence.HIGH,
            source_file="Node.java",
        )
        inferrer = StubInferrer(
            str(tmp_path),
            Config(),
            type_files={"Node": source_file},
            schemas={"Node": node_schema},
        )
        original_visited = {"A", "B"}
        visited_copy = set(original_visited)
        inferrer.resolve_type("Node", visited=visited_copy)
        assert visited_copy == original_visited  # must not be mutated


# ---------------------------------------------------------------------------
# Tests for not-found type
# ---------------------------------------------------------------------------

class TestResolveTypeNotFound:
    def test_missing_type_returns_empty_schema_result(self):
        inferrer = StubInferrer("/tmp", Config())
        result = inferrer.resolve_type("NonExistentType")
        assert result.is_empty
        assert result.confidence == Confidence.MANUAL
