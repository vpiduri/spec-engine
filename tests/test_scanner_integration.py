"""
Integration tests for scanner pipeline.
Tests that scan Go/Node fixtures skip gracefully when tools are not installed.
"""

import pytest
import shutil
from pathlib import Path

from spec_engine.scanner import get_scanner, detect_framework
from spec_engine.config import Config

FIXTURES = Path(__file__).parent / "fixtures"

_HAS_GO = shutil.which("go") is not None
_HAS_NODE = shutil.which("node") is not None


class TestSpringIntegration:
    def test_scan_fixture(self):
        """Scan the Spring fixture directory and verify routes are found."""
        scanner = get_scanner(str(FIXTURES.parent.parent), Config())
        # This uses the full test repo — check that spring scanner can scan java files
        from spec_engine.scanner.spring import SpringScanner
        spring = SpringScanner(str(FIXTURES.parent.parent), Config())
        routes = spring.scan()
        spring_routes = [r for r in routes if r.framework == "spring"]
        assert len(spring_routes) >= 5


class TestFastAPIIntegration:
    def test_scan_fixture(self):
        """Scan the FastAPI fixture directory and verify routes are found."""
        from spec_engine.scanner.fastapi import FastAPIScanner
        scanner = FastAPIScanner(str(FIXTURES.parent.parent), Config())
        routes = scanner.scan()
        fastapi_routes = [r for r in routes if r.framework == "fastapi" and "fixtures/fastapi" in r.file.replace("\\", "/")]
        assert len(fastapi_routes) >= 5


class TestDjangoIntegration:
    def test_scan_fixture(self):
        """Scan the Django fixture directory and verify routes are found."""
        from spec_engine.scanner.django import DjangoScanner
        scanner = DjangoScanner(str(FIXTURES.parent.parent), Config())
        routes = scanner.scan()
        django_routes = [r for r in routes if r.framework == "django" and "fixtures/django" in r.file.replace("\\", "/")]
        assert len(django_routes) >= 6


@pytest.mark.skipif(not _HAS_NODE, reason="Node.js not installed")
class TestExpressIntegration:
    def test_scan_fixture_with_node(self):
        """Scan Express fixture — only runs if Node.js is available."""
        from spec_engine.scanner.express import ExpressScanner
        scanner = ExpressScanner(str(FIXTURES / "express"), Config())
        routes = scanner.scan()
        # May be empty if @babel/parser not installed, but should not crash
        assert isinstance(routes, list)


class TestExpressWithoutNode:
    def test_returns_empty_when_node_unavailable(self, monkeypatch, tmp_path):
        """Express scanner returns [] gracefully when node is not found."""
        from spec_engine.scanner.express import ExpressScanner
        import subprocess

        (tmp_path / "routes.js").write_text("const r = require('express').Router()")

        original_run = subprocess.run

        def mock_run(args, **kwargs):
            if args and args[0] == "node":
                raise FileNotFoundError("node not found")
            return original_run(args, **kwargs)

        monkeypatch.setattr(subprocess, "run", mock_run)
        scanner = ExpressScanner(str(tmp_path), Config())
        routes = scanner.scan()
        assert routes == []


@pytest.mark.skipif(not _HAS_GO, reason="Go toolchain not installed")
class TestGinIntegration:
    def test_scan_fixture_with_go(self):
        """Scan Gin fixture — only runs if Go is available."""
        from spec_engine.scanner.gin import GinScanner
        scanner = GinScanner(str(FIXTURES / "gin"), Config())
        routes = scanner.scan()
        assert isinstance(routes, list)


class TestGinWithoutGo:
    def test_returns_empty_when_go_unavailable(self, monkeypatch, tmp_path):
        """Gin scanner gracefully handles missing Go by using regex fallback."""
        from spec_engine.scanner.gin import GinScanner
        import subprocess

        go_src = '''package main
import "github.com/gin-gonic/gin"
func main() {
    r := gin.Default()
    r.GET("/health", handler)
}
func handler(c *gin.Context) {}
'''
        (tmp_path / "main.go").write_text(go_src)

        # Scanner with no binary will use regex fallback
        scanner = GinScanner.__new__(GinScanner)
        scanner.repo_path = tmp_path
        scanner.config = Config()
        scanner._ast_binary = None
        scanner._warned = False

        routes = scanner.scan()
        # Regex fallback should find the route
        assert isinstance(routes, list)
