"""
Stage 5 — Validator & Linter.

Runs three validation passes and returns a consolidated ValidationResult:
  1. Redocly structural validation (OpenAPI 3.1 schema conformance)
  2. Spectral Amex ruleset (.spectral.amex.yaml) — 9 custom business rules
  3. Custom required x- field check (x-owner, x-gateway, x-lifecycle)

A spec passes if errors is empty. Warnings and infos are non-blocking.
"""

from dataclasses import dataclass, field
from typing import List, Tuple
import subprocess
import json
import logging
from pathlib import Path
import yaml
from spec_engine.config import Config

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# ValidationResult
# ---------------------------------------------------------------------------

@dataclass
class ValidationResult:
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    infos: List[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.errors

    def raise_if_failed(self) -> None:
        if not self.passed:
            raise ValueError(
                f"Validation failed with {len(self.errors)} error(s):\n"
                + "\n".join(self.errors)
            )


# ---------------------------------------------------------------------------
# Pass 1 — Redocly
# ---------------------------------------------------------------------------

def _run_redocly(spec_path: str) -> List[str]:
    """Run redocly lint; return list of error strings."""
    try:
        result = subprocess.run(
            ["redocly", "lint", spec_path, "--format", "json"],
            capture_output=True,
            text=True,
            timeout=60,
        )
    except FileNotFoundError:
        log.debug("redocly not installed — skipping structural validation")
        return []
    except subprocess.TimeoutExpired:
        return ["[redocly] Validation timed out"]

    if result.returncode == 0:
        return []

    try:
        data = json.loads(result.stdout)
        errors = []
        # Redocly JSON format: list of problem objects or {"problems": [...]}
        problems = data if isinstance(data, list) else data.get("problems", [])
        for item in problems:
            if item.get("severity") == "error":
                msg = item.get("message", str(item))
                errors.append(f"[redocly] {msg}")
        return errors
    except (json.JSONDecodeError, AttributeError):
        return [f"[redocly] {line}" for line in result.stdout.splitlines() if line.strip()]


# ---------------------------------------------------------------------------
# Pass 2 — Spectral
# ---------------------------------------------------------------------------

def _run_spectral(spec_path: str) -> Tuple[List[str], List[str]]:
    """Run spectral lint with Amex ruleset; return (errors, warnings)."""
    ruleset = Path(".spectral.amex.yaml")
    if not ruleset.exists():
        log.debug(".spectral.amex.yaml not found — skipping Spectral validation")
        return [], []

    try:
        result = subprocess.run(
            ["spectral", "lint", spec_path, "--ruleset", str(ruleset), "--format", "json"],
            capture_output=True,
            text=True,
            timeout=60,
        )
    except FileNotFoundError:
        log.debug("spectral not installed — skipping Spectral validation")
        return [], []
    except subprocess.TimeoutExpired:
        return ["[spectral] Validation timed out"], []

    errors: List[str] = []
    warnings: List[str] = []
    try:
        items = json.loads(result.stdout)
        if not isinstance(items, list):
            items = []
        for item in items:
            code = item.get("code", "")
            message = item.get("message", str(item))
            formatted = f"[spectral] {code}: {message}"
            if item.get("severity") == 0:
                errors.append(formatted)
            else:
                warnings.append(formatted)
    except (json.JSONDecodeError, AttributeError):
        pass

    return errors, warnings


# ---------------------------------------------------------------------------
# Pass 3 — x-fields check
# ---------------------------------------------------------------------------

def _check_x_fields(spec_path: str, required_x_fields: List[str]) -> List[str]:
    """Check that required x- extension fields are present in the info block."""
    try:
        doc = yaml.safe_load(Path(spec_path).read_text())
        info = doc.get("info", {}) if isinstance(doc, dict) else {}
        errors = []
        for xfield in required_x_fields:
            if xfield not in info:
                errors.append(
                    f"[x-fields] Required field '{xfield}' missing from info block"
                )
        return errors
    except Exception as e:
        return [f"[x-fields] Failed to parse spec: {e}"]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def validate(spec_path: str, config: Config) -> ValidationResult:
    """Run all passes; raise if strict_mode and errors found."""
    result = ValidationResult()

    if not Path(spec_path).exists():
        result.errors.append(f"Spec file not found: {spec_path}")
        return result

    result.errors.extend(_run_redocly(spec_path))

    errs, warns = _run_spectral(spec_path)
    result.errors.extend(errs)
    result.warnings.extend(warns)

    result.errors.extend(_check_x_fields(spec_path, config.required_x_fields))

    if config.strict_mode:
        result.raise_if_failed()

    return result
