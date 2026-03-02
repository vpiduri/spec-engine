"""Tests for spec_engine/scanner/fastapi.py — FastAPIScanner."""

import pytest
from pathlib import Path

from spec_engine.scanner.fastapi import FastAPIScanner
from spec_engine.config import Config

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "fastapi"


def make_scanner(path: Path) -> FastAPIScanner:
    return FastAPIScanner(str(path), Config())


class TestFastAPIScanner:
    @pytest.fixture
    def routes(self):
        scanner = make_scanner(FIXTURE_DIR.parent.parent)
        all_routes = scanner.scan()
        # Filter to routes from our fixture accounts.py
        return [r for r in all_routes if "accounts.py" in r.file and "fixtures" in r.file]

    def test_finds_five_routes(self, routes):
        assert len(routes) == 5

    def test_get_list_route(self, routes):
        route = next(r for r in routes if r.method == "GET" and "account_id" not in r.path)
        assert route.path.startswith("/v1/accounts")
        assert route.framework == "fastapi"

    def test_get_by_id_route(self, routes):
        route = next(r for r in routes if r.method == "GET" and "{account_id}" in r.path)
        assert route.path == "/v1/accounts/{account_id}"

    def test_post_route_has_request_body(self, routes):
        route = next(r for r in routes if r.method == "POST")
        assert route.request_body_type == "CreateAccountRequest"

    def test_post_route_handler(self, routes):
        route = next(r for r in routes if r.method == "POST")
        assert route.handler == "create_account"

    def test_put_route_has_path_param(self, routes):
        route = next(r for r in routes if r.method == "PUT")
        path_params = [p for p in route.params if p.location == "path"]
        assert len(path_params) >= 1

    def test_delete_route(self, routes):
        route = next(r for r in routes if r.method == "DELETE")
        assert "{account_id}" in route.path

    def test_get_list_has_query_params(self, routes):
        route = next(r for r in routes if r.method == "GET" and "{account_id}" not in r.path)
        query_params = [p for p in route.params if p.location == "query"]
        assert len(query_params) >= 1
        param_names = [p.name for p in query_params]
        assert "page" in param_names or "size" in param_names

    def test_framework_is_fastapi(self, routes):
        for r in routes:
            assert r.framework == "fastapi"


class TestFastAPIModelDetection:
    def test_model_class_detected_as_request_body(self, tmp_path):
        source = '''
from pydantic import BaseModel
from fastapi import APIRouter

class CreateRequest(BaseModel):
    name: str

router = APIRouter(prefix="/items")

@router.post("/")
def create(request: CreateRequest):
    pass
'''
        (tmp_path / "routes.py").write_text(source)
        scanner = FastAPIScanner(str(tmp_path), Config())
        routes = scanner.scan()
        assert len(routes) == 1
        assert routes[0].request_body_type == "CreateRequest"

    def test_path_param_extracted(self, tmp_path):
        source = '''
from fastapi import APIRouter

router = APIRouter(prefix="/v1")

@router.get("/{item_id}")
def get_item(item_id: str):
    pass
'''
        (tmp_path / "routes.py").write_text(source)
        scanner = FastAPIScanner(str(tmp_path), Config())
        routes = scanner.scan()
        assert len(routes) == 1
        path_params = [p for p in routes[0].params if p.location == "path"]
        assert len(path_params) == 1
        assert path_params[0].name == "item_id"

    def test_syntax_error_returns_empty(self, tmp_path):
        (tmp_path / "bad.py").write_text("def (broken):")
        scanner = FastAPIScanner(str(tmp_path), Config())
        routes = scanner.scan()
        assert routes == []

    def test_non_router_decorator_skipped(self, tmp_path):
        source = '''
from fastapi import APIRouter

router = APIRouter(prefix="/v1")

@some_decorator("/path")
def handler():
    pass
'''
        (tmp_path / "routes.py").write_text(source)
        scanner = FastAPIScanner(str(tmp_path), Config())
        routes = scanner.scan()
        assert routes == []
