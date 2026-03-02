"""
Configuration loader for spec-engine.

Supports a layered config system with four priority levels (highest to lowest):
  1. CLI overrides  — dot-notation keys passed programmatically, e.g. {"gateway": "kong-prod"}
  2. Repo .spec-engine.yaml — found by walking up from the current working directory
  3. config.yaml   — explicit config file path or default ./config.yaml
  4. Dataclass defaults

Usage:
  from spec_engine.config import Config
  cfg = Config.load(config_path="config.yaml", overrides={"gateway": "kong-prod"})
  cfg.validate()
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields as dataclass_fields
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _deep_merge(base: dict, override: dict) -> dict:
    """
    Recursively merge two dicts. Keys in *override* take priority over *base*.
    Nested dicts are merged rather than replaced wholesale.
    """
    result = dict(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _apply_dot_overrides(data: dict, overrides: Dict[str, Any]) -> None:
    """
    Apply dot-notation CLI overrides in-place to a nested dict.

    Example: {"gateway": "kong-prod"} sets data["gateway"] = "kong-prod".
    Missing intermediate dicts are created automatically.
    """
    for key, value in overrides.items():
        parts = key.split(".")
        d = data
        for part in parts[:-1]:
            if part not in d or not isinstance(d.get(part), dict):
                d[part] = {}
            d = d[part]
        d[parts[-1]] = value


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

@dataclass
class Config:
    """
    Top-level engine configuration.

    Loaded by Config.load() which merges defaults, config files, and CLI overrides
    in priority order. Use Config.validate() to check required fields before running
    the pipeline.
    """

    # API metadata injected into the OpenAPI info block
    gateway: str = "unknown"
    env: str = "production"
    owner: str = "unknown"

    # Engine behaviour
    strict_mode: bool = True   # fail pipeline on validation errors
    required_x_fields: List[str] = field(default_factory=lambda: [
        "x-owner", "x-gateway", "x-lifecycle"
    ])
    exclude_paths: List[str] = field(default_factory=list)

    # Framework override + type-file selection
    framework: str = ""      # override framework auto-detection ("fastapi", "spring", etc.)
    prefer_file: str = ""    # fnmatch glob: prefer this path when multiple type files found

    # Output
    out: str = "./openapi.yaml"

    # ---------------------------------------------------------------------------
    # Class methods
    # ---------------------------------------------------------------------------

    @classmethod
    def load(
        cls,
        config_path: Optional[str] = None,
        overrides: Optional[Dict[str, Any]] = None,
    ) -> "Config":
        """
        Load config using the layered priority system.

        Priority (highest → lowest):
          CLI overrides > repo .spec-engine.yaml > config.yaml > defaults

        Does not raise if config files are absent — falls back to defaults silently.
        Dot-notation override keys are supported.
        """
        data: dict = {}

        # --- Layer 1: explicit config file (lowest file-level priority) -----------
        resolved_config_path: Optional[Path] = None
        if config_path:
            resolved_config_path = Path(config_path)
        else:
            # Try the default config.yaml in the current working directory
            default = Path("config.yaml")
            if default.exists():
                resolved_config_path = default

        if resolved_config_path and resolved_config_path.exists():
            try:
                file_data = yaml.safe_load(resolved_config_path.read_text()) or {}
                data = _deep_merge(data, file_data)
            except yaml.YAMLError:
                pass  # malformed config file — silently use defaults

        # --- Layer 2: repo .spec-engine.yaml (overrides config.yaml) -------------
        repo_config = cls._find_repo_config(str(Path.cwd()))
        if repo_config:
            data = _deep_merge(data, repo_config)

        # --- Layer 3: CLI overrides (highest priority) ----------------------------
        if overrides:
            _apply_dot_overrides(data, overrides)

        # --- Build Config from remaining keys -------------------------------------
        config_field_names = {f.name for f in dataclass_fields(cls)}
        config_data = {k: v for k, v in data.items() if k in config_field_names}

        return cls(**config_data)

    @classmethod
    def _find_repo_config(cls, repo_path: str) -> Optional[Dict]:
        """
        Search for a .spec-engine.yaml repo-level config file.

        Walks up from repo_path to the filesystem root, stopping at the first
        .spec-engine.yaml it finds. Returns the parsed dict, or None if not found.
        """
        current = Path(repo_path).resolve()
        for directory in [current, *current.parents]:
            candidate = directory / ".spec-engine.yaml"
            if candidate.exists():
                try:
                    return yaml.safe_load(candidate.read_text()) or {}
                except yaml.YAMLError:
                    return None
        return None

    # ---------------------------------------------------------------------------
    # Validation
    # ---------------------------------------------------------------------------

    def validate(self) -> None:
        """
        Validate the configuration before running the pipeline.

        In strict_mode (the default), raises ValueError if gateway has not been
        set from the default "unknown" value, since every published spec must
        declare which gateway it is deployed behind.

        Raises:
          ValueError — if strict_mode is True and gateway == "unknown"
        """
        if self.strict_mode and self.gateway == "unknown":
            raise ValueError(
                "Config.gateway must be set when strict_mode=True. "
                "Pass --gateway <name> or set 'gateway' in config.yaml. "
                "Example: --gateway kong-prod"
            )
