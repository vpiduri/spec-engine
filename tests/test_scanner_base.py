"""Tests for spec_engine/scanner/base.py — BaseScanner._iter_files()."""

import pytest
from pathlib import Path
from unittest.mock import MagicMock

from spec_engine.scanner.base import BaseScanner, SKIP_DIRS
from spec_engine.config import Config


# ---------------------------------------------------------------------------
# Concrete subclass for testing
# ---------------------------------------------------------------------------

class DummyScanner(BaseScanner):
    """Minimal concrete scanner for testing _iter_files()."""
    EXTENSIONS = [".py"]

    def scan(self):
        return []


def make_scanner(tmp_path: Path, exclude_paths=None) -> DummyScanner:
    config = Config()
    if exclude_paths:
        config.exclude_paths = exclude_paths
    return DummyScanner(str(tmp_path), config)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestIterFiles:
    def test_finds_files_with_extension(self, tmp_path):
        (tmp_path / "app.py").write_text("print('hello')")
        scanner = make_scanner(tmp_path)
        found = scanner._iter_files()
        assert any(f.name == "app.py" for f in found)

    def test_ignores_other_extensions(self, tmp_path):
        (tmp_path / "data.json").write_text("{}")
        scanner = make_scanner(tmp_path)
        found = scanner._iter_files()
        assert not any(f.name == "data.json" for f in found)

    def test_skips_pycache_dir(self, tmp_path):
        cache_dir = tmp_path / "__pycache__"
        cache_dir.mkdir()
        (cache_dir / "mod.py").write_text("x=1")
        scanner = make_scanner(tmp_path)
        found = scanner._iter_files()
        assert not any("__pycache__" in str(f) for f in found)

    def test_skips_git_dir(self, tmp_path):
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        (git_dir / "hooks.py").write_text("x=1")
        scanner = make_scanner(tmp_path)
        found = scanner._iter_files()
        assert not any(".git" in str(f) for f in found)

    def test_skips_node_modules(self, tmp_path):
        nm = tmp_path / "node_modules"
        nm.mkdir()
        (nm / "dep.py").write_text("x=1")
        scanner = make_scanner(tmp_path)
        found = scanner._iter_files()
        assert not any("node_modules" in str(f) for f in found)

    def test_skips_build_dir(self, tmp_path):
        build = tmp_path / "build"
        build.mkdir()
        (build / "output.py").write_text("x=1")
        scanner = make_scanner(tmp_path)
        found = scanner._iter_files()
        assert not any("build" in str(f) for f in found)

    def test_skips_dot_dir(self, tmp_path):
        dot_dir = tmp_path / ".hidden"
        dot_dir.mkdir()
        (dot_dir / "secret.py").write_text("x=1")
        scanner = make_scanner(tmp_path)
        found = scanner._iter_files()
        assert not any(".hidden" in str(f) for f in found)

    def test_respects_exclude_paths(self, tmp_path):
        (tmp_path / "excluded.py").write_text("x=1")
        (tmp_path / "included.py").write_text("y=2")
        scanner = make_scanner(tmp_path, exclude_paths=["excluded.py"])
        found = [f.name for f in scanner._iter_files()]
        assert "included.py" in found
        assert "excluded.py" not in found

    def test_exclude_paths_glob_pattern(self, tmp_path):
        sub = tmp_path / "tests"
        sub.mkdir()
        (sub / "test_app.py").write_text("x=1")
        (tmp_path / "app.py").write_text("y=2")
        scanner = make_scanner(tmp_path, exclude_paths=["tests/*"])
        found = [f.name for f in scanner._iter_files()]
        assert "app.py" in found
        assert "test_app.py" not in found

    def test_deduplicates_files(self, tmp_path):
        """Same file should appear once even if matched by multiple extensions."""
        (tmp_path / "app.py").write_text("x=1")

        class MultiExtScanner(BaseScanner):
            EXTENSIONS = [".py", ".py"]  # duplicate
            def scan(self): return []

        scanner = MultiExtScanner(str(tmp_path), Config())
        found = scanner._iter_files()
        names = [f.name for f in found]
        assert names.count("app.py") == 1

    def test_finds_files_in_subdirs(self, tmp_path):
        sub = tmp_path / "src" / "api"
        sub.mkdir(parents=True)
        (sub / "routes.py").write_text("x=1")
        scanner = make_scanner(tmp_path)
        found = scanner._iter_files()
        assert any(f.name == "routes.py" for f in found)

    def test_skip_dirs_constant_contains_expected_entries(self):
        assert ".git" in SKIP_DIRS
        assert "node_modules" in SKIP_DIRS
        assert "__pycache__" in SKIP_DIRS
        assert "target" in SKIP_DIRS
        assert "build" in SKIP_DIRS
