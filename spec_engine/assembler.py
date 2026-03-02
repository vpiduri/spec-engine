"""
Stage 4 — Spec Assembler.

Combines route data and resolved schemas into a compliant OpenAPI 3.1 YAML document,
injecting Amex-required metadata (x-owner, x-gateway, x-lifecycle, etc.) automatically.

Key responsibilities:
  - Detect API title and owner from repo metadata (pom.xml, package.json, CODEOWNERS)
  - Build paths object, grouping routes by path string with operationId deduplication
  - Inject standard error responses (400, 401, 403, 404, 500) and Error schema
  - Serialise to YAML preserving key ordering via ruamel.yaml
"""

from pathlib import Path
from typing import List, Dict, Optional
import re
import io
import json
import logging
from ruamel.yaml import YAML
from spec_engine.models import RouteInfo, SchemaResult, Confidence
from spec_engine.config import Config

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_CONFIDENCE_PRIORITY = {
    Confidence.MANUAL: 0,
    Confidence.LOW: 1,
    Confidence.MEDIUM: 2,
    Confidence.HIGH: 3,
}

_STANDARD_ERRORS = {
    "400": {"description": "Bad Request"},
    "401": {"description": "Unauthorized"},
    "403": {"description": "Forbidden"},
    "404": {"description": "Not Found"},
    "500": {"description": "Internal Server Error"},
}

_yaml = YAML()
_yaml.default_flow_style = False
_yaml.width = 4096


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _detect_api_metadata(repo: Path) -> tuple:
    """Return (title, version, owner) detected from repo metadata files."""
    title = repo.name.replace("-", " ").title()
    version = "1.0.0"
    owner = "unknown"

    # Try pom.xml
    pom = repo / "pom.xml"
    if pom.exists():
        try:
            text = pom.read_text()
            m = re.search(r"<artifactId>([^<]+)</artifactId>", text)
            if m:
                title = m.group(1).replace("-", " ").title()
            m = re.search(r"<version>([^<]+)</version>", text)
            if m:
                version = m.group(1)
        except Exception:
            pass

    # Try package.json
    pkg = repo / "package.json"
    if pkg.exists():
        try:
            data = json.loads(pkg.read_text())
            if "name" in data:
                title = data["name"].replace("-", " ").title()
            if "version" in data:
                version = data["version"]
        except Exception:
            pass

    # Try CODEOWNERS
    for codeowners_path in (repo / "CODEOWNERS", repo / ".github" / "CODEOWNERS"):
        if codeowners_path.exists():
            try:
                for line in codeowners_path.read_text().splitlines():
                    line = line.strip()
                    if line and not line.startswith("#"):
                        tokens = line.split()
                        if len(tokens) >= 2:
                            owner = tokens[1].lstrip("@")
                        break
            except Exception:
                pass

    return title, version, owner


def _overall_confidence(schemas: Dict[str, SchemaResult]) -> Confidence:
    """Return the worst confidence level among all schemas; default HIGH if empty."""
    worst = Confidence.HIGH
    for sr in schemas.values():
        if _CONFIDENCE_PRIORITY[sr.confidence] < _CONFIDENCE_PRIORITY[worst]:
            worst = sr.confidence
    return worst


def _type_to_ref(type_name: Optional[str], schemas: Dict[str, SchemaResult]) -> dict:
    """Return a $ref if type is known in schemas, else a plain string schema."""
    if type_name and type_name in schemas:
        return {"$ref": f"#/components/schemas/{type_name}"}
    return {"type": "string"}


def _build_operation(
    route: RouteInfo,
    schemas: Dict[str, SchemaResult],
    seen_ids: set,
) -> dict:
    """Build an OpenAPI operation object for one route."""
    # operationId dedup
    op_id = route.operation_id
    if op_id in seen_ids:
        counter = 2
        while f"{op_id}_{counter}" in seen_ids:
            counter += 1
        op_id = f"{op_id}_{counter}"
    seen_ids.add(op_id)

    op: dict = {"operationId": op_id}

    if route.summary:
        op["summary"] = route.summary
    if route.tags:
        op["tags"] = list(route.tags)
    if route.deprecated:
        op["deprecated"] = True
    if route.auth_schemes:
        op["security"] = [{scheme: []} for scheme in route.auth_schemes]

    # Parameters
    if route.params:
        op["parameters"] = [p.to_openapi() for p in route.params]

    # Request body
    if route.request_body_type:
        schema_ref = _type_to_ref(route.request_body_type, schemas)
        op["requestBody"] = {
            "required": True,
            "content": {"application/json": {"schema": schema_ref}},
        }

    # Responses
    success_content: dict = {}
    if route.response_type:
        schema_ref = _type_to_ref(route.response_type, schemas)
        success_content = {"content": {"application/json": {"schema": schema_ref}}}

    op["responses"] = {
        "200": {"description": "OK", **success_content},
        **_STANDARD_ERRORS,
    }

    return op


def _build_paths(
    routes: List[RouteInfo],
    schemas: Dict[str, SchemaResult],
    config: Config,
) -> dict:
    """Build the OpenAPI paths object from all routes."""
    paths: dict = {}
    seen_ids: set = set()

    for route in routes:
        path_item = paths.setdefault(route.path, {})
        method_key = route.method.lower()
        path_item[method_key] = _build_operation(route, schemas, seen_ids)

    return paths


def _build_components(schemas: Dict[str, SchemaResult]) -> dict:
    """Build the OpenAPI components/schemas section."""
    schema_defs: dict = {
        "Error": {
            "type": "object",
            "properties": {
                "code": {"type": "string"},
                "message": {"type": "string"},
                "traceId": {"type": "string"},
            },
        }
    }

    for name, result in schemas.items():
        if result.json_schema:  # non-empty dict — includes enums
            schema_defs[name] = result.to_component_schema()

    return {"schemas": schema_defs}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def assemble(
    routes: List[RouteInfo],
    schemas: Dict[str, SchemaResult],
    repo_path: str,
    config: Config,
) -> str:
    """Return a ruamel.yaml-serialised OpenAPI 3.1 YAML string."""
    repo = Path(repo_path)
    detected_title, detected_version, detected_owner = _detect_api_metadata(repo)

    # Config owner overrides detected owner only when it's not the default "unknown"
    owner = config.owner if config.owner != "unknown" else detected_owner

    doc: dict = {}
    doc["openapi"] = "3.1.0"
    doc["info"] = {
        "title": detected_title,
        "version": detected_version,
        "x-owner": owner,
        "x-gateway": config.gateway,
        "x-lifecycle": getattr(config, "lifecycle", "production"),
    }
    doc["servers"] = getattr(config, "servers", [{"url": "/"}])
    doc["paths"] = _build_paths(routes, schemas, config)
    doc["components"] = _build_components(schemas)
    doc["x-confidence"] = _overall_confidence(schemas).value

    buf = io.StringIO()
    _yaml.dump(doc, buf)
    return buf.getvalue()
