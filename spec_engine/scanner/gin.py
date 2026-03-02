"""
Gin / Echo (Go) scanner.

Parses router.GET(), router.POST(), router.Group(), and nested route groups
in Go source files. Uses regex-based heuristics (no external Go dependency)
with a subprocess fallback to `go/ast` when precision is required.
"""

import json
import logging
import re
import subprocess
import tempfile
from pathlib import Path
from typing import List, Optional

from spec_engine.models import RouteInfo, ParamInfo
from spec_engine.scanner.base import BaseScanner
from spec_engine.config import Config

log = logging.getLogger(__name__)

_GO_SOURCE = Path(__file__).parent / "gin_ast.go"
_HTTP_METHODS = {"GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"}

# Regex for direct route registrations: r.GET("/path", handler)
_ROUTE_RE = re.compile(
    r'\.(%s)\s*\(\s*"([^"]+)"' % "|".join(_HTTP_METHODS),
    re.IGNORECASE,
)

# Regex for Group: r.Group("/prefix")
_GROUP_RE = re.compile(r'\.Group\s*\(\s*"([^"]+)"')


class GinScanner(BaseScanner):
    """Scanner for Gin / Echo Go applications."""

    EXTENSIONS = [".go"]

    def __init__(self, repo_path: str, config: Config) -> None:
        super().__init__(repo_path, config)
        self._ast_binary: Optional[Path] = self._compile_ast_tool()
        self._warned = False

    def _compile_ast_tool(self) -> Optional[Path]:
        """
        Compile gin_ast.go to a temporary binary.
        Returns None if Go toolchain is not available.
        """
        if not _GO_SOURCE.exists():
            log.debug("GinScanner: gin_ast.go not found at %s", _GO_SOURCE)
            return None

        try:
            with tempfile.NamedTemporaryFile(suffix="", delete=False, prefix="gin_ast_tool_") as f:
                binary_path = Path(f.name)

            result = subprocess.run(
                ["go", "build", "-o", str(binary_path), str(_GO_SOURCE)],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                log.debug("GinScanner: go build failed: %s", result.stderr)
                binary_path.unlink(missing_ok=True)
                return None

            log.debug("GinScanner: compiled AST tool to %s", binary_path)
            return binary_path

        except FileNotFoundError:
            log.debug("GinScanner: go toolchain not found — using regex fallback")
            return None
        except subprocess.TimeoutExpired:
            log.debug("GinScanner: go build timed out")
            return None
        except Exception as e:
            log.debug("GinScanner: compilation error: %s", e)
            return None

    def scan(self) -> List[RouteInfo]:
        routes: List[RouteInfo] = []
        for file_path in self._iter_files():
            try:
                routes.extend(self._scan_file(file_path))
            except Exception as e:
                log.debug("Gin: skipping %s: %s", file_path, e)
        return routes

    def _scan_file(self, file_path: Path) -> List[RouteInfo]:
        if self._ast_binary is not None:
            return self._scan_with_binary(file_path)
        else:
            if not self._warned:
                log.warning("GinScanner: Go toolchain unavailable; using regex fallback")
                self._warned = True
            return self._scan_with_regex(file_path)

    def _scan_with_binary(self, file_path: Path) -> List[RouteInfo]:
        """Use the compiled Go AST binary to parse routes."""
        if self._ast_binary is None:
            return []
        try:
            result = subprocess.run(
                [str(self._ast_binary), str(file_path)],
                capture_output=True,
                text=True,
                timeout=15,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired) as e:
            log.debug("Gin: binary failed for %s: %s", file_path, e)
            return self._scan_with_regex(file_path)

        stdout = (result.stdout or "").strip()
        if not stdout:
            return []

        try:
            raw_routes = json.loads(stdout)
        except json.JSONDecodeError:
            return self._scan_with_regex(file_path)

        return self._build_routes(raw_routes, file_path)

    def _scan_with_regex(self, file_path: Path) -> List[RouteInfo]:
        """Regex-based fallback route extraction from Go source."""
        source = file_path.read_text(encoding="utf-8", errors="ignore")
        routes_raw: List[dict] = []

        lines = source.splitlines()
        # Track current group prefix via simple heuristics
        prefix_stack: List[str] = [""]

        for i, line in enumerate(lines, start=1):
            # Group push
            group_match = _GROUP_RE.search(line)
            if group_match:
                group_prefix = group_match.group(1)
                current = prefix_stack[-1] if prefix_stack else ""
                prefix_stack.append(self._join_path(current, group_prefix))
                continue

            # Route
            for route_match in _ROUTE_RE.finditer(line):
                method = route_match.group(1).upper()
                path = route_match.group(2)
                current_prefix = prefix_stack[-1] if prefix_stack else ""
                full_path = self._join_path(current_prefix, path)
                routes_raw.append({"method": method, "path": full_path, "handler": "handler", "line": i})

        return self._build_routes(routes_raw, file_path)

    def _join_path(self, prefix: str, suffix: str) -> str:
        # Convert :param → {param}
        def normalize(p: str) -> str:
            return re.sub(r":(\w+)", r"{\1}", p)
        prefix = normalize(prefix).rstrip("/")
        suffix = normalize(suffix).lstrip("/")
        result = prefix + "/" + suffix if suffix else prefix
        if not result.startswith("/"):
            result = "/" + result
        return result.rstrip("/") or "/"

    def _build_routes(self, raw_routes: List[dict], file_path: Path) -> List[RouteInfo]:
        """Convert raw dicts to RouteInfo objects."""
        routes: List[RouteInfo] = []
        rel_path = str(file_path.relative_to(self.repo_path))

        for r in raw_routes:
            method = str(r.get("method", "")).upper()
            path = str(r.get("path", ""))
            handler = str(r.get("handler", "anonymous"))
            line = int(r.get("line", 1))

            if method not in _HTTP_METHODS or not path:
                continue
            if not path.startswith("/"):
                path = "/" + path

            path_params = [
                ParamInfo(name=p, location="path", required=True, schema={"type": "string"})
                for p in re.findall(r"\{(\w+)\}", path)
            ]

            try:
                routes.append(RouteInfo(
                    method=method,
                    path=path,
                    handler=handler,
                    file=rel_path,
                    line=line,
                    framework="gin",
                    params=path_params,
                ))
            except (ValueError, TypeError) as e:
                log.debug("Gin: invalid route: %s", e)

        return routes
