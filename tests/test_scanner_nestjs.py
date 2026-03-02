"""Tests for spec_engine/scanner/nestjs.py — NestJSScanner (regex path)."""

import subprocess
from pathlib import Path

import pytest

from spec_engine.scanner.nestjs import NestJSScanner
from spec_engine.config import Config


def _raise_fnf(*args, **kwargs):
    raise FileNotFoundError("node not found")


@pytest.fixture
def scanner(tmp_path, monkeypatch):
    """NestJSScanner with Node.js unavailable → forces regex path."""
    monkeypatch.setattr(subprocess, "run", _raise_fnf)
    return NestJSScanner(str(tmp_path), Config())


CONTROLLER_TEMPLATE = """\
import {{ Controller, Get, Post }} from '@nestjs/common';

@Controller('{prefix}')
export class {class_name}Controller {{
{methods}
}}
"""


def _write_controller(
    tmp_path: Path,
    prefix: str,
    class_name: str,
    methods: str,
    filename: str = "app.controller.ts",
) -> Path:
    f = tmp_path / filename
    f.write_text(CONTROLLER_TEMPLATE.format(
        prefix=prefix,
        class_name=class_name,
        methods=methods,
    ))
    return f


class TestNestJSScannerRegex:
    def test_finds_get_route(self, scanner, tmp_path):
        _write_controller(
            tmp_path, "items", "Item",
            "  @Get()\n  findAll() { return []; }\n"
        )
        routes = scanner.scan()
        get_routes = [r for r in routes if r.method == "GET"]
        assert len(get_routes) >= 1

    def test_finds_post_route(self, scanner, tmp_path):
        _write_controller(
            tmp_path, "items", "Item",
            "  @Post()\n  create() { return {}; }\n"
        )
        routes = scanner.scan()
        post_routes = [r for r in routes if r.method == "POST"]
        assert len(post_routes) >= 1

    def test_controller_prefix_prepended(self, scanner, tmp_path):
        _write_controller(
            tmp_path, "orders", "Order",
            "  @Get()\n  findAll() { return []; }\n"
        )
        routes = scanner.scan()
        get_routes = [r for r in routes if r.method == "GET"]
        assert any(r.path.startswith("/orders") for r in get_routes)

    def test_colon_param_converted(self, scanner, tmp_path):
        _write_controller(
            tmp_path, "items", "Item",
            "  @Get(':id')\n  findOne() { return {}; }\n"
        )
        routes = scanner.scan()
        get_routes = [r for r in routes if r.method == "GET"]
        assert any("{id}" in r.path for r in get_routes)

    def test_framework_is_nestjs(self, scanner, tmp_path):
        _write_controller(
            tmp_path, "users", "User",
            "  @Get()\n  findAll() { return []; }\n"
        )
        routes = scanner.scan()
        assert all(r.framework == "nestjs" for r in routes)

    def test_no_controller_no_routes(self, scanner, tmp_path):
        f = tmp_path / "no_controller.ts"
        f.write_text("export function helper() { return 1; }")
        routes = scanner.scan()
        assert routes == []

    def test_empty_file_no_routes(self, scanner, tmp_path):
        f = tmp_path / "empty.ts"
        f.write_text("")
        routes = scanner.scan()
        assert routes == []

    def test_handler_name_extracted(self, scanner, tmp_path):
        _write_controller(
            tmp_path, "products", "Product",
            "  @Get()\n  getAllProducts() { return []; }\n"
        )
        routes = scanner.scan()
        get_routes = [r for r in routes if r.method == "GET"]
        assert any(r.handler == "getAllProducts" for r in get_routes)
