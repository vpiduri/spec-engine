"""Tests for spec_engine/models.py — Sections 3.1 through 3.5."""

import json
import pytest

from spec_engine.models import (
    Confidence,
    ParamInfo,
    RouteInfo,
    SchemaResult,
    read_manifest,
    write_manifest,
)


# ---------------------------------------------------------------------------
# Section 3.1 — Confidence enum
# ---------------------------------------------------------------------------

class TestConfidence:
    def test_all_four_values_exist(self):
        assert Confidence.HIGH == "high"
        assert Confidence.MEDIUM == "medium"
        assert Confidence.LOW == "low"
        assert Confidence.MANUAL == "manual"

    def test_is_publishable_true_for_high(self):
        assert Confidence.HIGH.is_publishable() is True

    def test_is_publishable_true_for_medium(self):
        assert Confidence.MEDIUM.is_publishable() is True

    def test_is_publishable_false_for_low(self):
        assert Confidence.LOW.is_publishable() is False

    def test_is_publishable_false_for_manual(self):
        assert Confidence.MANUAL.is_publishable() is False


# ---------------------------------------------------------------------------
# Section 3.2 — ParamInfo dataclass
# ---------------------------------------------------------------------------

class TestParamInfo:
    def test_valid_location_creates_successfully(self):
        for loc in ("path", "query", "header", "cookie"):
            p = ParamInfo(name="x", location=loc)
            assert p.location == loc

    def test_invalid_location_raises_value_error(self):
        with pytest.raises(ValueError, match="location"):
            ParamInfo(name="x", location="body")

    def test_to_openapi_structure(self):
        p = ParamInfo(
            name="accountId",
            location="path",
            required=True,
            schema={"type": "string"},
            description="The account identifier",
        )
        result = p.to_openapi()
        assert result == {
            "name": "accountId",
            "in": "path",
            "required": True,
            "schema": {"type": "string"},
            "description": "The account identifier",
        }

    def test_to_openapi_empty_description_omits_key(self):
        p = ParamInfo(name="page", location="query", description="")
        result = p.to_openapi()
        assert "description" not in result

    def test_to_dict_uses_location_key_not_in(self):
        p = ParamInfo(name="x", location="header")
        d = p.to_dict()
        assert "location" in d
        assert "in" not in d

    def test_to_dict_round_trip_via_param_info(self):
        p = ParamInfo(name="q", location="query", required=False, schema={"type": "string"})
        reconstructed = ParamInfo(**p.to_dict())
        assert reconstructed.name == p.name
        assert reconstructed.location == p.location
        assert reconstructed.required == p.required


# ---------------------------------------------------------------------------
# Section 3.3 — RouteInfo dataclass
# ---------------------------------------------------------------------------

def _make_route(**kwargs) -> RouteInfo:
    defaults = dict(
        method="GET",
        path="/v1/accounts",
        handler="AccountController.list",
        file="src/AccountController.java",
        line=10,
        framework="spring",
    )
    defaults.update(kwargs)
    return RouteInfo(**defaults)


