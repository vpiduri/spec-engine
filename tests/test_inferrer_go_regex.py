"""Tests for the Go regex-fallback path in spec_engine/inferrer/go_ast.py."""

import pytest
from pathlib import Path

from spec_engine.inferrer.go_ast import GoASTInferrer
from spec_engine.config import Config

GO_STRUCT = """
package models

type CreateOrderRequest struct {
    Name    string    `json:"name" validate:"required,min=1,max=100"`
    Email   string    `json:"email" validate:"required"`
    Count   *int      `json:"count,omitempty"`
    Tags    []string  `json:"tags"`
    Addr    Address   `json:"address"`
    secret  string
    Ignored string    `json:"-"`
}
"""


@pytest.fixture
def inferrer(tmp_path):
    (tmp_path / "models.go").write_text(GO_STRUCT)
    inf = GoASTInferrer.__new__(GoASTInferrer)
    inf.repo_path = tmp_path
    inf.config = Config()
    inf._ast_binary = None
    inf.schema_registry = {}
    inf._visiting = set()
    return inf


class TestGoRegexFallback:
    def test_finds_go_file(self, inferrer):
        f = inferrer._find_type_file("CreateOrderRequest")
        assert f is not None
        assert f.name == "models.go"

    def test_name_is_string(self, inferrer):
        result = inferrer.resolve_type("CreateOrderRequest")
        assert result.json_schema["properties"]["name"]["type"] == "string"

    def test_name_required_from_validate_tag(self, inferrer):
        result = inferrer.resolve_type("CreateOrderRequest")
        assert "name" in result.json_schema.get("required", [])

    def test_name_has_min_max_constraints(self, inferrer):
        result = inferrer.resolve_type("CreateOrderRequest")
        name_schema = result.json_schema["properties"]["name"]
        assert name_schema.get("minimum") == 1.0
        assert name_schema.get("maximum") == 100.0

    def test_email_required(self, inferrer):
        result = inferrer.resolve_type("CreateOrderRequest")
        assert "email" in result.json_schema.get("required", [])

    def test_optional_field_nullable(self, inferrer):
        result = inferrer.resolve_type("CreateOrderRequest")
        count_schema = result.json_schema["properties"]["count"]
        assert count_schema.get("nullable") is True

    def test_slice_field_is_array(self, inferrer):
        result = inferrer.resolve_type("CreateOrderRequest")
        tags_schema = result.json_schema["properties"]["tags"]
        assert tags_schema["type"] == "array"
        assert tags_schema["items"]["type"] == "string"

    def test_complex_type_uses_ref(self, inferrer):
        result = inferrer.resolve_type("CreateOrderRequest")
        addr_schema = result.json_schema["properties"]["address"]
        assert "$ref" in addr_schema

    def test_unexported_field_excluded(self, inferrer):
        result = inferrer.resolve_type("CreateOrderRequest")
        assert "secret" not in result.json_schema["properties"]

    def test_json_dash_excluded(self, inferrer):
        result = inferrer.resolve_type("CreateOrderRequest")
        assert "Ignored" not in result.json_schema["properties"]
        # The field has json:"-" so it should be skipped entirely
        assert "-" not in result.json_schema["properties"]

    def test_missing_struct_returns_empty(self, inferrer):
        result = inferrer.resolve_type("NonExistentType")
        assert result.is_empty
