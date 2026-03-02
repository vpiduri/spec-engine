"""
End-to-end pipeline integration tests.

Covers the full scan → infer → assemble → validate → CLI flow using the
existing test fixtures.  External tools (redocly, spectral) are patched out
so the suite passes on a dev machine without those tools installed.
"""

from __future__ import annotations

import subprocess
import yaml
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from spec_engine.assembler import assemble
from spec_engine.cli import cli
from spec_engine.config import Config
from spec_engine.inferrer import run_inference
from spec_engine.models import RouteInfo, SchemaResult, Confidence
from spec_engine.validator import validate

FIXTURES = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_config(**kwargs) -> Config:
    defaults = {"gateway": "test-gw", "owner": "test-owner", "strict_mode": False}
    defaults.update(kwargs)
    return Config(**defaults)


def _make_route(**kwargs) -> RouteInfo:
    defaults = {
        "method": "GET",
        "path": "/v1/items",
        "handler": "ItemController.list",
        "file": "src/ItemController.java",
        "line": 5,
        "framework": "spring",
    }
    defaults.update(kwargs)
    return RouteInfo(**defaults)


def _make_schema(type_name: str = "Item") -> SchemaResult:
    return SchemaResult(
        type_name=type_name,
        json_schema={"type": "object", "properties": {"id": {"type": "string"}}},
        confidence=Confidence.HIGH,
        source_file="src/Item.java",
    )


# ---------------------------------------------------------------------------
# Spring pipeline
# ---------------------------------------------------------------------------

class TestSpringPipeline:
    def test_produces_valid_yaml(self):
        from spec_engine.scanner.spring import SpringScanner

        cfg = _make_config()
        scanner = SpringScanner(str(FIXTURES.parent.parent), cfg)
        all_routes = scanner.scan()
        routes = [r for r in all_routes if "AccountController" in r.file]
        assert routes, "Spring fixture must produce routes"

        schemas = run_inference(routes, str(FIXTURES / "java"), "spring", cfg)
        yaml_str = assemble(routes, schemas, str(FIXTURES.parent.parent), cfg)

        doc = yaml.safe_load(yaml_str)
        assert doc["openapi"] == "3.1.0"
        assert "paths" in doc
        assert "components" in doc

    def test_paths_contain_accounts_prefix(self):
        from spec_engine.scanner.spring import SpringScanner

        cfg = _make_config()
        scanner = SpringScanner(str(FIXTURES.parent.parent), cfg)
        routes = [r for r in scanner.scan() if "AccountController" in r.file]
        schemas = run_inference(routes, str(FIXTURES / "java"), "spring", cfg)
        yaml_str = assemble(routes, schemas, str(FIXTURES.parent.parent), cfg)

        doc = yaml.safe_load(yaml_str)
        assert any("/v1/accounts" in p for p in doc["paths"])

    def test_info_block_has_x_fields(self):
        from spec_engine.scanner.spring import SpringScanner

        cfg = _make_config()
        scanner = SpringScanner(str(FIXTURES.parent.parent), cfg)
        routes = [r for r in scanner.scan() if "AccountController" in r.file]
        schemas = run_inference(routes, str(FIXTURES / "java"), "spring", cfg)
        yaml_str = assemble(routes, schemas, str(FIXTURES.parent.parent), cfg)

        doc = yaml.safe_load(yaml_str)
        info = doc["info"]
        assert "x-owner" in info
        assert "x-gateway" in info
        assert "x-lifecycle" in info


# ---------------------------------------------------------------------------
# FastAPI pipeline
# ---------------------------------------------------------------------------

class TestFastAPIPipeline:
    def test_produces_valid_yaml(self):
        from spec_engine.scanner.fastapi import FastAPIScanner

        cfg = _make_config()
        scanner = FastAPIScanner(str(FIXTURES.parent.parent), cfg)
        all_routes = scanner.scan()
        routes = [
            r for r in all_routes
            if "fixtures/fastapi" in r.file.replace("\\", "/")
        ]
        assert routes, "FastAPI fixture must produce routes"

        schemas = run_inference(routes, str(FIXTURES / "fastapi"), "fastapi", cfg)
        yaml_str = assemble(routes, schemas, str(FIXTURES.parent.parent), cfg)

        doc = yaml.safe_load(yaml_str)
        assert doc["openapi"] == "3.1.0"
        assert "paths" in doc

    def test_components_includes_known_types(self):
        from spec_engine.scanner.fastapi import FastAPIScanner

        cfg = _make_config()
        scanner = FastAPIScanner(str(FIXTURES.parent.parent), cfg)
        routes = [
            r for r in scanner.scan()
            if "fixtures/fastapi" in r.file.replace("\\", "/")
        ]
        schemas = run_inference(routes, str(FIXTURES / "fastapi"), "fastapi", cfg)
        yaml_str = assemble(routes, schemas, str(FIXTURES.parent.parent), cfg)

        doc = yaml.safe_load(yaml_str)
        component_schemas = doc.get("components", {}).get("schemas", {})
        # At minimum the Error schema is always present
        assert "Error" in component_schemas


# ---------------------------------------------------------------------------
# Django pipeline
# ---------------------------------------------------------------------------

