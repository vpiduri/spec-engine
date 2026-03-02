"""
Django REST Framework scanner.

Parses urlpatterns lists, path() / re_path() calls, and @api_view / ViewSet
routers to extract routes. Also handles @action decorators with url_path arguments.
Two-pass approach:
  Pass 1: scan all urls.py → populate viewset and api_view mappings
  Pass 2: scan all views.py → use mappings to build routes
"""

import ast
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple  # noqa: F401

from spec_engine.models import RouteInfo, ParamInfo
from spec_engine.scanner.base import BaseScanner
from spec_engine.config import Config

log = logging.getLogger(__name__)

# DRF ModelViewSet standard routes (basename → [(method, path_suffix, action)])
_VIEWSET_ROUTES = [
    ("GET",    "",        "list"),
    ("POST",   "",        "create"),
    ("GET",    "/{pk}",   "retrieve"),
    ("PUT",    "/{pk}",   "update"),
    ("PATCH",  "/{pk}",   "partial_update"),
    ("DELETE", "/{pk}",   "destroy"),
]

_HTTP_METHODS = {"get", "post", "put", "delete", "patch", "head", "options"}

# Mixin → set of standard actions it provides
_MIXIN_ROUTE_MAP: Dict[str, Set[str]] = {
    "ModelViewSet":         {"list", "create", "retrieve", "update", "partial_update", "destroy"},
    "ReadOnlyModelViewSet": {"list", "retrieve"},
    "ViewSet":              set(),
    "GenericViewSet":       set(),
    "ViewSetMixin":         set(),
    "ListModelMixin":       {"list"},
    "CreateModelMixin":     {"create"},
    "RetrieveModelMixin":   {"retrieve"},
    "UpdateModelMixin":     {"update", "partial_update"},
    "DestroyModelMixin":    {"destroy"},
}


def _compute_allowed_actions(bases: List[str]) -> Set[str]:
    """Union of actions provided by each base class in the MRO."""
    allowed: Set[str] = set()
    for base in bases:
        allowed |= _MIXIN_ROUTE_MAP.get(base, set())
    return allowed


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


def _convert_django_path(path_str: str) -> str:
    """Convert Django path converters to OpenAPI path params."""
    # <str:account_id> or <int:pk> or <account_id> → {account_id}
    result = re.sub(r"<(?:\w+:)?(\w+)>", r"{\1}", path_str)
    if not result.startswith("/"):
        result = "/" + result
    return result


def _join_path(prefix: str, suffix: str) -> str:
    prefix = (prefix or "").rstrip("/")
    suffix = (suffix or "").lstrip("/")
    result = prefix + "/" + suffix if suffix else prefix
    if not result.startswith("/"):
        result = "/" + result
    result = result.rstrip("/")
    return result or "/"


# ---------------------------------------------------------------------------
# DjangoScanner
# ---------------------------------------------------------------------------

