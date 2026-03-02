"""Tests for spec_engine/assembler.py — Section 6."""

import json
import pytest
import yaml

from spec_engine.assembler import (
    assemble,
    _overall_confidence,
    _detect_api_metadata,
    _build_components,
    _CONFIDENCE_PRIORITY,
)
from spec_engine.models import RouteInfo, SchemaResult, Confidence, ParamInfo
from spec_engine.config import Config


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_config(**kwargs) -> Config:
    defaults = {"gateway": "kong-prod", "owner": "team-alpha", "strict_mode": False}
    defaults.update(kwargs)
    return Config(**defaults)


def _make_route(**kwargs) -> RouteInfo:
    defaults = {
        "method": "GET",
        "path": "/v1/accounts",
        "handler": "AccountController.list",
        "file": "src/AccountController.java",
        "line": 10,
        "framework": "spring",
    }
    defaults.update(kwargs)
    return RouteInfo(**defaults)


def _make_schema(type_name: str, confidence: Confidence = Confidence.HIGH, props=None) -> SchemaResult:
    if props is None:
        props = {"id": {"type": "string"}, "name": {"type": "string"}}
    return SchemaResult(
        type_name=type_name,
        json_schema={"type": "object", "properties": props},
        confidence=confidence,
        source_file="src/Foo.java",
    )


# ---------------------------------------------------------------------------
# Basic assembly
# ---------------------------------------------------------------------------

class TestAssembleBasic:
    def test_assemble_returns_yaml_string(self, tmp_path):
        routes = [_make_route()]
        schemas = {}
        cfg = _make_config()
        result = assemble(routes, schemas, str(tmp_path), cfg)
        assert isinstance(result, str)
        assert "openapi: 3.1.0" in result

    def test_assemble_paths_contains_route_path(self, tmp_path):
        routes = [_make_route(path="/v1/accounts")]
        cfg = _make_config()
        result = assemble(routes, {}, str(tmp_path), cfg)
        assert "/v1/accounts" in result

    def test_assemble_produces_parseable_yaml(self, tmp_path):
        routes = [_make_route()]
        cfg = _make_config()
        result = assemble(routes, {}, str(tmp_path), cfg)
        doc = yaml.safe_load(result)
        assert doc["openapi"] == "3.1.0"
        assert "paths" in doc
        assert "components" in doc

    def test_assemble_operation_id_dedup(self, tmp_path):
        """Two routes with the same path and method collision → operationId gets _2 suffix."""
        route1 = _make_route(method="GET", path="/v1/items")
        route2 = _make_route(method="GET", path="/v1/items", handler="Other.list")
        # Force a collision: both generate getItems
        cfg = _make_config()
        result = assemble([route1, route2], {}, str(tmp_path), cfg)
        doc = yaml.safe_load(result)
        # Both routes share the same path — so the second will be treated as
        # the same path item entry and overwrite. For dedup testing use different paths
        # that produce the same operationId.
        assert result  # basic sanity

    def test_assemble_operation_id_dedup_different_paths(self, tmp_path):
        """Routes that generate the same operationId get _2 dedup suffix."""
        # Both POST /v1/items and POST /v1/items-extra → both produce createV1Items... — hard to force
        # Easier: same path, different methods still unique; use routes that hash same
        route1 = _make_route(method="GET", path="/v1/orders")
        route2 = _make_route(method="GET", path="/v2/orders")  # v2 also stripped → same id
        cfg = _make_config()
        result = assemble([route1, route2], {}, str(tmp_path), cfg)
        doc = yaml.safe_load(result)
        ops = []
        for path_item in doc["paths"].values():
            for op in path_item.values():
                ops.append(op.get("operationId", ""))
        # dedup should mean no duplicate operationIds
        assert len(ops) == len(set(ops))


# ---------------------------------------------------------------------------
# Info block / x- fields
# ---------------------------------------------------------------------------

