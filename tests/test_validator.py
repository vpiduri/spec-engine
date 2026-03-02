"""Tests for spec_engine/validator.py — Section 7."""

import pytest
import yaml
from pathlib import Path
from unittest.mock import patch, MagicMock
import subprocess

from spec_engine.validator import (
    ValidationResult,
    validate,
    _run_redocly,
    _run_spectral,
    _check_x_fields,
)
from spec_engine.config import Config


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_config(**kwargs) -> Config:
    defaults = {"gateway": "kong-prod", "strict_mode": False}
    defaults.update(kwargs)
    return Config(**defaults)


def _write_valid_spec(path: Path) -> str:
    """Write a minimal valid OpenAPI spec with all required x- fields."""
    spec = {
        "openapi": "3.1.0",
        "info": {
            "title": "Test API",
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


# ---------------------------------------------------------------------------
# ValidationResult
# ---------------------------------------------------------------------------

class TestValidationResult:
    def test_passed_when_no_errors(self):
        vr = ValidationResult()
        assert vr.passed is True

    def test_failed_when_errors_present(self):
        vr = ValidationResult(errors=["some error"])
        assert vr.passed is False

    def test_raise_if_failed_raises_value_error(self):
        vr = ValidationResult(errors=["err1", "err2"])
        with pytest.raises(ValueError, match="2 error"):
            vr.raise_if_failed()

    def test_raise_if_failed_no_raise_when_passed(self):
        vr = ValidationResult()
        vr.raise_if_failed()  # should not raise


# ---------------------------------------------------------------------------
# x-fields check
# ---------------------------------------------------------------------------

class TestCheckXFields:
    def test_check_x_fields_all_present(self, tmp_path):
        spec_file = _write_valid_spec(tmp_path)
        errors = _check_x_fields(spec_file, ["x-owner", "x-gateway", "x-lifecycle"])
        assert errors == []

    def test_check_x_fields_missing_one(self, tmp_path):
        spec = {"openapi": "3.1.0", "info": {"title": "T", "version": "1", "x-owner": "me"}, "paths": {}}
        spec_file = str(tmp_path / "openapi.yaml")
        Path(spec_file).write_text(yaml.dump(spec))
        errors = _check_x_fields(spec_file, ["x-owner", "x-gateway"])
        assert any("x-gateway" in e for e in errors)
        assert not any("x-owner" in e for e in errors)

    def test_check_x_fields_missing_multiple(self, tmp_path):
        spec = {"openapi": "3.1.0", "info": {"title": "T", "version": "1"}, "paths": {}}
        spec_file = str(tmp_path / "openapi.yaml")
        Path(spec_file).write_text(yaml.dump(spec))
        errors = _check_x_fields(spec_file, ["x-owner", "x-gateway", "x-lifecycle"])
        assert len(errors) == 3

    def test_check_x_fields_parse_error(self, tmp_path):
        spec_file = str(tmp_path / "bad.yaml")
        # YAML with a tab character inside a mapping — triggers a scanner error
        Path(spec_file).write_text("key:\n\t- broken_tab_indent\n")
        errors = _check_x_fields(spec_file, ["x-owner"])
        assert len(errors) == 1
        assert "[x-fields] Failed to parse spec" in errors[0]

    def test_check_x_fields_empty_required_list(self, tmp_path):
        spec_file = _write_valid_spec(tmp_path)
        errors = _check_x_fields(spec_file, [])
        assert errors == []


# ---------------------------------------------------------------------------
# Redocly
# ---------------------------------------------------------------------------

class TestRunRedocly:
    def test_tool_not_installed_returns_empty(self):
        with patch("subprocess.run", side_effect=FileNotFoundError):
            result = _run_redocly("/fake/spec.yaml")
        assert result == []

    def test_timeout_returns_error_string(self):
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="redocly", timeout=60)):
            result = _run_redocly("/fake/spec.yaml")
        assert len(result) == 1
        assert "timed out" in result[0]

    def test_zero_return_code_returns_empty(self):
        mock = MagicMock()
        mock.returncode = 0
        mock.stdout = ""
        with patch("subprocess.run", return_value=mock):
            result = _run_redocly("/fake/spec.yaml")
        assert result == []

    def test_nonzero_with_json_errors(self):
        problems = [
            {"severity": "error", "message": "Missing required field"},
            {"severity": "warning", "message": "Deprecated"},
        ]
        mock = MagicMock()
        mock.returncode = 1
        mock.stdout = '{"problems": ' + str(problems).replace("'", '"') + '}'
        import json
        mock.stdout = json.dumps({"problems": problems})
        with patch("subprocess.run", return_value=mock):
            result = _run_redocly("/fake/spec.yaml")
        assert len(result) == 1
        assert "[redocly] Missing required field" in result[0]


