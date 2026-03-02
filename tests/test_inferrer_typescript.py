"""Tests for spec_engine/inferrer/typescript_ast.py — TypeScriptASTInferrer."""

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from spec_engine.inferrer.typescript_ast import TypeScriptASTInferrer, _SCRIPT_PATH
from spec_engine.config import Config
from spec_engine.models import Confidence


def _make_inferrer(tmp_path: Path) -> TypeScriptASTInferrer:
    return TypeScriptASTInferrer(str(tmp_path), Config())


# ---------------------------------------------------------------------------
# _find_type_file tests
# ---------------------------------------------------------------------------

class TestFindTypeFile:
    def test_returns_none_when_no_ts_files(self, tmp_path):
        inf = _make_inferrer(tmp_path)
        assert inf._find_type_file("Foo") is None

    def test_finds_interface_declaration(self, tmp_path):
        ts_file = tmp_path / "foo.ts"
        ts_file.write_text("interface Foo { id: number; }")
        inf = _make_inferrer(tmp_path)
        assert inf._find_type_file("Foo") == ts_file

    def test_finds_class_declaration(self, tmp_path):
        ts_file = tmp_path / "bar.ts"
        ts_file.write_text("class Bar { name: string; }")
        inf = _make_inferrer(tmp_path)
        assert inf._find_type_file("Bar") == ts_file

    def test_finds_type_alias(self, tmp_path):
        ts_file = tmp_path / "types.ts"
        ts_file.write_text("type MyAlias = { value: string; }")
        inf = _make_inferrer(tmp_path)
        assert inf._find_type_file("MyAlias") == ts_file

    def test_prefers_dto_in_path(self, tmp_path):
        dto_dir = tmp_path / "dto"
        dto_dir.mkdir()
        other_file = tmp_path / "other.ts"
        dto_file = dto_dir / "foo.dto.ts"
        other_file.write_text("interface Foo { id: number; }")
        dto_file.write_text("interface Foo { id: number; }")
        inf = _make_inferrer(tmp_path)
        result = inf._find_type_file("Foo")
        assert "dto" in str(result)


# ---------------------------------------------------------------------------
# _extract_fields tests (subprocess mocked)
# ---------------------------------------------------------------------------

class TestExtractFields:
    def test_node_not_found_returns_empty(self, tmp_path, monkeypatch):
        ts_file = tmp_path / "foo.ts"
        ts_file.write_text("interface Foo { id: number; }")
        monkeypatch.setattr(
            subprocess,
            "run",
            lambda *args, **kwargs: (_ for _ in ()).throw(FileNotFoundError()),
        )
        inf = _make_inferrer(tmp_path)
        # Also ensure _SCRIPT_PATH appears to exist
        monkeypatch.setattr(
            "spec_engine.inferrer.typescript_ast._SCRIPT_PATH",
            ts_file,  # re-use ts_file as a stand-in existing file
        )
        result = inf._extract_fields("Foo", ts_file, set())
        assert result.is_empty

    def test_timeout_returns_empty(self, tmp_path, monkeypatch):
        ts_file = tmp_path / "foo.ts"
        ts_file.write_text("interface Foo { id: number; }")
        monkeypatch.setattr(
            subprocess,
            "run",
            lambda *args, **kwargs: (_ for _ in ()).throw(subprocess.TimeoutExpired("node", 30)),
        )
        inf = _make_inferrer(tmp_path)
        monkeypatch.setattr(
            "spec_engine.inferrer.typescript_ast._SCRIPT_PATH",
            ts_file,
        )
        result = inf._extract_fields("Foo", ts_file, set())
        assert result.is_empty

    def test_empty_stdout_returns_empty(self, tmp_path, monkeypatch):
        ts_file = tmp_path / "foo.ts"
        ts_file.write_text("interface Foo { id: number; }")
        mock_result = MagicMock()
        mock_result.stdout = ""
        monkeypatch.setattr(subprocess, "run", lambda *a, **kw: mock_result)
        inf = _make_inferrer(tmp_path)
        monkeypatch.setattr(
            "spec_engine.inferrer.typescript_ast._SCRIPT_PATH",
            ts_file,
        )
        result = inf._extract_fields("Foo", ts_file, set())
        assert result.is_empty

    def test_invalid_json_returns_empty(self, tmp_path, monkeypatch):
        ts_file = tmp_path / "foo.ts"
        ts_file.write_text("interface Foo { id: number; }")
        mock_result = MagicMock()
        mock_result.stdout = "not-json"
        monkeypatch.setattr(subprocess, "run", lambda *a, **kw: mock_result)
        inf = _make_inferrer(tmp_path)
        monkeypatch.setattr(
            "spec_engine.inferrer.typescript_ast._SCRIPT_PATH",
            ts_file,
        )
        result = inf._extract_fields("Foo", ts_file, set())
        assert result.is_empty

    def test_no_properties_key_returns_empty(self, tmp_path, monkeypatch):
        ts_file = tmp_path / "foo.ts"
        ts_file.write_text("interface Foo { id: number; }")
        mock_result = MagicMock()
        mock_result.stdout = json.dumps({"type": "object"})
        monkeypatch.setattr(subprocess, "run", lambda *a, **kw: mock_result)
        inf = _make_inferrer(tmp_path)
        monkeypatch.setattr(
            "spec_engine.inferrer.typescript_ast._SCRIPT_PATH",
            ts_file,
        )
        result = inf._extract_fields("Foo", ts_file, set())
        assert result.is_empty

    def test_valid_schema_returns_result(self, tmp_path, monkeypatch):
        ts_file = tmp_path / "foo.ts"
        ts_file.write_text("interface Foo { id: number; }")
        schema = {"type": "object", "properties": {"id": {"type": "number"}}}
        mock_result = MagicMock()
        mock_result.stdout = json.dumps(schema)
        monkeypatch.setattr(subprocess, "run", lambda *a, **kw: mock_result)
        inf = _make_inferrer(tmp_path)
        monkeypatch.setattr(
            "spec_engine.inferrer.typescript_ast._SCRIPT_PATH",
            ts_file,
        )
        result = inf._extract_fields("Foo", ts_file, set())
        assert not result.is_empty
        assert result.json_schema["properties"]["id"] == {"type": "number"}
        assert result.confidence == Confidence.HIGH

    def test_script_missing_returns_empty(self, tmp_path, monkeypatch):
        ts_file = tmp_path / "foo.ts"
        ts_file.write_text("interface Foo { id: number; }")
        monkeypatch.setattr(
            "spec_engine.inferrer.typescript_ast._SCRIPT_PATH",
            tmp_path / "nonexistent_script.js",
        )
        inf = _make_inferrer(tmp_path)
        result = inf._extract_fields("Foo", ts_file, set())
        assert result.is_empty
