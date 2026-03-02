"""Tests for spec_engine/config.py — Section 3.6."""

import pytest

from spec_engine.config import Config


class TestConfigDefaults:
    def test_load_with_no_args_returns_defaults(self, monkeypatch, tmp_path):
        # Run from a tmp dir so we never accidentally pick up a real config.yaml
        monkeypatch.chdir(tmp_path)
        cfg = Config.load()
        assert cfg.gateway == "unknown"
        assert cfg.env == "production"
        assert cfg.owner == "unknown"
        assert cfg.strict_mode is True
        assert cfg.out == "./openapi.yaml"

    def test_default_required_x_fields(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        cfg = Config.load()
        assert "x-owner" in cfg.required_x_fields
        assert "x-gateway" in cfg.required_x_fields
        assert "x-lifecycle" in cfg.required_x_fields

    def test_load_does_not_raise_when_no_config_file(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        cfg = Config.load(config_path=str(tmp_path / "nonexistent.yaml"))
        assert cfg.gateway == "unknown"


class TestConfigFileLoading:
    def test_load_from_file_sets_gateway(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        config_file = tmp_path / "config.yaml"
        config_file.write_text("gateway: kong-test\n")
        cfg = Config.load(config_path=str(config_file))
        assert cfg.gateway == "kong-test"

    def test_load_from_file_sets_multiple_fields(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        config_file = tmp_path / "config.yaml"
        config_file.write_text(
            "gateway: kong-prod\n"
            "env: staging\n"
            "owner: payments-team\n"
            "strict_mode: false\n"
        )
        cfg = Config.load(config_path=str(config_file))
        assert cfg.gateway == "kong-prod"
        assert cfg.env == "staging"
        assert cfg.owner == "payments-team"
        assert cfg.strict_mode is False

    def test_load_from_file_with_exclude_paths(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        config_file = tmp_path / "config.yaml"
        config_file.write_text("exclude_paths:\n  - /health\n  - /metrics\n")
        cfg = Config.load(config_path=str(config_file))
        assert "/health" in cfg.exclude_paths
        assert "/metrics" in cfg.exclude_paths

    def test_load_default_config_yaml_in_cwd(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "config.yaml").write_text("gateway: from-cwd\n")
        cfg = Config.load()  # no config_path — should find ./config.yaml
        assert cfg.gateway == "from-cwd"


class TestCliOverrides:
    def test_cli_override_takes_priority_over_file(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        config_file = tmp_path / "config.yaml"
        config_file.write_text("gateway: file-gateway\n")
        cfg = Config.load(
            config_path=str(config_file),
            overrides={"gateway": "cli-gateway"},
        )
        assert cfg.gateway == "cli-gateway"

    def test_cli_override_preserves_unrelated_file_values(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        config_file = tmp_path / "config.yaml"
        config_file.write_text("gateway: file-gw\nenv: staging\n")
        cfg = Config.load(
            config_path=str(config_file),
            overrides={"gateway": "cli-gw"},
        )
        assert cfg.gateway == "cli-gw"
        assert cfg.env == "staging"  # file value preserved

    def test_cli_overrides_none_does_not_raise(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        cfg = Config.load(overrides=None)
        assert cfg.gateway == "unknown"

    def test_cli_override_env_field(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        cfg = Config.load(overrides={"env": "dev"})
        assert cfg.env == "dev"


class TestConfigValidation:
    def test_validate_raises_when_gateway_unknown_strict_mode(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        cfg = Config.load()
        assert cfg.gateway == "unknown"
        assert cfg.strict_mode is True
        with pytest.raises(ValueError, match="gateway"):
            cfg.validate()

    def test_validate_passes_when_gateway_set(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        cfg = Config.load(overrides={"gateway": "kong-prod"})
        cfg.validate()  # must not raise

    def test_validate_does_not_raise_when_strict_mode_false(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        cfg = Config.load(overrides={"strict_mode": False})
        cfg.validate()  # must not raise even though gateway is "unknown"

    def test_validate_error_message_is_helpful(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        cfg = Config.load()
        with pytest.raises(ValueError) as exc_info:
            cfg.validate()
        assert "--gateway" in str(exc_info.value) or "gateway" in str(exc_info.value).lower()


class TestRepoConfig:
    def test_repo_config_overrides_main_config(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        config_file = tmp_path / "config.yaml"
        config_file.write_text("gateway: config-gw\n")
        repo_config = tmp_path / ".spec-engine.yaml"
        repo_config.write_text("gateway: repo-gw\n")
        cfg = Config.load(config_path=str(config_file))
        assert cfg.gateway == "repo-gw"

    def test_cli_overrides_repo_config(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        repo_config = tmp_path / ".spec-engine.yaml"
        repo_config.write_text("gateway: repo-gw\n")
        cfg = Config.load(overrides={"gateway": "cli-gw"})
        assert cfg.gateway == "cli-gw"
