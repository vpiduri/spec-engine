"""Tests for spec_engine/inferrer/python_ast.py — PythonASTInferrer."""

import pytest
from pathlib import Path

from spec_engine.inferrer.python_ast import PythonASTInferrer
from spec_engine.models import Confidence
from spec_engine.config import Config

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "fastapi"


@pytest.fixture
def inferrer():
    return PythonASTInferrer(str(FIXTURE_DIR), Config())


class TestPythonASTInferrer:
    def test_find_type_file_returns_models_py(self, inferrer):
        path = inferrer._find_type_file("CreateAccountRequest")
        assert path is not None
        assert path.name == "models.py"

    def test_find_type_file_returns_none_for_unknown(self, inferrer):
        path = inferrer._find_type_file("NonExistentModel")
        assert path is None

    def test_resolve_create_account_request(self, inferrer):
        result = inferrer.resolve_type("CreateAccountRequest")
        assert not result.is_empty
        assert result.json_schema.get("type") == "object"
        assert "properties" in result.json_schema

    def test_create_account_has_name_field(self, inferrer):
        result = inferrer.resolve_type("CreateAccountRequest")
        assert "name" in result.json_schema["properties"]

    def test_create_account_has_email_field(self, inferrer):
        result = inferrer.resolve_type("CreateAccountRequest")
        assert "email" in result.json_schema["properties"]

    def test_name_field_has_min_length_constraint(self, inferrer):
        result = inferrer.resolve_type("CreateAccountRequest")
        name_schema = result.json_schema["properties"]["name"]
        assert name_schema.get("minLength") == 1

    def test_name_field_has_max_length_constraint(self, inferrer):
        result = inferrer.resolve_type("CreateAccountRequest")
        name_schema = result.json_schema["properties"]["name"]
        assert name_schema.get("maxLength") == 100

    def test_required_fields_populated(self, inferrer):
        result = inferrer.resolve_type("CreateAccountRequest")
        required = result.json_schema.get("required", [])
        assert "name" in required
        assert "email" in required

    def test_optional_field_not_required(self, inferrer):
        result = inferrer.resolve_type("CreateAccountRequest")
        required = result.json_schema.get("required", [])
        assert "address" not in required

    def test_address_field_is_optional(self, inferrer):
        result = inferrer.resolve_type("CreateAccountRequest")
        address_schema = result.json_schema["properties"].get("address", {})
        assert address_schema.get("nullable") is True or "address" not in result.json_schema.get("required", [])

    def test_resolve_address_model(self, inferrer):
        result = inferrer.resolve_type("Address")
        assert not result.is_empty
        props = result.json_schema["properties"]
        assert "street" in props
        assert "city" in props
        assert "zip_code" in props

    def test_resolve_account_response(self, inferrer):
        result = inferrer.resolve_type("AccountResponse")
        assert not result.is_empty
        props = result.json_schema["properties"]
        assert "id" in props
        assert "name" in props

    def test_confidence_is_high_for_simple_model(self, inferrer):
        result = inferrer.resolve_type("Address")
        assert result.confidence == Confidence.HIGH

    def test_source_file_is_set(self, inferrer):
        result = inferrer.resolve_type("CreateAccountRequest")
        assert result.source_file.endswith("models.py")


class TestPythonAnnotationParsing:
    def test_list_field_type(self, tmp_path):
        source = '''
from pydantic import BaseModel
from typing import List

class Response(BaseModel):
    items: List[str]
'''
        (tmp_path / "models.py").write_text(source)
        inferrer = PythonASTInferrer(str(tmp_path), Config())
        result = inferrer.resolve_type("Response")
        assert "items" in result.json_schema["properties"]

    def test_optional_field_is_not_required(self, tmp_path):
        source = '''
from pydantic import BaseModel
from typing import Optional

class Widget(BaseModel):
    name: str
    description: Optional[str] = None
'''
        (tmp_path / "models.py").write_text(source)
        inferrer = PythonASTInferrer(str(tmp_path), Config())
        result = inferrer.resolve_type("Widget")
        required = result.json_schema.get("required", [])
        assert "name" in required
        assert "description" not in required

    def test_nested_model_uses_ref(self, tmp_path):
        source = '''
from pydantic import BaseModel

class Inner(BaseModel):
    value: str

class Outer(BaseModel):
    inner: Inner
'''
        (tmp_path / "models.py").write_text(source)
        inferrer = PythonASTInferrer(str(tmp_path), Config())
        result = inferrer.resolve_type("Outer")
        inner_schema = result.json_schema["properties"]["inner"]
        assert inner_schema.get("$ref") == "#/components/schemas/Inner"

    def test_syntax_error_returns_empty(self, tmp_path):
        (tmp_path / "bad_model.py").write_text("class Broken(BaseModel:\n    x = 1")
        inferrer = PythonASTInferrer(str(tmp_path), Config())
        source_file = tmp_path / "bad_model.py"
        result = inferrer._extract_fields("Broken", source_file, set())
        assert result.is_empty

    def test_pattern_constraint_from_field(self, tmp_path):
        source = '''
from pydantic import BaseModel, Field

class Form(BaseModel):
    email: str = Field(..., pattern=r"^[^@]+@[^@]+$")
'''
        (tmp_path / "models.py").write_text(source)
        inferrer = PythonASTInferrer(str(tmp_path), Config())
        result = inferrer.resolve_type("Form")
        email_schema = result.json_schema["properties"]["email"]
        assert "pattern" in email_schema
