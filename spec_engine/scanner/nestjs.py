"""
NestJS scanner.

Delegates to the Node.js express_ast.js helper (which already handles NestJS
controller decorators) when Node.js is available and relabels each route's
framework field as "nestjs". Falls back to a pure-Python regex scan when
Node.js is not installed.

Regex patterns recognised:
  @Controller('prefix')
  @Get(':id') / @Post() / @Put(':id') / @Patch(':id') / @Delete(':id')
"""

import dataclasses
import logging
import re
import subprocess
from pathlib import Path
from typing import List, Optional

from spec_engine.models import RouteInfo, ParamInfo
from spec_engine.scanner.base import BaseScanner
from spec_engine.config import Config

log = logging.getLogger(__name__)

# Regex patterns for NestJS TypeScript scanning
_CONTROLLER_RE = re.compile(r"@Controller\(\s*['\"]([^'\"]*)['\"]")
_HTTP_DEC_RE = re.compile(
    r"@(Get|Post|Put|Patch|Delete)\(\s*(?:['\"]([^'\"]*)['\"])?\s*\)"
)
_PARAM_COLON = re.compile(r":(\w+)")   # :id → {id}
_FUNC_NAME_RE = re.compile(r"(?:async\s+)?(\w+)\s*\(")


def _normalise_path(path: str) -> str:
    """Ensure path starts with / and colon params become {param}."""
    if not path.startswith("/"):
        path = "/" + path
    path = _PARAM_COLON.sub(r"{\1}", path)
    return path


def _join_paths(prefix: str, suffix: str) -> str:
    prefix = prefix.rstrip("/")
    suffix = suffix.lstrip("/")
    result = prefix + "/" + suffix if suffix else prefix
    return _normalise_path(result)


def _node_available() -> bool:
    """Return True if `node` is on PATH."""
    try:
        subprocess.run(
            ["node", "--version"],
            capture_output=True,
            timeout=5,
        )
        return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


class NestJSScanner(BaseScanner):
    """Scanner for NestJS TypeScript applications."""

    EXTENSIONS = [".ts", ".js"]

    def scan(self) -> List[RouteInfo]:
        if _node_available():
            return self._scan_via_express()
        return self._regex_scan()

    # ------------------------------------------------------------------
    # Node.js delegation path
    # ------------------------------------------------------------------

    def _scan_via_express(self) -> List[RouteInfo]:
        """Delegate to ExpressScanner and relabel framework='nestjs'."""
        from spec_engine.scanner.express import ExpressScanner

        express_scanner = ExpressScanner(str(self.repo_path), self.config)
        routes = express_scanner.scan()
        return [
            dataclasses.replace(r, framework="nestjs")
            for r in routes
        ]

    # ------------------------------------------------------------------
    # Pure Python regex fallback
    # ------------------------------------------------------------------

    def _regex_scan(self) -> List[RouteInfo]:
        routes: List[RouteInfo] = []
        for file_path in self._iter_files():
            try:
                routes.extend(self._scan_file_regex(file_path))
            except Exception as e:
                log.debug("NestJS: skipping %s: %s", file_path, e)
        return routes

    def _scan_file_regex(self, file_path: Path) -> List[RouteInfo]:
        """Scan a single .ts/.js file using Python regex patterns."""
        try:
            text = file_path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return []

        # Find @Controller prefix
        ctrl_m = _CONTROLLER_RE.search(text)
        if not ctrl_m:
            return []
        controller_prefix = _normalise_path(ctrl_m.group(1))

        try:
            rel_path = str(file_path.relative_to(self.repo_path))
        except ValueError:
            rel_path = str(file_path)

        routes: List[RouteInfo] = []
        lines = text.splitlines()

        i = 0
        while i < len(lines):
            line = lines[i]
            dec_m = _HTTP_DEC_RE.search(line)
            if dec_m:
                http_method = dec_m.group(1).upper()
                route_suffix = dec_m.group(2) or ""
                full_path = _join_paths(controller_prefix, route_suffix)

                # Look ahead up to 5 lines for the handler function name
                handler = "anonymous"
                for j in range(i + 1, min(i + 6, len(lines))):
                    fn_m = _FUNC_NAME_RE.search(lines[j])
                    if fn_m:
                        handler = fn_m.group(1)
                        break

                # Extract path params
                path_param_names = re.findall(r"\{(\w+)\}", full_path)
                params = [
                    ParamInfo(
                        name=p,
                        location="path",
                        required=True,
                        schema={"type": "string"},
                    )
                    for p in path_param_names
                ]

                try:
                    routes.append(
                        RouteInfo(
                            method=http_method,
                            path=full_path,
                            handler=handler,
                            file=rel_path,
                            line=i + 1,
                            framework="nestjs",
                            params=params,
                        )
                    )
                except (ValueError, TypeError) as e:
                    log.debug("NestJS: invalid route in %s line %d: %s", file_path, i + 1, e)

            i += 1

        return routes
