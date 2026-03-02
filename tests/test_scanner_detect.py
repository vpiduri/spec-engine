"""Tests for spec_engine/scanner/__init__.py — detect_framework() and get_scanner()."""

import pytest
from pathlib import Path

from spec_engine.scanner import detect_framework, get_scanner
from spec_engine.scanner.spring import SpringScanner
from spec_engine.scanner.fastapi import FastAPIScanner
from spec_engine.scanner.django import DjangoScanner
from spec_engine.scanner.express import ExpressScanner
from spec_engine.scanner.gin import GinScanner
from spec_engine.config import Config


class TestDetectFramework:
    def test_detects_gin_from_go_mod(self, tmp_path):
        (tmp_path / "go.mod").write_text('module example.com/app\nrequire github.com/gin-gonic/gin v1.9.0')
        assert detect_framework(str(tmp_path)) == "gin"

    def test_detects_echo_from_go_mod(self, tmp_path):
        (tmp_path / "go.mod").write_text('module example.com/app\nrequire github.com/labstack/echo/v4 v4.11.0')
        assert detect_framework(str(tmp_path)) == "echo"

    def test_detects_spring_from_pom_xml(self, tmp_path):
        (tmp_path / "pom.xml").write_text('<project><artifactId>demo</artifactId></project>')
        assert detect_framework(str(tmp_path)) == "spring"

    def test_detects_spring_from_build_gradle(self, tmp_path):
        (tmp_path / "build.gradle").write_text("apply plugin: 'org.springframework.boot'")
        assert detect_framework(str(tmp_path)) == "spring"

    def test_detects_fastapi_from_requirements(self, tmp_path):
        (tmp_path / "requirements.txt").write_text("fastapi>=0.100.0\nuvicorn")
        assert detect_framework(str(tmp_path)) == "fastapi"

    def test_detects_django_from_requirements(self, tmp_path):
        (tmp_path / "requirements.txt").write_text("django>=4.0\ndjangorestframework")
        assert detect_framework(str(tmp_path)) == "django"

    def test_detects_express_from_package_json(self, tmp_path):
        (tmp_path / "package.json").write_text('{"dependencies": {"express": "^4.18.0"}}')
        assert detect_framework(str(tmp_path)) == "express"

    def test_detects_nestjs_from_package_json(self, tmp_path):
        (tmp_path / "package.json").write_text('{"dependencies": {"@nestjs/core": "^10.0.0"}}')
        assert detect_framework(str(tmp_path)) == "nestjs"

    def test_returns_unknown_when_no_markers(self, tmp_path):
        assert detect_framework(str(tmp_path)) == "unknown"

    def test_go_takes_priority_over_python(self, tmp_path):
        (tmp_path / "go.mod").write_text("module example.com\nrequire github.com/gin-gonic/gin v1.9.0")
        (tmp_path / "requirements.txt").write_text("fastapi")
        assert detect_framework(str(tmp_path)) == "gin"

    def test_spring_takes_priority_over_python(self, tmp_path):
        (tmp_path / "pom.xml").write_text("<project/>")
        (tmp_path / "requirements.txt").write_text("fastapi")
        assert detect_framework(str(tmp_path)) == "spring"


class TestGetScanner:
    def test_returns_spring_scanner(self, tmp_path):
        (tmp_path / "pom.xml").write_text("<project/>")
        scanner = get_scanner(str(tmp_path), Config())
        assert isinstance(scanner, SpringScanner)

    def test_returns_fastapi_scanner(self, tmp_path):
        (tmp_path / "requirements.txt").write_text("fastapi")
        scanner = get_scanner(str(tmp_path), Config())
        assert isinstance(scanner, FastAPIScanner)

    def test_returns_django_scanner(self, tmp_path):
        (tmp_path / "requirements.txt").write_text("django\ndjangorestframework")
        scanner = get_scanner(str(tmp_path), Config())
        assert isinstance(scanner, DjangoScanner)

    def test_returns_express_scanner(self, tmp_path):
        (tmp_path / "package.json").write_text('{"dependencies": {"express": "^4"}}')
        scanner = get_scanner(str(tmp_path), Config())
        assert isinstance(scanner, ExpressScanner)

    def test_returns_gin_scanner(self, tmp_path):
        (tmp_path / "go.mod").write_text("module example.com\nrequire github.com/gin-gonic/gin v1.9.0")
        scanner = get_scanner(str(tmp_path), Config())
        assert isinstance(scanner, GinScanner)

    def test_config_framework_overrides_detection(self, tmp_path):
        """If config.framework is set, use it instead of auto-detecting."""
        # Even without go.mod, if config says gin, get GinScanner
        config = Config()
        config.framework = "gin"  # type: ignore[attr-defined]
        scanner = get_scanner(str(tmp_path), config)
        assert isinstance(scanner, GinScanner)

    def test_raises_for_unknown_framework(self, tmp_path):
        config = Config()
        config.framework = "rails"  # type: ignore[attr-defined]
        with pytest.raises(ValueError, match="Unknown or unsupported"):
            get_scanner(str(tmp_path), config)
