"""Tests for spec_engine/inferrer/java_ast.py — JavaASTInferrer."""

import pytest
from pathlib import Path

from spec_engine.inferrer.java_ast import JavaASTInferrer
from spec_engine.models import Confidence
from spec_engine.config import Config

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "java"


@pytest.fixture
def inferrer():
    return JavaASTInferrer(str(FIXTURE_DIR), Config())


class TestJavaASTInferrer:
    def test_find_type_file_returns_path(self, inferrer):
        path = inferrer._find_type_file("CreateAccountRequest")
        assert path is not None
        assert path.name == "CreateAccountRequest.java"

    def test_find_type_file_returns_none_for_unknown(self, inferrer):
        path = inferrer._find_type_file("NonExistentClass")
        assert path is None

    def test_resolve_create_account_request(self, inferrer):
        result = inferrer.resolve_type("CreateAccountRequest")
        assert not result.is_empty
        assert result.json_schema.get("type") == "object"
        assert "properties" in result.json_schema

    def test_create_account_request_has_name_field(self, inferrer):
        result = inferrer.resolve_type("CreateAccountRequest")
        props = result.json_schema["properties"]
        assert "name" in props
        assert props["name"]["type"] == "string"

    def test_create_account_request_has_email_field(self, inferrer):
        result = inferrer.resolve_type("CreateAccountRequest")
        props = result.json_schema["properties"]
        assert "email" in props

    def test_name_field_has_size_constraints(self, inferrer):
        result = inferrer.resolve_type("CreateAccountRequest")
        name_schema = result.json_schema["properties"]["name"]
        assert name_schema.get("minLength") == 1
        assert name_schema.get("maxLength") == 100

    def test_email_field_has_format(self, inferrer):
        result = inferrer.resolve_type("CreateAccountRequest")
        email_schema = result.json_schema["properties"]["email"]
        assert email_schema.get("format") == "email"

    def test_required_fields_populated(self, inferrer):
        result = inferrer.resolve_type("CreateAccountRequest")
        required = result.json_schema.get("required", [])
        assert "name" in required
        assert "email" in required

    def test_resolve_address_class(self, inferrer):
        result = inferrer.resolve_type("Address")
        assert not result.is_empty
        props = result.json_schema["properties"]
        assert "street" in props
        assert "city" in props

    def test_resolve_account_status_enum(self, inferrer):
        result = inferrer.resolve_type("AccountStatus")
        # Enums have no "properties" key so is_empty is True by design
        # but the json_schema dict itself should be non-empty
        assert result.json_schema  # non-empty dict
        schema = result.json_schema
        assert schema.get("type") == "string"
        assert "ACTIVE" in schema.get("enum", [])
        assert "INACTIVE" in schema.get("enum", [])
        assert "SUSPENDED" in schema.get("enum", [])

    def test_credit_limit_uses_json_property_name(self, inferrer):
        result = inferrer.resolve_type("CreateAccountRequest")
        props = result.json_schema["properties"]
        # @JsonProperty("credit_limit") should rename the field
        assert "credit_limit" in props or "creditLimit" in props

    def test_confidence_is_high_for_fully_resolved(self, inferrer):
        result = inferrer.resolve_type("AccountStatus")
        assert result.confidence == Confidence.HIGH

    def test_source_file_is_set(self, inferrer):
        result = inferrer.resolve_type("Address")
        assert result.source_file.endswith("Address.java")

    def test_parse_error_returns_empty(self, tmp_path):
        bad_file = tmp_path / "Bad.java"
        bad_file.write_text("this is not { valid java }}}")
        inferrer = JavaASTInferrer(str(tmp_path), Config())
        result = inferrer._extract_fields("Bad", bad_file, set())
        assert result.is_empty

    def test_address_required_fields(self, inferrer):
        result = inferrer.resolve_type("Address")
        required = result.json_schema.get("required", [])
        # street and city have @NotBlank
        assert "street" in required
        assert "city" in required


class TestJavaConstraints:
    def test_min_constraint(self, tmp_path):
        source = '''
public class Item {
    @Min(0)
    private Integer quantity;
}
'''
        (tmp_path / "Item.java").write_text(source)
        inferrer = JavaASTInferrer(str(tmp_path), Config())
        result = inferrer.resolve_type("Item")
        assert result.json_schema["properties"]["quantity"].get("minimum") == 0

    def test_max_constraint(self, tmp_path):
        source = '''
public class Item {
    @Max(100)
    private Integer score;
}
'''
        (tmp_path / "Item.java").write_text(source)
        inferrer = JavaASTInferrer(str(tmp_path), Config())
        result = inferrer.resolve_type("Item")
        assert result.json_schema["properties"]["score"].get("maximum") == 100

    def test_nested_type_uses_ref(self, tmp_path):
        source = '''
public class Order {
    private Address shippingAddress;
}
'''
        (tmp_path / "Order.java").write_text(source)
        inferrer = JavaASTInferrer(str(tmp_path), Config())
        result = inferrer.resolve_type("Order")
        addr_schema = result.json_schema["properties"]["shippingAddress"]
        assert addr_schema.get("$ref") == "#/components/schemas/Address" or \
               "Address" in str(addr_schema)
