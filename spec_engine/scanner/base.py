"""
Base scanner class.

All framework-specific scanners inherit from BaseScanner and must implement scan().
The base class provides shared utilities: file discovery, path filtering, and
framework-agnostic route deduplication.
"""

from abc import ABC, abstractmethod
import logging
from fnmatch import fnmatch
from pathlib import Path
from typing import List, Set

from spec_engine.models import RouteInfo
from spec_engine.config import Config

log = logging.getLogger(__name__)

SKIP_DIRS: Set[str] = {
    ".git", "node_modules", "__pycache__", "target", "build",
    "dist", ".idea", ".vscode", ".pytest_cache",
}


class BaseScanner(ABC):
    """Abstract base class for all framework-specific scanners."""

    EXTENSIONS: List[str] = []

    def __init__(self, repo_path: str, config: Config) -> None:
        self.repo_path = Path(repo_path)
        self.config = config

    @abstractmethod
    def scan(self) -> List[RouteInfo]:
        """Scan the repository and return a list of discovered routes."""

    def _iter_files(self) -> List[Path]:
        """
        Discover source files for this scanner's extensions.

        Skip rules:
          - Any parent directory that starts with "." or is in SKIP_DIRS
          - Paths matching config.exclude_paths glob patterns
        Deduplication via a seen set (rglob may yield duplicates across extensions).
        """
        seen: Set[Path] = set()
        results: List[Path] = []

        for ext in self.EXTENSIONS:
            for path in self.repo_path.rglob(f"*{ext}"):
                try:
                    rel = path.relative_to(self.repo_path)
                except ValueError:
                    continue

                # Check parent directory components
                skip = False
                for part in rel.parts[:-1]:  # all parts except the filename
                    if part.startswith(".") or part in SKIP_DIRS:
                        skip = True
                        break
                if skip:
                    continue

                # Respect config.exclude_paths glob patterns
                rel_str = str(rel)
                if any(fnmatch(rel_str, pat) for pat in getattr(self.config, "exclude_paths", [])):
                    continue

                if path not in seen:
                    seen.add(path)
                    log.debug("Scanner found file: %s", path)
                    results.append(path)

        return results