class TestRouteInfo:
    def test_method_normalised_to_uppercase(self):
        r = _make_route(method="post")
        assert r.method == "POST"

    def test_lowercase_method_normalised(self):
        r = _make_route(method="delete")
        assert r.method == "DELETE"

    def test_path_without_leading_slash_raises(self):
        with pytest.raises(ValueError, match="path"):
            _make_route(path="v1/accounts")

    def test_line_zero_raises(self):
        with pytest.raises(ValueError, match="line"):
            _make_route(line=0)

    def test_line_negative_raises(self):
        with pytest.raises(ValueError, match="line"):
            _make_route(line=-1)

    # operation_id — five distinct path patterns
    def test_operation_id_post_collection(self):
        r = _make_route(method="POST", path="/v1/accounts")
        assert r.operation_id == "createAccounts"

    def test_operation_id_get_collection(self):
        r = _make_route(method="GET", path="/v1/accounts")
        assert r.operation_id == "getAccounts"

    def test_operation_id_get_with_path_param(self):
        r = _make_route(method="GET", path="/v1/accounts/{id}")
        assert r.operation_id == "getAccountsById"

    def test_operation_id_delete_with_path_param(self):
        r = _make_route(method="DELETE", path="/v1/accounts/{id}")
        assert r.operation_id == "deleteAccountsById"

    def test_operation_id_put_nested_resource(self):
        r = _make_route(method="PUT", path="/v1/users/{userId}/profile")
        assert r.operation_id == "updateUsersByUserIdProfile"

    def test_operation_id_hyphenated_segment(self):
        r = _make_route(method="GET", path="/api-keys")
        assert r.operation_id == "getApiKeys"

    def test_operation_id_patch_nested(self):
        r = _make_route(method="PATCH", path="/v1/payments/{paymentId}/status")
        assert r.operation_id == "patchPaymentsByPaymentIdStatus"

    def test_to_dict_is_json_serialisable(self):
        r = _make_route(
            params=[ParamInfo(name="X-Request-ID", location="header", required=False)],
            request_body_type="CreateAccountRequest",
            response_type="AccountResponse",
            auth_schemes=["oauth2"],
            tags=["accounts"],
            summary="Create an account",
        )
        # Must not raise
        serialised = json.dumps(r.to_dict())
        assert isinstance(serialised, str)

    def test_to_dict_contains_expected_keys(self):
        r = _make_route()
        d = r.to_dict()
        for key in ("method", "path", "handler", "file", "line", "framework",
                    "params", "request_body_type", "response_type",
                    "auth_schemes", "tags", "summary", "deprecated"):
            assert key in d, f"Missing key: {key}"

    def test_to_dict_does_not_include_operation_id(self):
        # operation_id is computed — should NOT be stored in manifest
        r = _make_route()
        assert "operation_id" not in r.to_dict()


# ---------------------------------------------------------------------------
# Section 3.4 — SchemaResult dataclass
# ---------------------------------------------------------------------------

class TestSchemaResult:
    def test_is_empty_for_empty_dict(self):
        sr = SchemaResult(
            type_name="Foo", json_schema={},
            confidence=Confidence.MANUAL, source_file="Foo.java",
        )
        assert sr.is_empty is True

    def test_is_empty_for_dict_without_properties(self):
        sr = SchemaResult(
            type_name="Foo", json_schema={"type": "object"},
            confidence=Confidence.MEDIUM, source_file="Foo.java",
        )
        assert sr.is_empty is True

    def test_is_empty_false_when_properties_present(self):
        sr = SchemaResult(
            type_name="Foo",
            json_schema={"type": "object", "properties": {"id": {"type": "string"}}},
            confidence=Confidence.HIGH, source_file="Foo.java",
        )
        assert sr.is_empty is False

    def test_ref_count(self):
        sr = SchemaResult(
            type_name="Foo", json_schema={},
            confidence=Confidence.LOW, source_file="Foo.java",
            refs=["Bar", "Baz"],
        )
        assert sr.ref_count == 2

    def test_ref_count_empty(self):
        sr = SchemaResult(
            type_name="Foo", json_schema={},
            confidence=Confidence.HIGH, source_file="Foo.java",
        )
        assert sr.ref_count == 0

    def test_to_component_schema_includes_x_fields(self):
        sr = SchemaResult(
            type_name="AccountResponse",
            json_schema={"type": "object", "properties": {"id": {"type": "string"}}},
            confidence=Confidence.HIGH,
            source_file="src/AccountResponse.java",
        )
        result = sr.to_component_schema()
        assert result["x-confidence"] == "high"
        assert result["x-source-file"] == "src/AccountResponse.java"

    def test_to_component_schema_preserves_original_fields(self):
        sr = SchemaResult(
            type_name="T",
            json_schema={"type": "object", "properties": {}},
            confidence=Confidence.MEDIUM,
            source_file="T.py",
        )
        result = sr.to_component_schema()
        assert result["type"] == "object"

    def test_to_component_schema_does_not_mutate_original(self):
        original_schema = {"type": "object", "properties": {}}
        sr = SchemaResult(
            type_name="T", json_schema=original_schema,
            confidence=Confidence.HIGH, source_file="T.py",
        )
        sr.to_component_schema()
        assert "x-confidence" not in original_schema

    def test_empty_classmethod_creates_manual_confidence(self):
        sr = SchemaResult.empty("UnknownType", "UnknownFile.java")
        assert sr.type_name == "UnknownType"
        assert sr.source_file == "UnknownFile.java"
        assert sr.confidence == Confidence.MANUAL
        assert sr.json_schema == {}
        assert sr.is_empty is True


