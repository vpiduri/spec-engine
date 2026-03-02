"""Tests for spec_engine/scanner/spring.py — SpringScanner."""

import pytest
from pathlib import Path

from spec_engine.scanner.spring import SpringScanner, _join_path, _camel_to_title
from spec_engine.config import Config

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "spring"


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def make_scanner(path: Path) -> SpringScanner:
    return SpringScanner(str(path), Config())


# ---------------------------------------------------------------------------
# Unit tests for helpers
# ---------------------------------------------------------------------------

class TestHelpers:
    def test_join_path_no_double_slash(self):
        assert _join_path("/v1/accounts", "/sub") == "/v1/accounts/sub"

    def test_join_path_adds_leading_slash(self):
        assert _join_path("v1/accounts", "sub").startswith("/")

    def test_join_path_empty_suffix(self):
        assert _join_path("/v1/accounts", "") == "/v1/accounts"

    def test_join_path_empty_prefix(self):
        assert _join_path("", "/sub") == "/sub"

    def test_join_path_both_empty(self):
        assert _join_path("", "") == "/"

    def test_camel_to_title_single_word(self):
        assert _camel_to_title("list") == "List"

    def test_camel_to_title_camel_case(self):
        assert _camel_to_title("listAccounts") == "List Accounts"

    def test_camel_to_title_multi_word(self):
        assert _camel_to_title("createAccount") == "Create Account"


# ---------------------------------------------------------------------------
# Integration tests using fixture file
# ---------------------------------------------------------------------------

class TestSpringScanner:
    @pytest.fixture
    def routes(self):
        scanner = make_scanner(FIXTURE_DIR.parent.parent)
        all_routes = scanner.scan()
        # Filter to only routes from our fixture
        return [r for r in all_routes if "AccountController" in r.file]

    def test_finds_five_routes(self, routes):
        assert len(routes) == 5

    def test_get_list_route(self, routes):
        route = next(r for r in routes if r.method == "GET" and r.path == "/v1/accounts")
        assert route.framework == "spring"
        assert "AccountController" in route.handler

    def test_get_by_id_route(self, routes):
        route = next(r for r in routes if r.method == "GET" and "{accountId}" in r.path)
        assert route.path == "/v1/accounts/{accountId}"

    def test_post_route_has_request_body(self, routes):
        route = next(r for r in routes if r.method == "POST")
        assert route.request_body_type == "CreateAccountRequest"

    def test_post_route_has_auth(self, routes):
        route = next(r for r in routes if r.method == "POST")
        assert "oauth2" in route.auth_schemes

    def test_post_route_response_type(self, routes):
        route = next(r for r in routes if r.method == "POST")
        assert route.response_type == "AccountResponse"

    def test_put_route_has_path_param(self, routes):
        route = next(r for r in routes if r.method == "PUT")
        path_params = [p for p in route.params if p.location == "path"]
        assert len(path_params) == 1
        assert path_params[0].name == "accountId"

    def test_delete_route(self, routes):
        route = next(r for r in routes if r.method == "DELETE")
        assert "/accountId" in route.path or "{accountId}" in route.path

    def test_tags_derived_from_class_name(self, routes):
        for r in routes:
            assert "Account" in r.tags

    def test_summary_is_title_case(self, routes):
        for r in routes:
            assert r.summary  # non-empty
            assert r.summary[0].isupper()

    def test_get_list_has_query_param(self, routes):
        route = next(r for r in routes if r.method == "GET" and r.path == "/v1/accounts")
        query_params = [p for p in route.params if p.location == "query"]
        assert len(query_params) >= 1
        assert query_params[0].name == "status"
        assert query_params[0].required is False

    def test_parse_error_returns_empty_list(self, tmp_path):
        bad_file = tmp_path / "Bad.java"
        bad_file.write_text("this is not java {{{")
        scanner = SpringScanner(str(tmp_path), Config())
        routes = scanner.scan()
        assert routes == []


class TestSpringGetMapping:
    """Targeted tests for annotation value extraction."""

    def test_scan_get_mapping_with_path_param(self, tmp_path):
        source = '''
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api")
public class TestController {
    @GetMapping("/{id}")
    public String get(@PathVariable String id) { return id; }
}
'''
        (tmp_path / "TestController.java").write_text(source)
        scanner = SpringScanner(str(tmp_path), Config())
        routes = scanner.scan()
        assert len(routes) == 1
        r = routes[0]
        assert r.method == "GET"
        assert r.path == "/api/{id}"
        assert len(r.params) == 1
        assert r.params[0].location == "path"

    def test_scan_post_with_request_body(self, tmp_path):
        source = '''
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/items")
public class ItemController {
    @PostMapping
    public ItemResponse create(@RequestBody ItemRequest req) { return null; }
}
'''
        (tmp_path / "ItemController.java").write_text(source)
        scanner = SpringScanner(str(tmp_path), Config())
        routes = scanner.scan()
        assert len(routes) == 1
        assert routes[0].request_body_type == "ItemRequest"

    def test_non_controller_class_is_skipped(self, tmp_path):
        source = '''
public class NotAController {
    @GetMapping("/path")
    public void method() {}
}
'''
        (tmp_path / "NotAController.java").write_text(source)
        scanner = SpringScanner(str(tmp_path), Config())
        routes = scanner.scan()
        assert routes == []