class DjangoScanner(BaseScanner):
    """Scanner for Django REST Framework applications. Two-pass approach."""

    EXTENSIONS = [".py"]

    def scan(self) -> List[RouteInfo]:
        """
        Two-pass scan:
          Pass 1: collect URL → ViewSet/View mappings from urls.py files.
          Pass 2: use mappings with view definitions to produce routes.
        """
        # Pass 1: parse all urls.py
        url_mappings: List[Dict] = []
        for file_path in self._iter_files():
            if file_path.name not in ("urls.py",):
                continue
            try:
                url_mappings.extend(self._parse_urls_file(file_path))
            except Exception as e:
                log.debug("Django: urls.py parse error %s: %s", file_path, e)

        if not url_mappings:
            return []

        # Build a lookup: class_name → view info from views.py
        view_info: Dict[str, Dict] = {}
        for file_path in self._iter_files():
            if file_path.name not in ("views.py", "viewsets.py", "api.py"):
                continue
            try:
                info = self._parse_views_file(file_path)
                view_info.update(info)
            except Exception as e:
                log.debug("Django: views.py parse error %s: %s", file_path, e)

        # Pass 2: combine URL mappings with view info to produce routes
        routes: List[RouteInfo] = []
        for mapping in url_mappings:
            routes.extend(self._build_routes(mapping, view_info))

        return routes

    # -----------------------------------------------------------------------
    # Pass 1: URL pattern parsing
    # -----------------------------------------------------------------------

    def _parse_urls_file(self, file_path: Path) -> List[Dict]:
        """
        Parse a urls.py file and return a list of URL mapping dicts:
          {type: "viewset", path, class_name, basename, source_file}
          {type: "apiview", path, class_name, source_file}
          {type: "function", path, method, handler, source_file}
        """
        source = file_path.read_text(encoding="utf-8", errors="ignore")
        try:
            tree = ast.parse(source, filename=str(file_path))
        except SyntaxError:
            return []

        rel_path = str(file_path.relative_to(self.repo_path))
        mappings: List[Dict] = []

        # Pre-pass: identify router variable types (simple vs nested)
        router_vars: Dict[str, Dict] = {}
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign):
                continue
            if not isinstance(node.value, ast.Call):
                continue
            func = node.value.func
            func_name = (
                func.id if isinstance(func, ast.Name)
                else func.attr if isinstance(func, ast.Attribute)
                else None
            )
            if func_name in ("DefaultRouter", "SimpleRouter"):
                for t in node.targets:
                    if isinstance(t, ast.Name):
                        router_vars[t.id] = {"type": "simple"}
            elif func_name in ("NestedSimpleRouter", "NestedDefaultRouter"):
                args = node.value.args
                parent_prefix = ""
                if len(args) >= 2:
                    parent_prefix = (_ast_str(args[1]) or "").strip("/")
                lookup_kw = _get_keyword(node.value.keywords, "lookup")
                lookup_val = _ast_str(lookup_kw) if lookup_kw else "pk"
                lookup_field = lookup_val + "_pk"
                for t in node.targets:
                    if isinstance(t, ast.Name):
                        router_vars[t.id] = {
                            "type": "nested",
                            "parent_prefix": parent_prefix,
                            "lookup_field": lookup_field,
                        }

        for node in ast.walk(tree):
            # router.register(r'accounts', AccountViewSet, basename='account')
            if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
                call = node.value
                if isinstance(call.func, ast.Attribute) and call.func.attr == "register":
                    # Get the variable name the register() is called on
                    var_name = (
                        call.func.value.id
                        if isinstance(call.func.value, ast.Name) else None
                    )
                    m = self._parse_router_register(call, rel_path)
                    if m and var_name:
                        rinfo = router_vars.get(var_name, {"type": "simple"})
                        if rinfo.get("type") == "nested":
                            parent = rinfo["parent_prefix"]
                            lookup = rinfo["lookup_field"]
                            child = m["path"].lstrip("/")
                            m["path"] = f"{parent}/{{{lookup}}}/{child}"
                    if m:
                        mappings.append(m)

            # path('accounts/', AccountView.as_view()) or path('accounts/', handler)
            if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
                pass  # handled below via urlpatterns assignment

        # Look at urlpatterns list for path() / re_path() calls
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign):
                continue
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "urlpatterns":
                    if isinstance(node.value, ast.List):
                        for elt in node.value.elts:
                            m = self._parse_urlpatterns_entry(elt, rel_path)
                            if m:
                                mappings.append(m)

        return mappings

    def _parse_router_register(self, call: ast.Call, rel_path: str) -> Optional[Dict]:
        """Parse router.register(r'prefix', ViewSetClass, basename='...')"""
        if len(call.args) < 2:
            return None
        prefix = _ast_str(call.args[0])
        view_node = call.args[1]
        class_name = None
        if isinstance(view_node, ast.Name):
            class_name = view_node.id
        elif isinstance(view_node, ast.Attribute):
            class_name = view_node.attr
        if not prefix or not class_name:
            return None
        basename_node = _get_keyword(call.keywords, "basename")
        basename = _ast_str(basename_node) if basename_node else class_name.lower().replace("viewset", "")
        return {
            "type": "viewset",
            "path": prefix,
            "class_name": class_name,
            "basename": basename,
            "source_file": rel_path,
        }

    def _parse_urlpatterns_entry(self, node: ast.expr, rel_path: str) -> Optional[Dict]:
        """Parse a path() or re_path() entry from urlpatterns."""
        if not isinstance(node, ast.Call):
            return None
        func_name = None
        if isinstance(node.func, ast.Name):
            func_name = node.func.id
        elif isinstance(node.func, ast.Attribute):
            func_name = node.func.attr

        if func_name not in ("path", "re_path", "url"):
            return None
        if len(node.args) < 2:
            return None

        path_str = _ast_str(node.args[0])
        view_node = node.args[1]
        if path_str is None:
            return None

        openapi_path = _convert_django_path(path_str)

        # Check for .as_view() call
        if isinstance(view_node, ast.Call):
            call = view_node
            if isinstance(call.func, ast.Attribute) and call.func.attr == "as_view":
                class_node = call.func.value
                class_name = None
                if isinstance(class_node, ast.Name):
                    class_name = class_node.id
                elif isinstance(class_node, ast.Attribute):
                    class_name = class_node.attr
                if class_name:
                    return {
                        "type": "apiview",
                        "path": openapi_path,
                        "class_name": class_name,
                        "source_file": rel_path,
                    }

        return None

    # -----------------------------------------------------------------------
    # Pass 2: View class parsing
    # -----------------------------------------------------------------------

    def _parse_views_file(self, file_path: Path) -> Dict[str, Dict]:
        """
        Parse a views.py file. Returns {class_name: {type, methods, actions}}.
        """
        source = file_path.read_text(encoding="utf-8", errors="ignore")
        try:
            tree = ast.parse(source, filename=str(file_path))
        except SyntaxError:
            return {}

        rel_path = str(file_path.relative_to(self.repo_path))
        view_info: Dict[str, Dict] = {}

        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            class_type = self._classify_view(node)
            if not class_type:
                continue

            methods: List[str] = []
            actions: List[Dict] = []  # @action decorators

            for item in node.body:
                if not isinstance(item, ast.FunctionDef):
                    continue
                method_name = item.name.lower()
                if method_name in _HTTP_METHODS:
                    methods.append(method_name.upper())
                # @action decorator
                action = self._parse_action_decorator(item, rel_path)
                if action:
                    actions.append(action)

            viewset_bases = []
            for base in node.bases:
                base_name = (
                    base.id if isinstance(base, ast.Name)
                    else base.attr if isinstance(base, ast.Attribute)
                    else None
                )
                if base_name:
                    viewset_bases.append(base_name)

            view_info[node.name] = {
                "type": class_type,
                "methods": methods,
                "actions": actions,
                "source_file": rel_path,
                "line": node.lineno,
                "viewset_bases": viewset_bases,
            }

        return view_info

    def _classify_view(self, node: ast.ClassDef) -> Optional[str]:
        """Return 'viewset', 'apiview', or None."""
        for base in node.bases:
            name = None
            if isinstance(base, ast.Name):
                name = base.id
            elif isinstance(base, ast.Attribute):
                name = base.attr
            if name in _MIXIN_ROUTE_MAP:
                return "viewset"
            if name in ("APIView", "GenericAPIView", "ListAPIView", "CreateAPIView",
                        "RetrieveAPIView", "UpdateAPIView", "DestroyAPIView",
                        "ListCreateAPIView", "RetrieveUpdateAPIView",
                        "RetrieveDestroyAPIView", "RetrieveUpdateDestroyAPIView"):
                return "apiview"
        return None

    def _parse_action_decorator(
        self, method_node: ast.FunctionDef, rel_path: str
    ) -> Optional[Dict]:
        """Parse @action(detail=True, methods=['post'], url_path='activate')."""
        for dec in method_node.decorator_list:
            if not isinstance(dec, ast.Call):
                continue
            func_name = None
            if isinstance(dec.func, ast.Name):
                func_name = dec.func.id
            elif isinstance(dec.func, ast.Attribute):
                func_name = dec.func.attr
            if func_name != "action":
                continue

            detail = False
            detail_node = _get_keyword(dec.keywords, "detail")
            if detail_node is not None and isinstance(detail_node, ast.Constant):
                detail = bool(detail_node.value)

            methods: List[str] = ["GET"]
            methods_node = _get_keyword(dec.keywords, "methods")
            if methods_node is not None and isinstance(methods_node, ast.List):
                methods = []
                for elt in methods_node.elts:
                    s = _ast_str(elt)
                    if s:
                        methods.append(s.upper())

            url_path_node = _get_keyword(dec.keywords, "url_path")
            url_path = _ast_str(url_path_node) if url_path_node else method_node.name.replace("_", "-")

            return {
                "detail": detail,
                "methods": methods,
                "url_path": url_path,
                "handler": method_node.name,
                "line": method_node.lineno,
            }

        return None

    # -----------------------------------------------------------------------
    # Route building
    # -----------------------------------------------------------------------

    def _build_routes(
        self, mapping: Dict, view_info: Dict[str, Dict]
    ) -> List[RouteInfo]:
        """Produce RouteInfo objects from a URL mapping + view class info."""
        routes: List[RouteInfo] = []
        class_name = mapping.get("class_name", "")
        base_path = mapping.get("path", "")
        source_file = mapping.get("source_file", "")
        mapping_type = mapping.get("type", "")

        info = view_info.get(class_name, {})
        view_source = info.get("source_file", source_file)
        view_line = info.get("line", 1)

        if mapping_type == "viewset":
            # Determine which standard actions this ViewSet supports via its bases
            viewset_bases = info.get("viewset_bases", ["ModelViewSet"])
            allowed = _compute_allowed_actions(viewset_bases)
            # Fallback: unknown bases with no @action → emit all routes for compatibility
            if not allowed and not info.get("actions"):
                allowed = {action for _, _, action in _VIEWSET_ROUTES}

            # Standard CRUD routes (filtered by mixin-derived allowed set)
            for method, suffix, action in _VIEWSET_ROUTES:
                if action not in allowed:
                    continue
                full_path = _join_path("/" + base_path.lstrip("/"), suffix)
                path_params = [
                    ParamInfo(name=p, location="path", required=True, schema={"type": "string"})
                    for p in re.findall(r"\{(\w+)\}", full_path)
                ]
                try:
                    routes.append(RouteInfo(
                        method=method,
                        path=full_path,
                        handler=f"{class_name}.{action}",
                        file=view_source,
                        line=view_line,
                        framework="django",
                        params=path_params,
                        tags=[class_name.replace("ViewSet", "")],
                        summary=action.replace("_", " ").title(),
                    ))
                except (ValueError, TypeError) as e:
                    log.debug("Django: invalid route: %s", e)

            # @action routes
            for action_info in info.get("actions", []):
                detail = action_info.get("detail", False)
                url_path = action_info.get("url_path", "")
                if detail:
                    suffix = f"/{{pk}}/{url_path}"
                else:
                    suffix = f"/{url_path}"
                full_path = _join_path("/" + base_path.lstrip("/"), suffix.lstrip("/"))
                path_params = [
                    ParamInfo(name=p, location="path", required=True, schema={"type": "string"})
                    for p in re.findall(r"\{(\w+)\}", full_path)
                ]
                for method in action_info.get("methods", ["POST"]):
                    try:
                        routes.append(RouteInfo(
                            method=method,
                            path=full_path,
                            handler=f"{class_name}.{action_info['handler']}",
                            file=view_source,
                            line=action_info.get("line", view_line),
                            framework="django",
                            params=path_params,
                            tags=[class_name.replace("ViewSet", "")],
                        ))
                    except (ValueError, TypeError) as e:
                        log.debug("Django: invalid action route: %s", e)

        elif mapping_type == "apiview":
            methods = info.get("methods", ["GET"])
            if not methods:
                methods = ["GET"]
            path_params = [
                ParamInfo(name=p, location="path", required=True, schema={"type": "string"})
                for p in re.findall(r"\{(\w+)\}", base_path)
            ]
            for method in methods:
                try:
                    routes.append(RouteInfo(
                        method=method,
                        path=base_path if base_path.startswith("/") else "/" + base_path,
                        handler=f"{class_name}.{method.lower()}",
                        file=view_source,
                        line=view_line,
                        framework="django",
                        params=path_params,
                        tags=[class_name.replace("APIView", "").replace("View", "")],
                    ))
                except (ValueError, TypeError) as e:
                    log.debug("Django: invalid APIView route: %s", e)

        return routes