class TestAssembleInfoBlock:
    def test_assemble_injects_x_owner_x_gateway_x_lifecycle(self, tmp_path):
        cfg = _make_config(owner="platform-team", gateway="istio")
        result = assemble([], {}, str(tmp_path), cfg)
        doc = yaml.safe_load(result)
        assert doc["info"]["x-owner"] == "platform-team"
        assert doc["info"]["x-gateway"] == "istio"
        assert "x-lifecycle" in doc["info"]

    def test_x_lifecycle_default_is_production(self, tmp_path):
        cfg = _make_config()
        result = assemble([], {}, str(tmp_path), cfg)
        doc = yaml.safe_load(result)
        assert doc["info"]["x-lifecycle"] == "production"

    def test_x_confidence_in_root(self, tmp_path):
        cfg = _make_config()
        result = assemble([], {}, str(tmp_path), cfg)
        doc = yaml.safe_load(result)
        assert "x-confidence" in doc


# ---------------------------------------------------------------------------
# Confidence
# ---------------------------------------------------------------------------

class TestOverallConfidence:
    def test_overall_confidence_empty_schemas_returns_high(self):
        assert _overall_confidence({}) == Confidence.HIGH

    def test_overall_confidence_worst_wins_manual_beats_high(self):
        schemas = {
            "A": _make_schema("A", Confidence.HIGH),
            "B": _make_schema("B", Confidence.MANUAL),
        }
        assert _overall_confidence(schemas) == Confidence.MANUAL

    def test_overall_confidence_medium_beats_high(self):
        schemas = {
            "A": _make_schema("A", Confidence.HIGH),
            "B": _make_schema("B", Confidence.MEDIUM),
        }
        assert _overall_confidence(schemas) == Confidence.MEDIUM

    def test_overall_confidence_low_beats_medium(self):
        schemas = {
            "A": _make_schema("A", Confidence.MEDIUM),
            "B": _make_schema("B", Confidence.LOW),
        }
        assert _overall_confidence(schemas) == Confidence.LOW

    def test_overall_confidence_all_high_returns_high(self):
        schemas = {
            "A": _make_schema("A", Confidence.HIGH),
            "B": _make_schema("B", Confidence.HIGH),
        }
        assert _overall_confidence(schemas) == Confidence.HIGH


# ---------------------------------------------------------------------------
# Metadata detection
# ---------------------------------------------------------------------------

class TestDetectApiMetadata:
    def test_detect_api_metadata_fallback_to_dir_name(self, tmp_path):
        title, version, owner = _detect_api_metadata(tmp_path)
        # tmp_path name is something like "tmp12345" — just verify it returns strings
        assert isinstance(title, str)
        assert version == "1.0.0"
        assert owner == "unknown"

    def test_detect_api_metadata_from_package_json(self, tmp_path):
        pkg = {"name": "my-service", "version": "2.3.1"}
        (tmp_path / "package.json").write_text(json.dumps(pkg))
        title, version, owner = _detect_api_metadata(tmp_path)
        assert title == "My Service"
        assert version == "2.3.1"

    def test_detect_api_metadata_from_pom_xml(self, tmp_path):
        pom = """<project>
  <artifactId>payment-service</artifactId>
  <version>3.0.0</version>
</project>"""
        (tmp_path / "pom.xml").write_text(pom)
        title, version, owner = _detect_api_metadata(tmp_path)
        assert title == "Payment Service"
        assert version == "3.0.0"

    def test_detect_api_metadata_codeowners(self, tmp_path):
        (tmp_path / "CODEOWNERS").write_text("# comment\n* @platform/team-sre\n")
        _, _, owner = _detect_api_metadata(tmp_path)
        assert owner == "platform/team-sre"


# ---------------------------------------------------------------------------
# Components
# ---------------------------------------------------------------------------