class TestDjangoPipeline:
    def test_produces_valid_yaml(self):
        from spec_engine.scanner.django import DjangoScanner

        cfg = _make_config()
        scanner = DjangoScanner(str(FIXTURES.parent.parent), cfg)
        all_routes = scanner.scan()
        routes = [
            r for r in all_routes
            if "fixtures/django" in r.file.replace("\\", "/")
        ]
        assert routes, "Django fixture must produce routes"

        schemas = run_inference(routes, str(FIXTURES / "django"), "django", cfg)
        yaml_str = assemble(routes, schemas, str(FIXTURES.parent.parent), cfg)

        doc = yaml.safe_load(yaml_str)
        assert doc["openapi"] == "3.1.0"
        assert "paths" in doc
        assert "components" in doc


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

class TestPipelineValidation:
    def test_validate_passes_on_assembled_spec(self, tmp_path):
        from spec_engine.scanner.spring import SpringScanner

        cfg = _make_config()
        scanner = SpringScanner(str(FIXTURES.parent.parent), cfg)
        routes = [r for r in scanner.scan() if "AccountController" in r.file]
        schemas = run_inference(routes, str(FIXTURES / "java"), "spring", cfg)
        yaml_str = assemble(routes, schemas, str(FIXTURES.parent.parent), cfg)

        spec_path = str(tmp_path / "test.yaml")
        Path(spec_path).write_text(yaml_str)

        # Patch subprocess so redocly/spectral are treated as "not installed"
        def _fake_run(args, **kwargs):
            raise FileNotFoundError("tool not installed")

        with patch("subprocess.run", side_effect=_fake_run):
            result = validate(spec_path, cfg)

        assert result.passed, f"Unexpected errors: {result.errors}"

    def test_validate_fails_when_x_fields_missing(self, tmp_path):
        cfg = _make_config(required_x_fields=["x-custom-field"])
        spec = {
            "openapi": "3.1.0",
            "info": {"title": "Test API", "version": "1.0.0"},
            "paths": {},
        }
        spec_path = str(tmp_path / "test.yaml")
        Path(spec_path).write_text(yaml.dump(spec))

        def _fake_run(args, **kwargs):
            raise FileNotFoundError("tool not installed")

        with patch("subprocess.run", side_effect=_fake_run):
            result = validate(spec_path, cfg)

        assert not result.passed
        assert any("x-custom-field" in e for e in result.errors)

    def test_validate_reports_all_errors_when_strict_mode_false(self, tmp_path):
        cfg = _make_config(
            strict_mode=False,
            required_x_fields=["x-field-one", "x-field-two"],
        )
        spec = {
            "openapi": "3.1.0",
            "info": {"title": "No x-fields", "version": "0.0.1"},
            "paths": {},
        }
        spec_path = str(tmp_path / "spec.yaml")
        Path(spec_path).write_text(yaml.dump(spec))

        def _fake_run(args, **kwargs):
            raise FileNotFoundError("tool not installed")

        with patch("subprocess.run", side_effect=_fake_run):
            result = validate(spec_path, cfg)

        assert len(result.errors) == 2


# ---------------------------------------------------------------------------
# CLI end-to-end
# ---------------------------------------------------------------------------

class TestPipelineCLI:
    def test_generate_command_end_to_end(self, tmp_path, monkeypatch):
        """Full generate pipeline on Spring fixture; external tools stubbed out."""
        # Patch subprocess so redocly/spectral are treated as not installed
        original_run = subprocess.run

        def _fake_subprocess(args, **kwargs):
            if args and args[0] in ("redocly", "spectral"):
                raise FileNotFoundError("tool not installed")
            return original_run(args, **kwargs)

        monkeypatch.setattr(subprocess, "run", _fake_subprocess)

        out_file = str(tmp_path / "openapi.yaml")
        runner = CliRunner()
        result = runner.invoke(cli, [
            "generate",
            "--repo", str(FIXTURES.parent.parent),
            "--gateway", "test-gw",
            "--owner", "test-owner",
            "--out", out_file,
        ])

        assert result.exit_code == 0, f"CLI failed: {result.output}\n{result.exception}"
        assert Path(out_file).exists()
        doc = yaml.safe_load(Path(out_file).read_text())
        assert doc.get("openapi") == "3.1.0"

    def test_generate_exits_on_zero_routes(self, tmp_path, monkeypatch):
        """generate exits with code 1 when no routes are found."""
        import spec_engine.scanner as _scanner_mod

        mock_scanner = MagicMock()
        mock_scanner.scan.return_value = []
        monkeypatch.setattr(_scanner_mod, "get_scanner", lambda *a, **kw: mock_scanner)

        runner = CliRunner()
        result = runner.invoke(cli, [
            "generate",
            "--repo", str(tmp_path),
            "--gateway", "test-gw",
        ])
        assert result.exit_code == 1
        assert "No routes found" in result.output or "No routes found" in (result.exception and str(result.exception) or "")

    def test_generate_writes_valid_openapi(self, tmp_path, monkeypatch):
        """Spec written by generate is parseable and contains expected keys."""
        original_run = subprocess.run

        def _fake_subprocess(args, **kwargs):
            if args and args[0] in ("redocly", "spectral"):
                raise FileNotFoundError("tool not installed")
            return original_run(args, **kwargs)

        monkeypatch.setattr(subprocess, "run", _fake_subprocess)

        out_file = str(tmp_path / "api.yaml")
        runner = CliRunner()
        result = runner.invoke(cli, [
            "generate",
            "--repo", str(FIXTURES.parent.parent),
            "--gateway", "gw-prod",
            "--owner", "my-team",
            "--out", out_file,
        ])

        assert result.exit_code == 0
        doc = yaml.safe_load(Path(out_file).read_text())
        assert "paths" in doc
        assert doc["info"]["x-gateway"] == "gw-prod"
        assert doc["info"]["x-owner"] == "my-team"
