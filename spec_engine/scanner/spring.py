"""
Spring Boot (Java) scanner.

Parses @RequestMapping, @GetMapping, @PostMapping, @PutMapping, @DeleteMapping,
and @PatchMapping annotations using the javalang AST library to extract routes,
handler method names, parameter annotations (@RequestBody, @PathVariable, etc.),
and security annotations (@PreAuthorize).
"""

import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import javalang
import javalang.tree as jt

from spec_engine.models import RouteInfo, ParamInfo
from spec_engine.scanner.base import BaseScanner
from spec_engine.config import Config

log = logging.getLogger(__name__)

# Annotation name → HTTP method (shortcuts)
_METHOD_ANNOTATIONS: Dict[str, str] = {
    "GetMapping": "GET",
    "PostMapping": "POST",
    "PutMapping": "PUT",
    "DeleteMapping": "DELETE",
    "PatchMapping": "PATCH",
}

_REQUEST_METHOD_MAP: Dict[str, str] = {
    "GET": "GET", "POST": "POST", "PUT": "PUT",
    "DELETE": "DELETE", "PATCH": "PATCH",
    "HEAD": "HEAD", "OPTIONS": "OPTIONS",
}

# Java primitive/common types → JSON Schema
_JAVA_TYPE_SCHEMA: Dict[str, dict] = {
    "String": {"type": "string"},
    "Integer": {"type": "integer"},
    "int": {"type": "integer"},
    "Long": {"type": "integer", "format": "int64"},
    "long": {"type": "integer", "format": "int64"},
    "Boolean": {"type": "boolean"},
    "boolean": {"type": "boolean"},
    "Double": {"type": "number", "format": "double"},
    "double": {"type": "number", "format": "double"},
    "Float": {"type": "number", "format": "float"},
    "float": {"type": "number", "format": "float"},
    "UUID": {"type": "string", "format": "uuid"},
    "BigDecimal": {"type": "number"},
    "BigInteger": {"type": "integer"},
    "LocalDate": {"type": "string", "format": "date"},
    "LocalDateTime": {"type": "string", "format": "date-time"},
    "ZonedDateTime": {"type": "string", "format": "date-time"},
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _strip_quotes(value: Any) -> str:
    """Remove surrounding double/single quotes from a Java string literal."""
    s = str(value).strip()
    if s.startswith('"') and s.endswith('"'):
        return s[1:-1]
    if s.startswith("'") and s.endswith("'"):
        return s[1:-1]
    return s


def _join_path(prefix: str, suffix: str) -> str:
    """
    Join two URL path segments cleanly.
    Result always starts with '/', never has double slashes.
    """
    prefix = (prefix or "").rstrip("/")
    suffix = (suffix or "").lstrip("/")
    if not prefix and not suffix:
        return "/"
    combined = prefix + "/" + suffix if suffix else prefix
    if not combined.startswith("/"):
        combined = "/" + combined
    return combined or "/"


def _camel_to_title(name: str) -> str:
    """Convert camelCase method name to 'Title Case Words'."""
    spaced = re.sub(r"([a-z])([A-Z])", r"\1 \2", name)
    return spaced[0].upper() + spaced[1:] if spaced else spaced


def _get_element_pairs(annotation: Any) -> list:
    """
    Return all ElementValuePair objects from an annotation.
    javalang may place named pairs in annotation.element (as a list)
    or annotation.elements depending on the version / annotation form.
    """
    pairs = []
    elem = getattr(annotation, "element", None)
    if isinstance(elem, list):
        pairs.extend(elem)
    elements = getattr(annotation, "elements", None) or []
    pairs.extend(elements)
    return pairs


def _get_annotation_value(annotation: Any, key: Optional[str] = None) -> Optional[str]:
    """
    Extract a string value from a javalang annotation.

    If key is None: try annotation.element (single unnamed value).
    If key is provided: search annotation element pairs for a match.
    Falls back to searching for "value" and "path" keys when key is None.
    """
    if key is None:
        # Single-value annotation: @RequestMapping("/path")
        elem = getattr(annotation, "element", None)
        if elem is not None and not isinstance(elem, list):
            if hasattr(elem, "value"):
                return _strip_quotes(elem.value)
            return _strip_quotes(str(elem))
        # Named elements — look for "value" or "path" keys
        val = _get_annotation_value(annotation, "value")
        if val is not None:
            return val
        return _get_annotation_value(annotation, "path")
    else:
        for el in _get_element_pairs(annotation):
            if not hasattr(el, "name") or el.name != key:
                continue
            val = el.value
            if val is None:
                return None
            if hasattr(val, "member"):
                return str(val.member)
            if hasattr(val, "value"):
                return _strip_quotes(val.value)
            return _strip_quotes(str(val))
        return None


# ---------------------------------------------------------------------------
# SpringScanner
# ---------------------------------------------------------------------------

class SpringScanner(BaseScanner):
    """Scanner for Spring Boot Java applications."""

    EXTENSIONS = [".java"]

    def scan(self) -> List[RouteInfo]:
        routes: List[RouteInfo] = []
        for file_path in self._iter_files():
            try:
                routes.extend(self._scan_file(file_path))
            except Exception as e:
                log.debug("Spring: skipping %s: %s", file_path, e)
        return routes

    def _scan_file(self, file_path: Path) -> List[RouteInfo]:
        source = file_path.read_text(encoding="utf-8", errors="ignore")
        try:
            tree = javalang.parse.parse(source)
        except Exception as e:
            log.debug("Spring: parse error in %s: %s", file_path, e)
            return []

        rel_path = str(file_path.relative_to(self.repo_path))
        routes: List[RouteInfo] = []

        for _, type_decl in tree.filter(jt.ClassDeclaration):
            if not self._is_controller(type_decl):
                continue
            class_prefix = self._get_class_mapping(type_decl)
            tags = [self._class_to_tag(type_decl.name)]

            for method in (type_decl.methods or []):
                route = self._process_method(method, class_prefix, tags, rel_path, type_decl.name)
                if route:
                    routes.append(route)

        return routes

    def _is_controller(self, type_decl: jt.ClassDeclaration) -> bool:
        """Return True if class has @RestController or @Controller."""
        for ann in (type_decl.annotations or []):
            if ann.name in ("RestController", "Controller"):
                return True
        return False

    def _get_class_mapping(self, type_decl: jt.ClassDeclaration) -> str:
        """Extract @RequestMapping value from class-level annotation."""
        for ann in (type_decl.annotations or []):
            if ann.name == "RequestMapping":
                val = _get_annotation_value(ann)
                if val is not None:
                    return val
        return ""

    def _class_to_tag(self, class_name: str) -> str:
        """AccountController → Account"""
        if class_name.endswith("Controller"):
            return class_name[: -len("Controller")]
        return class_name

    def _process_method(
        self,
        method: jt.MethodDeclaration,
        class_prefix: str,
        tags: List[str],
        rel_path: str,
        class_name: str,
    ) -> Optional[RouteInfo]:
        """Extract RouteInfo from a method declaration, or None if not a route handler."""
        http_method: Optional[str] = None
        method_path = ""

        for ann in (method.annotations or []):
            if ann.name in _METHOD_ANNOTATIONS:
                http_method = _METHOD_ANNOTATIONS[ann.name]
                method_path = _get_annotation_value(ann) or ""
                break
            elif ann.name == "RequestMapping":
                rm = _get_annotation_value(ann, "method")
                if rm:
                    rm = rm.split(".")[-1].upper()
                    http_method = _REQUEST_METHOD_MAP.get(rm, "GET")
                else:
                    http_method = "GET"
                method_path = _get_annotation_value(ann) or ""
                break

        if not http_method:
            return None

        full_path = _join_path(class_prefix, method_path)
        params = self._extract_params(method, full_path)
        request_body_type = self._extract_request_body(method)
        response_type = self._extract_response_type(method)
        auth_schemes = self._extract_auth(method)
        summary = _camel_to_title(method.name)
        line = method.position.line if method.position else 1
        handler = f"{class_name}.{method.name}"

        return RouteInfo(
            method=http_method,
            path=full_path,
            handler=handler,
            file=rel_path,
            line=line,
            framework="spring",
            params=params,
            request_body_type=request_body_type,
            response_type=response_type,
            auth_schemes=auth_schemes,
            tags=tags,
            summary=summary,
        )

    def _extract_params(
        self, method: jt.MethodDeclaration, path: str
    ) -> List[ParamInfo]:
        """Extract @PathVariable, @RequestParam, @RequestHeader, @CookieValue params."""
        params: List[ParamInfo] = []

        for param in (method.parameters or []):
            location: Optional[str] = None
            param_name = param.name
            required = True

            for ann in (param.annotations or []):
                if ann.name == "PathVariable":
                    location = "path"
                    override = _get_annotation_value(ann)
                    if override:
                        param_name = override
                elif ann.name == "RequestParam":
                    location = "query"
                    override = _get_annotation_value(ann)
                    if override:
                        param_name = override
                    req_val = _get_annotation_value(ann, "required")
                    if req_val and req_val.lower() == "false":
                        required = False
                elif ann.name == "RequestHeader":
                    location = "header"
                    override = _get_annotation_value(ann)
                    if override:
                        param_name = override
                elif ann.name == "CookieValue":
                    location = "cookie"
                    override = _get_annotation_value(ann)
                    if override:
                        param_name = override

            if location:
                type_name = str(param.type.name) if param.type else "String"
                schema = _JAVA_TYPE_SCHEMA.get(type_name, {"type": "string"})
                params.append(
                    ParamInfo(
                        name=param_name,
                        location=location,
                        required=required,
                        schema=schema,
                    )
                )

        return params

    def _extract_request_body(self, method: jt.MethodDeclaration) -> Optional[str]:
        """Find the @RequestBody parameter's type name."""
        for param in (method.parameters or []):
            for ann in (param.annotations or []):
                if ann.name == "RequestBody":
                    return str(param.type.name) if param.type else None
        return None

    def _extract_response_type(self, method: jt.MethodDeclaration) -> Optional[str]:
        """Get return type, unwrapping ResponseEntity<T> → T."""
        ret = method.return_type
        if ret is None:
            return None
        type_name = str(ret.name)
        if type_name in ("void", "Void"):
            return None
        if type_name == "ResponseEntity":
            args = getattr(ret, "arguments", None)
            if args:
                first = args[0]
                if hasattr(first, "type") and first.type:
                    return str(first.type.name)
                if hasattr(first, "name"):
                    return str(first.name)
        return type_name

    def _extract_auth(self, method: jt.MethodDeclaration) -> List[str]:
        """Extract auth scheme from @PreAuthorize annotation value."""
        for ann in (method.annotations or []):
            if ann.name == "PreAuthorize":
                val = (_get_annotation_value(ann) or "").lower()
                if "oauth" in val or "scope" in val:
                    return ["oauth2"]
                if "bearer" in val:
                    return ["bearerAuth"]
                if "apikey" in val or "api_key" in val:
                    return ["apiKey"]
                return ["bearerAuth"]
        return []
