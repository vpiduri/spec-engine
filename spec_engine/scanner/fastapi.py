"""
FastAPI (Python) scanner.

Parses @app.get(), @app.post(), @router.get(), @router.post(), etc. decorators
using Python's built-in ast module (no external dependencies). Resolves router
prefixes by tracing include_router() calls and APIRouter(prefix=...) arguments.
"""

import ast
import logging
import re
from pathlib import Path
from typing import Dict, List, Optional, Set

from spec_engine.models import RouteInfo, ParamInfo
from spec_engine.scanner.base import BaseScanner
from spec_engine.config import Config

log = logging.getLogger(__name__)

_HTTP_METHODS = {"get", "post", "put", "delete", "patch", "head", "options"}
_ROUTER_TYPES = {"APIRouter", "FastAPI"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ast_str(node: ast.expr) -> Optional[str]:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _get_keyword(keywords: List[ast.keyword], name: str) -> Optional[ast.expr]:
    for kw in keywords:
        if kw.arg == name:
            return kw.value
    return None


# ---------------------------------------------------------------------------
# FastAPIScanner
# ---------------------------------------------------------------------------

class FastAPIScanner(BaseScanner):
    """Scanner for FastAPI Python applications."""

    EXTENSIONS = [".py"]

    def scan(self) -> List[RouteInfo]:
        # Global pre-pass: collect all BaseModel subclasses across the repo
        global_model_classes: Set[str] = set()
        for file_path in self._iter_files():
            try:
                source = file_path.read_text(encoding="utf-8", errors="ignore")
                tree = ast.parse(source, filename=str(file_path))
                global_model_classes.update(self._find_model_classes(tree))
            except Exception:
                pass

        routes: List[RouteInfo] = []
        for file_path in self._iter_files():
            try:
                routes.extend(self._scan_file(file_path, global_model_classes))
            except Exception as e:
                log.debug("FastAPI: skipping %s: %s", file_path, e)
        return routes

    def _scan_file(self, file_path: Path, global_model_classes: Optional[Set[str]] = None) -> List[RouteInfo]:
        source = file_path.read_text(encoding="utf-8", errors="ignore")
        try:
            tree = ast.parse(source, filename=str(file_path))
        except SyntaxError as e:
            log.debug("FastAPI: parse error in %s: %s", file_path, e)
            return []

        rel_path = str(file_path.relative_to(self.repo_path))
        # Merge file-local model classes with global ones
        file_model_classes: Set[str] = self._find_model_classes(tree)
        model_classes = file_model_classes | (global_model_classes or set())
        router_names: Dict[str, str] = self._find_router_vars(tree)

        routes: List[RouteInfo] = []
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for dec in node.decorator_list:
                route = self._parse_decorator(dec, node, router_names, model_classes, rel_path)
                if route:
                    routes.append(route)
                    break  # one decorator per function

        return routes

    def _find_model_classes(self, tree: ast.Module) -> Set[str]:
        """Pre-pass: collect class names inheriting from BaseModel or similar."""
        model_classes: Set[str] = set()
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            for base in node.bases:
                base_name = None
                if isinstance(base, ast.Name):
                    base_name = base.id
                elif isinstance(base, ast.Attribute):
                    base_name = base.attr
                if base_name in ("BaseModel", "Schema", "SQLModel"):
                    model_classes.add(node.name)
                    break
        return model_classes

    def _find_router_vars(self, tree: ast.Module) -> Dict[str, str]:
        """Pre-pass: find APIRouter/FastAPI assignments → {var_name: prefix}."""
        router_names: Dict[str, str] = {}
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign):
                continue
            call = node.value
            if not isinstance(call, ast.Call):
                continue
            func_name = None
            if isinstance(call.func, ast.Name):
                func_name = call.func.id
            elif isinstance(call.func, ast.Attribute):
                func_name = call.func.attr
            if func_name not in _ROUTER_TYPES:
                continue
            prefix = ""
            prefix_node = _get_keyword(call.keywords, "prefix")
            if prefix_node is not None:
                prefix = _ast_str(prefix_node) or ""
            for target in node.targets:
                if isinstance(target, ast.Name):
                    router_names[target.id] = prefix
        return router_names

    def _parse_decorator(
        self,
        dec: ast.expr,
        func: ast.FunctionDef,
        router_names: Dict[str, str],
        model_classes: Set[str],
        rel_path: str,
    ) -> Optional[RouteInfo]:
        """Parse a decorator as a route definition, or return None."""
        if not isinstance(dec, ast.Call):
            return None
        call = dec
        if not isinstance(call.func, ast.Attribute):
            return None
        method_name = call.func.attr.lower()
        if method_name not in _HTTP_METHODS:
            return None
        obj = call.func.value
        if not isinstance(obj, ast.Name):
            return None
        router_var = obj.id
        if router_var not in router_names:
            return None
        if not call.args:
            return None
        path_suffix = _ast_str(call.args[0])
        if path_suffix is None:
            return None

        prefix = router_names[router_var]
        full_path = self._join_path(prefix, path_suffix)

        params = self._extract_params(func, full_path, model_classes)
        request_body_type = self._extract_request_body(func, model_classes)

        response_type: Optional[str] = None
        resp_node = _get_keyword(call.keywords, "response_model")
        if resp_node is not None:
            response_type = self._extract_type_name(resp_node)

        tags: List[str] = []
        tags_node = _get_keyword(call.keywords, "tags")
        if tags_node is not None and isinstance(tags_node, ast.List):
            for elt in tags_node.elts:
                s = _ast_str(elt)
                if s:
                    tags.append(s)

        summary = func.name.replace("_", " ").title()

        return RouteInfo(
            method=method_name.upper(),
            path=full_path,
            handler=func.name,
            file=rel_path,
            line=func.lineno,
            framework="fastapi",
            params=params,
            request_body_type=request_body_type,
            response_type=response_type,
            tags=tags,
            summary=summary,
        )

    def _extract_type_name(self, node: ast.expr) -> Optional[str]:
        """Extract a type name from a Name, Attribute, or Subscript node."""
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            return node.attr
        if isinstance(node, ast.Subscript):
            inner = node.slice
            if isinstance(inner, ast.Name):
                return inner.id
            if isinstance(inner, ast.Index):  # type: ignore[attr-defined]
                idx = inner.value  # type: ignore[attr-defined]
                if isinstance(idx, ast.Name):
                    return idx.id
        return None

    def _join_path(self, prefix: str, suffix: str) -> str:
        prefix = (prefix or "").rstrip("/")
        suffix = (suffix or "").lstrip("/")
        result = prefix + "/" + suffix if suffix else prefix
        if not result.startswith("/"):
            result = "/" + result
        result = result.rstrip("/")
        return result or "/"

    # Framework-injected types that are not request body or params
    _FRAMEWORK_TYPES = {
        "Request", "Response", "HTTPConnection", "BackgroundTasks",
        "Depends", "Session", "AsyncSession", "Connection",
    }

    def _extract_params(
        self,
        func: ast.FunctionDef,
        path: str,
        model_classes: Set[str],
    ) -> List[ParamInfo]:
        """Extract path and query parameters from function signature."""
        params: List[ParamInfo] = []
        path_param_names = set(re.findall(r"\{(\w+)\}", path))

        args = func.args.args
        defaults = func.args.defaults
        default_map: Dict[str, ast.expr] = {}
        offset = len(args) - len(defaults)
        for i, default in enumerate(defaults):
            default_map[args[offset + i].arg] = default

        for arg in args:
            name = arg.arg
            if name in ("self", "cls", "db", "session"):
                continue
            annotation = arg.annotation
            type_name = self._resolve_annotation_name(annotation)
            # Skip framework-injected types
            if type_name in self._FRAMEWORK_TYPES:
                continue
            # Skip Pydantic model classes (they're request bodies)
            if type_name in model_classes:
                continue

            default = default_map.get(name)
            is_path_param = name in path_param_names

            if default is not None and isinstance(default, ast.Call):
                func_name = None
                if isinstance(default.func, ast.Name):
                    func_name = default.func.id
                elif isinstance(default.func, ast.Attribute):
                    func_name = default.func.attr
                if func_name == "Path":
                    is_path_param = True

            if is_path_param:
                location = "path"
                required = True
            else:
                location = "query"
                required = default is None

            schema = self._type_name_to_schema(type_name)
            params.append(
                ParamInfo(name=name, location=location, required=required, schema=schema)
            )

        return params

    def _extract_request_body(
        self, func: ast.FunctionDef, model_classes: Set[str]
    ) -> Optional[str]:
        """Return type name of the first BaseModel parameter."""
        for arg in func.args.args:
            if arg.arg in ("self", "cls", "db", "session"):
                continue
            type_name = self._resolve_annotation_name(arg.annotation)
            if type_name in self._FRAMEWORK_TYPES:
                continue
            if type_name in model_classes:
                return type_name
        return None

    def _resolve_annotation_name(self, annotation: Optional[ast.expr]) -> Optional[str]:
        """Extract a simple type name from an annotation node."""
        if annotation is None:
            return None
        if isinstance(annotation, ast.Name):
            return annotation.id
        if isinstance(annotation, ast.Attribute):
            return annotation.attr
        if isinstance(annotation, ast.Subscript):
            inner = annotation.slice
            if isinstance(inner, ast.Name):
                return inner.id
            if isinstance(inner, ast.Index):  # type: ignore[attr-defined]
                idx = inner.value  # type: ignore[attr-defined]
                if isinstance(idx, ast.Name):
                    return idx.id
        return None

    def _type_name_to_schema(self, type_name: Optional[str]) -> dict:
        _map = {
            "str": {"type": "string"},
            "int": {"type": "integer"},
            "float": {"type": "number"},
            "bool": {"type": "boolean"},
            "datetime": {"type": "string", "format": "date-time"},
            "date": {"type": "string", "format": "date"},
            "UUID": {"type": "string", "format": "uuid"},
        }
        return _map.get(type_name or "", {"type": "string"})
