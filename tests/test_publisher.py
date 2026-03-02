"""Tests for spec_engine/publisher.py — Section 8."""

import json
import os
import pytest
import yaml
import respx
import httpx
from pathlib import Path
from unittest.mock import patch

from spec_engine.publisher import publish, _extract_api_name, _check_existing
from spec_engine.config import Config


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_config(**kwargs) -> Config:
    cfg = Config(gateway="kong", strict_mode=False, **kwargs)
    return cfg


def _config_with_catalog(url: str = "https://catalog.example.com") -> Config:
    cfg = Config.__new__(Config)
    cfg.__dict__.update(Config(gateway="kong", strict_mode=False).__dict__)
    cfg.catalog_url = url  # type: ignore[attr-defined]
    return cfg


def _write_spec(path: Path, title: str = "My API") -> str:
    spec = {"openapi": "3.1.0", "info": {"title": title, "version": "1.0"}, "paths": {}}
    spec_file = str(path / "openapi.yaml")
    Path(spec_file).write_text(yaml.dump(spec))
    return spec_file


# ---------------------------------------------------------------------------
# _extract_api_name
# ---------------------------------------------------------------------------

class TestExtractApiName:
    def test_extract_api_name_from_yaml(self):
        spec_content = yaml.dump({"info": {"title": "Payment API"}, "openapi": "3.1.0"})
        assert _extract_api_name(spec_content) == "Payment API"

    def test_extract_api_name_fallback_on_garbage(self):
        assert _extract_api_name("not: valid: yaml: content:::") == "unknown"

    def test_extract_api_name_fallback_missing_info(self):
        spec_content = yaml.dump({"openapi": "3.1.0"})
        assert _extract_api_name(spec_content) == "unknown"


# ---------------------------------------------------------------------------
# _check_existing
# ---------------------------------------------------------------------------

class TestCheckExisting:
    @respx.mock
    def test_check_existing_found(self):
        apis = [{"id": "abc123", "title": "My API"}, {"id": "xyz", "title": "Other"}]
        respx.get("https://catalog.example.com/apis").mock(
            return_value=httpx.Response(200, json=apis)
        )
        result = _check_existing("https://catalog.example.com", "My API", "token")
        assert result == "abc123"

    @respx.mock
    def test_check_existing_not_found(self):
        apis = [{"id": "xyz", "title": "Other API"}]
        respx.get("https://catalog.example.com/apis").mock(
            return_value=httpx.Response(200, json=apis)
        )
        result = _check_existing("https://catalog.example.com", "My API", "token")
        assert result is None

    def test_check_existing_request_error_returns_none(self):
        """Network error → returns None (no crash)."""
        with respx.mock:
            respx.get("https://catalog.example.com/apis").mock(side_effect=httpx.ConnectError("fail"))
            result = _check_existing("https://catalog.example.com", "My API", "token")
        assert result is None


# ---------------------------------------------------------------------------
# publish()
# ---------------------------------------------------------------------------

class TestPublish:
    def test_publish_missing_catalog_url_raises(self, tmp_path):
        spec_file = _write_spec(tmp_path)
        cfg = _make_config()  # no catalog_url
        with pytest.raises(ValueError, match="catalog_url"):
            publish(spec_file, cfg)

    def test_publish_missing_token_raises(self, tmp_path):
        spec_file = _write_spec(tmp_path)
        cfg = _config_with_catalog()
        env = {k: v for k, v in os.environ.items() if k != "EXPLORER_API_TOKEN"}
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(ValueError, match="EXPLORER_API_TOKEN"):
                publish(spec_file, cfg)

    def test_publish_dry_run_returns_status(self, tmp_path):
        spec_file = _write_spec(tmp_path)
        cfg = _config_with_catalog()
        # dry_run=True should not need token or make HTTP calls
        result = publish(spec_file, cfg, dry_run=True)
        assert result["status"] == "dry-run"
        assert result["spec_path"] == spec_file

    @respx.mock
    def test_publish_post_new_api(self, tmp_path):
        spec_file = _write_spec(tmp_path, title="Fresh API")
        cfg = _config_with_catalog("https://catalog.example.com")

        # GET /apis → empty list (no existing)
        respx.get("https://catalog.example.com/apis").mock(
            return_value=httpx.Response(200, json=[])
        )
        # POST /apis → created
        respx.post("https://catalog.example.com/apis").mock(
            return_value=httpx.Response(201, json={"id": "new-id", "title": "Fresh API"})
        )

        with patch.dict(os.environ, {"EXPLORER_API_TOKEN": "test-token"}):
            result = publish(spec_file, cfg)

        assert result["id"] == "new-id"

    @respx.mock
    def test_publish_put_existing_api(self, tmp_path):
        spec_file = _write_spec(tmp_path, title="Existing API")
        cfg = _config_with_catalog("https://catalog.example.com")

        # GET /apis → found existing
        respx.get("https://catalog.example.com/apis").mock(
            return_value=httpx.Response(200, json=[{"id": "existing-99", "title": "Existing API"}])
        )
        # PUT /apis/existing-99 → updated
        respx.put("https://catalog.example.com/apis/existing-99").mock(
            return_value=httpx.Response(200, json={"id": "existing-99", "updated": True})
        )

        with patch.dict(os.environ, {"EXPLORER_API_TOKEN": "test-token"}):
            result = publish(spec_file, cfg)

        assert result["id"] == "existing-99"
        assert result["updated"] is True