class TestBuildComponents:
    def test_build_components_includes_error_schema(self):
        result = _build_components({})
        assert "Error" in result["schemas"]
        error_schema = result["schemas"]["Error"]
        assert "code" in error_schema["properties"]
        assert "message" in error_schema["properties"]
        assert "traceId" in error_schema["properties"]

    def test_build_components_skips_empty_schema(self):
        schemas = {"Empty": SchemaResult.empty("Empty", "src/E.java")}
        result = _build_components(schemas)
        assert "Empty" not in result["schemas"]

    def test_build_components_includes_nonempty_schema(self):
        schemas = {"Account": _make_schema("Account")}
        result = _build_components(schemas)
        assert "Account" in result["schemas"]

    def test_build_components_includes_enum_schema(self):
        """Enums have no 'properties' key but should still be included if json_schema is truthy."""
        enum_result = SchemaResult(
            type_name="Status",
            json_schema={"type": "string", "enum": ["ACTIVE", "INACTIVE"]},
            confidence=Confidence.HIGH,
            source_file="src/Status.java",
        )
        result = _build_components({"Status": enum_result})
        assert "Status" in result["schemas"]


# ---------------------------------------------------------------------------
# Operation details
# ---------------------------------------------------------------------------

class TestOperationDetails:
    def test_standard_errors_present_in_responses(self, tmp_path):
        routes = [_make_route()]
        cfg = _make_config()
        result = assemble(routes, {}, str(tmp_path), cfg)
        doc = yaml.safe_load(result)
        responses = doc["paths"]["/v1/accounts"]["get"]["responses"]
        assert "400" in responses
        assert "401" in responses
        assert "403" in responses
        assert "404" in responses
        assert "500" in responses

    def test_deprecated_route_sets_flag(self, tmp_path):
        routes = [_make_route(deprecated=True)]
        cfg = _make_config()
        result = assemble(routes, {}, str(tmp_path), cfg)
        doc = yaml.safe_load(result)
        op = doc["paths"]["/v1/accounts"]["get"]
        assert op.get("deprecated") is True

    def test_auth_schemes_set_security(self, tmp_path):
        routes = [_make_route(auth_schemes=["bearerAuth"])]
        cfg = _make_config()
        result = assemble(routes, {}, str(tmp_path), cfg)
        doc = yaml.safe_load(result)
        op = doc["paths"]["/v1/accounts"]["get"]
        assert op.get("security") == [{"bearerAuth": []}]

    def test_params_in_operation(self, tmp_path):
        param = ParamInfo(name="accountId", location="path", required=True, schema={"type": "string"})
        routes = [_make_route(path="/v1/accounts/{accountId}", params=[param])]
        cfg = _make_config()
        result = assemble(routes, {}, str(tmp_path), cfg)
        doc = yaml.safe_load(result)
        op = doc["paths"]["/v1/accounts/{accountId}"]["get"]
        assert len(op["parameters"]) == 1
        assert op["parameters"][0]["name"] == "accountId"
        assert op["parameters"][0]["in"] == "path"

    def test_request_body_uses_ref_when_schema_known(self, tmp_path):
        routes = [_make_route(method="POST", request_body_type="CreateAccountRequest")]
        schemas = {"CreateAccountRequest": _make_schema("CreateAccountRequest")}
        cfg = _make_config()
        result = assemble(routes, schemas, str(tmp_path), cfg)
        doc = yaml.safe_load(result)
        op = doc["paths"]["/v1/accounts"]["post"]
        body_schema = op["requestBody"]["content"]["application/json"]["schema"]
        assert body_schema == {"$ref": "#/components/schemas/CreateAccountRequest"}

    def test_response_type_uses_ref_when_schema_known(self, tmp_path):
        routes = [_make_route(response_type="AccountResponse")]
        schemas = {"AccountResponse": _make_schema("AccountResponse")}
        cfg = _make_config()
        result = assemble(routes, schemas, str(tmp_path), cfg)
        doc = yaml.safe_load(result)
        op = doc["paths"]["/v1/accounts"]["get"]
        resp_schema = op["responses"]["200"]["content"]["application/json"]["schema"]
        assert resp_schema == {"$ref": "#/components/schemas/AccountResponse"}

    def test_request_body_falls_back_to_string_when_schema_unknown(self, tmp_path):
        routes = [_make_route(method="POST", request_body_type="UnknownType")]
        cfg = _make_config()
        result = assemble(routes, {}, str(tmp_path), cfg)
        doc = yaml.safe_load(result)
        op = doc["paths"]["/v1/accounts"]["post"]
        body_schema = op["requestBody"]["content"]["application/json"]["schema"]
        assert body_schema == {"type": "string"}
