"""
Express / NestJS (TypeScript / JavaScript) scanner.

Parses router.get(), router.post(), app.get(), etc. calls and NestJS controller
decorators (@Controller, @Get, @Post, @Body, @Param) via a Node.js helper script
that uses @babel/parser. Invokes the helper as a subprocess and parses JSON output.
"""

import json
import logging
import re
import subprocess
from pathlib import Path
from typing import List, Optional

from spec_engine.models import RouteInfo, ParamInfo
from spec_engine.scanner.base import BaseScanner
from spec_engine.config import Config

log = logging.getLogger(__name__)

_SCRIPT_PATH = Path(__file__).parent / "express_ast.js"


class ExpressScanner(BaseScanner):
    """Scanner for Express / NestJS JavaScript/TypeScript applications."""

    EXTENSIONS = [".js", ".ts"]

    def scan(self) -> List[RouteInfo]:
        routes: List[RouteInfo] = []
        for file_path in self._iter_files():
            try:
                routes.extend(self._scan_file(file_path))
            except Exception as e:
                log.debug("Express: skipping %s: %s", file_path, e)
        return routes

    def _scan_file(self, file_path: Path) -> List[RouteInfo]:
        """Run the Node.js AST helper and parse JSON output."""
        try:
            result = subprocess.run(
                ["node", str(_SCRIPT_PATH), str(file_path)],
                capture_output=True,
                text=True,
                timeout=15,
            )
        except FileNotFoundError:
            log.debug("Express: node not found — skipping %s", file_path)
            return []
        except subprocess.TimeoutExpired:
            log.debug("Express: timeout parsing %s", file_path)
            return []

        stdout = (result.stdout or "").strip()
        if not stdout:
            return []

        try:
            raw_routes = json.loads(stdout)
        except json.JSONDecodeError as e:
            log.debug("Express: JSON parse error for %s: %s", file_path, e)
            return []

        if not isinstance(raw_routes, list):
            return []

        rel_path = str(file_path.relative_to(self.repo_path))
        routes: List[RouteInfo] = []

        for r in raw_routes:
            if not isinstance(r, dict):
                continue
            method = str(r.get("method", "")).upper()
            path = str(r.get("path", ""))
            handler = str(r.get("handler", "anonymous"))
            line = int(r.get("line", 1))

            if not method or not path:
                continue
            if not path.startswith("/"):
                path = "/" + path

            # Extract path params
            path_param_names = re.findall(r"\{(\w+)\}", path)
            params = [
                ParamInfo(name=p, location="path", required=True, schema={"type": "string"})
                for p in path_param_names
            ]

            try:
                routes.append(
                    RouteInfo(
                        method=method,
                        path=path,
                        handler=handler,
                        file=rel_path,
                        line=line,
                        framework="express",
                        params=params,
                    )
                )
            except (ValueError, TypeError) as e:
                log.debug("Express: invalid route from %s: %s", file_path, e)

        return routes