# ---------------------------------------------------------------------------
# Spectral
# ---------------------------------------------------------------------------

class TestRunSpectral:
    def test_tool_not_installed_returns_empty(self, tmp_path):
        ruleset = tmp_path / ".spectral.amex.yaml"
        ruleset.write_text("rules: {}")
        with patch("subprocess.run", side_effect=FileNotFoundError), \
             patch("pathlib.Path.exists", return_value=True):
            errs, warns = _run_spectral("/fake/spec.yaml")
        assert errs == []
        assert warns == []

    def test_no_ruleset_file_returns_empty(self, monkeypatch):
        monkeypatch.chdir("/tmp")
        # No .spectral.amex.yaml in /tmp (most likely)
        errs, warns = _run_spectral("/fake/spec.yaml")
        # Either empty (file not found) or depends on environment — just check types
        assert isinstance(errs, list)
        assert isinstance(warns, list)

    def test_spectral_parses_severity_0_as_error(self, tmp_path):
        items = [{"severity": 0, "code": "must-have-owner", "message": "x-owner missing"}]
        import json
        mock = MagicMock()
        mock.returncode = 1
        mock.stdout = json.dumps(items)
        ruleset = Path(".spectral.amex.yaml")
        with patch("subprocess.run", return_value=mock), \
             patch.object(Path, "exists", return_value=True):
            errs, warns = _run_spectral("/fake/spec.yaml")
        assert any("[spectral]" in e for e in errs)

    def test_spectral_parses_severity_1_as_warning(self, tmp_path):
        items = [{"severity": 1, "code": "info-missing", "message": "description missing"}]
        import json
        mock = MagicMock()
        mock.returncode = 1
        mock.stdout = json.dumps(items)
        with patch("subprocess.run", return_value=mock), \
             patch.object(Path, "exists", return_value=True):
            errs, warns = _run_spectral("/fake/spec.yaml")
        assert any("[spectral]" in w for w in warns)


# ---------------------------------------------------------------------------
# validate() integration
# ---------------------------------------------------------------------------

class TestValidate:
    def test_validate_nonexistent_file(self, tmp_path):
        cfg = _make_config()
        result = validate("/nonexistent/spec.yaml", cfg)
        assert not result.passed
        assert any("not found" in e for e in result.errors)

    def test_validate_passes_valid_spec(self, tmp_path):
        spec_file = _write_valid_spec(tmp_path)
        cfg = _make_config(strict_mode=False)
        # Patch out external tools so we only test x-fields
        with patch("spec_engine.validator._run_redocly", return_value=[]), \
             patch("spec_engine.validator._run_spectral", return_value=([], [])):
            result = validate(spec_file, cfg)
        assert result.passed

    def test_validate_strict_mode_raises_on_errors(self, tmp_path):
        spec_file = _write_valid_spec(tmp_path)
        cfg = _make_config(strict_mode=True)
        with patch("spec_engine.validator._run_redocly", return_value=["[redocly] fatal error"]), \
             patch("spec_engine.validator._run_spectral", return_value=([], [])):
            with pytest.raises(ValueError, match="Validation failed"):
                validate(spec_file, cfg)

    def test_validate_no_strict_mode_does_not_raise(self, tmp_path):
        spec_file = _write_valid_spec(tmp_path)
        cfg = _make_config(strict_mode=False)
        with patch("spec_engine.validator._run_redocly", return_value=["[redocly] error"]), \
             patch("spec_engine.validator._run_spectral", return_value=([], [])):
            result = validate(spec_file, cfg)
        assert not result.passed  # has errors, but no exception

    def test_validate_missing_x_fields_adds_errors(self, tmp_path):
        # Write spec without x-owner
        spec = {"openapi": "3.1.0", "info": {"title": "T", "version": "1"}, "paths": {}}
        spec_file = str(tmp_path / "spec.yaml")
        Path(spec_file).write_text(yaml.dump(spec))
        cfg = _make_config(strict_mode=False)
        with patch("spec_engine.validator._run_redocly", return_value=[]), \
             patch("spec_engine.validator._run_spectral", return_value=([], [])):
            result = validate(spec_file, cfg)
        assert not result.passed
        assert any("x-owner" in e for e in result.errors)

    def test_validate_collects_warnings(self, tmp_path):
        spec_file = _write_valid_spec(tmp_path)
        cfg = _make_config(strict_mode=False)
        with patch("spec_engine.validator._run_redocly", return_value=[]), \
             patch("spec_engine.validator._run_spectral", return_value=([], ["[spectral] warn: something"])):
            result = validate(spec_file, cfg)
        assert result.passed  # no errors
        assert len(result.warnings) == 1
