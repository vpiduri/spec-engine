"""
Stage 1 — Repo Scanner package.

Auto-detects the API framework in a repository and dispatches to the appropriate
framework-specific scanner to extract route information from source files.

Usage:
  from spec_engine.scanner import get_scanner, detect_framework
  scanner = get_scanner(repo_path, config)
  routes  = scanner.scan()
"""

import logging
from pathlib import Path

from spec_engine.scanner.base import BaseScanner
from spec_engine.config import Config

log = logging.getLogger(__name__)


def detect_framework(repo_path: str) -> str:
    """
    Auto-detect the API framework used in a repository.

    Check order: go.mod → pom.xml/build.gradle → requirements.txt/pyproject.toml → package.json
    Returns lowercase framework name: gin, echo, spring, fastapi, django, nestjs, express, unknown.
    """
    root = Path(repo_path)

    # Go
    go_mod = root / "go.mod"
    if go_mod.exists():
        content = go_mod.read_text(errors="ignore").lower()
        if "github.com/labstack/echo" in content:
            return "echo"
        return "gin"

    # Java / Spring
    if (root / "pom.xml").exists() or (root / "build.gradle").exists():
        return "spring"

    # Python
    for fname in ("requirements.txt", "pyproject.toml"):
        candidate = root / fname
        if candidate.exists():
            content = candidate.read_text(errors="ignore").lower()
            if "django" in content:
                return "django"
            if "fastapi" in content:
                return "fastapi"
            return "fastapi"  # default Python framework

    # Node.js
    pkg = root / "package.json"
    if pkg.exists():
        content = pkg.read_text(errors="ignore").lower()
        if "@nestjs" in content or '"nestjs"' in content:
            return "nestjs"
        return "express"

    return "unknown"


def get_scanner(repo_path: str, config: Config) -> BaseScanner:
    """
    Return the appropriate scanner instance for the repository.

    Checks config.framework first (if set via getattr), then calls detect_framework().
    """
    framework = getattr(config, "framework", "") or detect_framework(repo_path)
    framework = (framework or "").lower()

    log.info("Using framework scanner: %s", framework)

    if framework == "spring":
        from spec_engine.scanner.spring import SpringScanner
        return SpringScanner(repo_path, config)
    elif framework == "fastapi":
        from spec_engine.scanner.fastapi import FastAPIScanner
        return FastAPIScanner(repo_path, config)
    elif framework == "django":
        from spec_engine.scanner.django import DjangoScanner
        return DjangoScanner(repo_path, config)
    elif framework == "express":
        from spec_engine.scanner.express import ExpressScanner
        return ExpressScanner(repo_path, config)
    elif framework == "nestjs":
        from spec_engine.scanner.nestjs import NestJSScanner
        return NestJSScanner(repo_path, config)
    elif framework in ("gin", "echo"):
        from spec_engine.scanner.gin import GinScanner
        return GinScanner(repo_path, config)
    else:
        raise ValueError(
            f"Unknown or unsupported framework: {framework!r}. "
            "Supported: spring, fastapi, django, express, nestjs, gin, echo."
        )
