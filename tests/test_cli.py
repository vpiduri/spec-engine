"""Tests for spec_engine/cli.py — Section 9."""

import json
import os
import pytest
import yaml
from pathlib import Path
from unittest.mock import patch, MagicMock

from click.testing import CliRunner

from spec_engine.cli import cli
from spec_engine.config import Config
from spec_engine.models import RouteInfo, SchemaResult, Confidence


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_valid_spec(path: Path, title: str = "Test API") -> str:
    spec = {
        "openapi": "3.1.0",
        "info": {
            "title": title,
            "version": "1.0.0",
            "x-owner": "team-a",
            "x-gateway": "kong",
            "x-lifecycle": "production",
        },
        "paths": {},
    }
    spec_file = str(path / "openapi.yaml")
    Path(spec_file).write_text(yaml.dump(spec))
    return spec_file


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


def _dummy_schema() -> SchemaResult:
    return SchemaResult(
        type_name="Item",
        json_schema={"type": "object", "properties": {"id": {"type": "string"}}},
        confidence=Confidence.HIGH,
        source_file="src/Item.java",
    )


# ---------------------------------------------------------------------------
# Basic CLI tests
# ---------------------------------------------------------------------------

class TestCliHelp:
    def test_cli_help_exits_zero(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "spec-engine" in result.output.lower() or "Usage" in result.output

    def test_generate_help_exits_zero(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["generate", "--help"])
        assert result.exit_code == 0

    def test_scan_help_exits_zero(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["scan", "--help"])
        assert result.exit_code == 0

    def test_validate_help_exits_zero(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["validate", "--help"])
        assert result.exit_code == 0

    def test_publish_help_exits_zero(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["publish", "--help"])
        assert result.exit_code == 0


# ---------------------------------------------------------------------------
# scan command
# ---------------------------------------------------------------------------

class TestScanCommand:
    def test_scan_writes_manifest(self, tmp_path):
        # Create a minimal Python file to scan
        src = tmp_path / "app.py"
        src.write_text("from fastapi import FastAPI\napp = FastAPI()\n@app.get('/v1/items')\ndef list_items(): pass\n")
        manifest_path = str(tmp_path / "manifest.json")

        runner = CliRunner()
        with patch("spec_engine.scanner.detect_framework", return_value="fastapi"), \
             patch("spec_engine.scanner.get_scanner") as mock_get:
            mock_scanner = MagicMock()
            mock_scanner.scan.return_value = [_make_route()]
            mock_get.return_value = mock_scanner
            result = runner.invoke(cli, [
                "scan",
                "--repo", str(tmp_path),
                "--manifest", manifest_path,
            ])

        assert result.exit_code == 0
        assert Path(manifest_path).exists()
        data = json.loads(Path(manifest_path).read_text())
        assert data["route_count"] == 1


# ---------------------------------------------------------------------------
# validate command
# ---------------------------------------------------------------------------

class TestValidateCommand:
    def test_validate_missing_file_exits_nonzero(self, tmp_path):
        runner = CliRunner()
        result = runner.invoke(cli, ["validate", str(tmp_path / "nonexistent.yaml")])
        assert result.exit_code != 0

    def test_validate_valid_spec_exits_zero(self, tmp_path):
        spec_file = _write_valid_spec(tmp_path)
        runner = CliRunner()
        with patch("spec_engine.validator._run_redocly", return_value=[]), \
             patch("spec_engine.validator._run_spectral", return_value=([], [])):
            result = runner.invoke(cli, ["validate", spec_file])
        assert result.exit_code == 0
        assert "passed" in result.output.lower()

    def test_validate_missing_x_fields_exits_one(self, tmp_path):
        # Spec without x-owner / x-gateway / x-lifecycle
        spec = {"openapi": "3.1.0", "info": {"title": "T", "version": "1"}, "paths": {}}
        spec_file = str(tmp_path / "spec.yaml")
        Path(spec_file).write_text(yaml.dump(spec))

        runner = CliRunner()
        with patch("spec_engine.validator._run_redocly", return_value=[]), \
             patch("spec_engine.validator._run_spectral", return_value=([], [])):
            result = runner.invoke(cli, ["validate", spec_file])
        assert result.exit_code == 1


# ---------------------------------------------------------------------------
# publish command
# ---------------------------------------------------------------------------

class TestPublishCommand:
    def test_publish_dry_run(self, tmp_path):
        spec_file = _write_valid_spec(tmp_path)

        def _fake_publish_spec(spec_path, config, dry_run=False):
            pass  # no-op

        runner = CliRunner()
        with patch("spec_engine.cli._publish_spec", side_effect=_fake_publish_spec):
            result = runner.invoke(cli, ["publish", spec_file, "--dry-run"])
        assert result.exit_code == 0


# ---------------------------------------------------------------------------
# schema command
# ---------------------------------------------------------------------------

class TestSchemaCommand:
    def test_schema_writes_json(self, tmp_path):
        from spec_engine.models import write_manifest
        routes = [_make_route()]
        manifest_path = str(tmp_path / "manifest.json")
        write_manifest(routes, str(tmp_path), "spring", manifest_path)

        out_path = str(tmp_path / "schemas.json")
        runner = CliRunner()
        with patch("spec_engine.inferrer.run_inference", return_value={"Item": _dummy_schema()}):
            result = runner.invoke(cli, [
                "schema",
                "--manifest", manifest_path,
                "--repo", str(tmp_path),
                "--out", out_path,
            ])

        assert result.exit_code == 0
        assert Path(out_path).exists()
        data = json.loads(Path(out_path).read_text())
        assert "Item" in data


# ---------------------------------------------------------------------------
# assemble command
# ---------------------------------------------------------------------------

class TestAssembleCommand:
    def test_assemble_writes_yaml(self, tmp_path):
        from spec_engine.models import write_manifest
        routes = [_make_route()]
        manifest_path = str(tmp_path / "manifest.json")
        write_manifest(routes, str(tmp_path), "spring", manifest_path)

        out_path = str(tmp_path / "openapi.yaml")
        runner = CliRunner()
        with patch("spec_engine.inferrer.run_inference", return_value={}), \
             patch("spec_engine.assembler.assemble", return_value="openapi: 3.1.0\n"):
            result = runner.invoke(cli, [
                "assemble",
                "--manifest", manifest_path,
                "--repo", str(tmp_path),
                "--out", out_path,
                "--gateway", "kong",
            ])

        assert result.exit_code == 0
        assert Path(out_path).exists()


# ---------------------------------------------------------------------------
# generate command (integration-level with mocks)
# ---------------------------------------------------------------------------

class TestGenerateCommand:
    def test_generate_full_pipeline(self, tmp_path):
        out_path = str(tmp_path / "openapi.yaml")

        # Minimal valid YAML that validate will accept
        valid_yaml = yaml.dump({
            "openapi": "3.1.0",
            "info": {
                "title": "My Service",
                "version": "1.0.0",
                "x-owner": "team",
                "x-gateway": "kong",
                "x-lifecycle": "production",
            },
            "paths": {},
        })

        runner = CliRunner()
        with patch("spec_engine.scanner.detect_framework", return_value="spring"), \
             patch("spec_engine.scanner.get_scanner") as mock_get_scanner, \
             patch("spec_engine.inferrer.run_inference", return_value={}), \
             patch("spec_engine.assembler.assemble", return_value=valid_yaml), \
             patch("spec_engine.validator._run_redocly", return_value=[]), \
             patch("spec_engine.validator._run_spectral", return_value=([], [])):

            mock_scanner = MagicMock()
            mock_scanner.scan.return_value = [_make_route()]
            mock_get_scanner.return_value = mock_scanner

            result = runner.invoke(cli, [
                "generate",
                "--repo", str(tmp_path),
                "--gateway", "kong",
                "--owner", "team",
                "--out", out_path,
            ])

        assert result.exit_code == 0, result.output
        assert Path(out_path).exists()
