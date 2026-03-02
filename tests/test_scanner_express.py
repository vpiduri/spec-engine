"""Tests for spec_engine/scanner/express.py — ExpressScanner unit tests."""

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from spec_engine.scanner.express import ExpressScanner
from spec_engine.config import Config


def _make_scanner(tmp_path: Path) -> ExpressScanner:
    return ExpressScanner(str(tmp_path), Config())


class TestExpressScannerUnit:
    @pytest.fixture
    def scanner(self, tmp_path):
        return _make_scanner(tmp_path)

    def test_node_not_found_returns_empty(self, scanner, tmp_path, monkeypatch):
        js_file = tmp_path / "app.js"
        js_file.write_text("app.get('/items', handler);")
        monkeypatch.setattr(
            subprocess,
            "run",
            lambda *args, **kwargs: (_ for _ in ()).throw(FileNotFoundError()),
        )
        assert scanner._scan_file(js_file) == []

    def test_timeout_returns_empty(self, scanner, tmp_path, monkeypatch):
        js_file = tmp_path / "app.js"
        js_file.write_text("app.get('/items', handler);")
        monkeypatch.setattr(
            subprocess,
            "run",
            lambda *args, **kwargs: (_ for _ in ()).throw(
                subprocess.TimeoutExpired("node", 15)
            ),
        )
        assert scanner._scan_file(js_file) == []

    def test_empty_stdout_returns_empty(self, scanner, tmp_path, monkeypatch):
        js_file = tmp_path / "app.js"
        js_file.write_text("app.get('/items', handler);")
        mock_result = MagicMock()
        mock_result.stdout = ""
        monkeypatch.setattr(subprocess, "run", lambda *a, **kw: mock_result)
        assert scanner._scan_file(js_file) == []

    def test_invalid_json_returns_empty(self, scanner, tmp_path, monkeypatch):
        js_file = tmp_path / "app.js"
        js_file.write_text("app.get('/items', handler);")
        mock_result = MagicMock()
        mock_result.stdout = "not-valid-json"
        monkeypatch.setattr(subprocess, "run", lambda *a, **kw: mock_result)
        assert scanner._scan_file(js_file) == []

    def test_non_list_json_returns_empty(self, scanner, tmp_path, monkeypatch):
        js_file = tmp_path / "app.js"
        js_file.write_text("app.get('/items', handler);")
        mock_result = MagicMock()
        mock_result.stdout = json.dumps({"routes": []})
        monkeypatch.setattr(subprocess, "run", lambda *a, **kw: mock_result)
        assert scanner._scan_file(js_file) == []

    def test_valid_route_parsed(self, scanner, tmp_path, monkeypatch):
        js_file = tmp_path / "app.js"
        js_file.write_text("app.get('/items', handler);")
        mock_result = MagicMock()
        mock_result.stdout = json.dumps([
            {"method": "GET", "path": "/items", "handler": "h", "line": 1}
        ])
        monkeypatch.setattr(subprocess, "run", lambda *a, **kw: mock_result)
        routes = scanner._scan_file(js_file)
        assert len(routes) == 1
        assert routes[0].method == "GET"
        assert routes[0].path == "/items"
        assert routes[0].handler == "h"

    def test_path_without_leading_slash(self, scanner, tmp_path, monkeypatch):
        js_file = tmp_path / "app.js"
        js_file.write_text("")
        mock_result = MagicMock()
        mock_result.stdout = json.dumps([
            {"method": "GET", "path": "v1/items", "handler": "h", "line": 1}
        ])
        monkeypatch.setattr(subprocess, "run", lambda *a, **kw: mock_result)
        routes = scanner._scan_file(js_file)
        assert routes[0].path == "/v1/items"

    def test_path_params_extracted(self, scanner, tmp_path, monkeypatch):
        js_file = tmp_path / "app.js"
        js_file.write_text("")
        mock_result = MagicMock()
        mock_result.stdout = json.dumps([
            {"method": "GET", "path": "/items/{id}", "handler": "getItem", "line": 3}
        ])
        monkeypatch.setattr(subprocess, "run", lambda *a, **kw: mock_result)
        routes = scanner._scan_file(js_file)
        assert len(routes[0].params) == 1
        assert routes[0].params[0].name == "id"
        assert routes[0].params[0].location == "path"

    def test_framework_is_express(self, scanner, tmp_path, monkeypatch):
        js_file = tmp_path / "app.js"
        js_file.write_text("")
        mock_result = MagicMock()
        mock_result.stdout = json.dumps([
            {"method": "POST", "path": "/users", "handler": "createUser", "line": 5}
        ])
        monkeypatch.setattr(subprocess, "run", lambda *a, **kw: mock_result)
        routes = scanner._scan_file(js_file)
        assert routes[0].framework == "express"