# ---------------------------------------------------------------------------
# Section 3.5 — Route manifest writer & reader
# ---------------------------------------------------------------------------

def _make_full_route() -> RouteInfo:
    return RouteInfo(
        method="POST",
        path="/v1/accounts",
        handler="AccountController.createAccount",
        file="src/AccountController.java",
        line=42,
        framework="spring",
        params=[
            ParamInfo(name="X-Request-ID", location="header", required=False),
            ParamInfo(name="accountId", location="path", required=True,
                      schema={"type": "string"}),
        ],
        request_body_type="CreateAccountRequest",
        response_type="AccountResponse",
        auth_schemes=["oauth2"],
        tags=["accounts"],
        summary="Create a new account",
        deprecated=False,
    )


class TestManifest:
    def test_write_manifest_creates_file(self, tmp_path):
        route = _make_full_route()
        out = str(tmp_path / "manifest.json")
        write_manifest([route], repo="my-repo", framework="spring", output_path=out)
        assert (tmp_path / "manifest.json").exists()

    def test_write_manifest_creates_parent_dirs(self, tmp_path):
        route = _make_full_route()
        out = str(tmp_path / "deep" / "nested" / "manifest.json")
        write_manifest([route], repo="my-repo", framework="spring", output_path=out)
        assert (tmp_path / "deep" / "nested" / "manifest.json").exists()

    def test_write_manifest_correct_structure(self, tmp_path):
        route = _make_full_route()
        out = str(tmp_path / "manifest.json")
        write_manifest([route], repo="my-repo", framework="spring", output_path=out)

        data = json.loads((tmp_path / "manifest.json").read_text())
        assert "generated_at" in data
        assert data["repo"] == "my-repo"
        assert data["framework"] == "spring"
        assert data["route_count"] == 1
        assert len(data["routes"]) == 1

    def test_round_trip_preserves_route(self, tmp_path):
        route = _make_full_route()
        out = str(tmp_path / "manifest.json")
        write_manifest([route], repo="repo", framework="spring", output_path=out)
        routes = read_manifest(out)

        assert len(routes) == 1
        r = routes[0]
        assert r.method == route.method
        assert r.path == route.path
        assert r.handler == route.handler
        assert r.file == route.file
        assert r.line == route.line
        assert r.framework == route.framework
        assert r.request_body_type == route.request_body_type
        assert r.response_type == route.response_type
        assert r.auth_schemes == route.auth_schemes
        assert r.tags == route.tags
        assert r.summary == route.summary
        assert r.deprecated == route.deprecated

    def test_round_trip_preserves_params(self, tmp_path):
        route = _make_full_route()
        out = str(tmp_path / "manifest.json")
        write_manifest([route], repo="repo", framework="spring", output_path=out)
        routes = read_manifest(out)

        assert len(routes[0].params) == 2
        assert routes[0].params[0].name == "X-Request-ID"
        assert routes[0].params[0].location == "header"
        assert routes[0].params[0].required is False

    def test_read_manifest_raises_file_not_found(self, tmp_path):
        with pytest.raises(FileNotFoundError, match="manifest"):
            read_manifest(str(tmp_path / "nonexistent.json"))

    def test_read_manifest_raises_value_error_on_missing_routes_key(self, tmp_path):
        bad_file = tmp_path / "bad.json"
        bad_file.write_text(json.dumps({"repo": "x", "framework": "spring"}))
        with pytest.raises(ValueError, match="routes"):
            read_manifest(str(bad_file))

    def test_write_read_multiple_routes(self, tmp_path):
        routes = [
            _make_full_route(),
            RouteInfo(
                method="GET", path="/v1/accounts/{id}",
                handler="AccountController.get", file="src/AC.java",
                line=60, framework="spring",
            ),
        ]
        out = str(tmp_path / "manifest.json")
        write_manifest(routes, repo="r", framework="spring", output_path=out)
        loaded = read_manifest(out)
        assert len(loaded) == 2
        assert loaded[1].path == "/v1/accounts/{id}"
