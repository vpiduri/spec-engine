"""
Core data models for spec-engine.

Defines the data structures that flow between pipeline stages:
  Confidence   — enum driving publish gating and human review routing
  ParamInfo    — a single route parameter (path, query, header, cookie)
  RouteInfo    — one discovered API route with all metadata
  SchemaResult — a resolved JSON Schema for a request/response type

Also provides write_manifest() and read_manifest() for Stage 1 → Stage 3 hand-off.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _capitalize_first(s: str) -> str:
    """Uppercase only the first character, preserving the rest (handles camelCase params)."""
    return s[0].upper() + s[1:] if s else s


def _segment_to_camel(segment: str) -> str:
    """
    Convert a path segment to CamelCase by splitting on hyphens and underscores.

    Uses _capitalize_first (not str.capitalize) so that existing camelCase in path
    parameters like {userId} is preserved: "userId" → "UserId" not "Userid".
    """
    parts = re.split(r"[-_]+", segment)
    return "".join(_capitalize_first(p) for p in parts if p)


# ---------------------------------------------------------------------------
# 3.1 — Confidence enum
# ---------------------------------------------------------------------------

class Confidence(str, Enum):
    """
    Confidence level assigned to every inferred JSON Schema.

    Assignment rules:
      HIGH   — Full type info from strongly-typed annotations (e.g. Java @RequestBody
               with a fully resolved class, Pydantic model). Safe to auto-publish.
      MEDIUM — Partial type info: some fields inferred, some missing or using
               generic types. Publish after a quick human review.
      LOW    — LLM-assisted inference used as a fallback. Accuracy not guaranteed.
               Human review required before publishing.
      MANUAL — Inferrer could not resolve the type at all (dynamic typing, reflection,
               runtime-assembled schemas). Block publish and flag for manual authoring.
    """

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    MANUAL = "manual"

    def is_publishable(self) -> bool:
        """Return True only for confidence levels safe enough to auto-publish."""
        return self in (Confidence.HIGH, Confidence.MEDIUM)


# ---------------------------------------------------------------------------
# 3.2 — ParamInfo dataclass
# ---------------------------------------------------------------------------

_VALID_LOCATIONS = {"path", "query", "header", "cookie"}


@dataclass
class ParamInfo:
    """A single parameter on an API route (path variable, query param, header, cookie)."""

    name: str
    location: str          # Must be one of: "path", "query", "header", "cookie"
    required: bool = True
    schema: Dict[str, Any] = field(default_factory=dict)
    description: str = ""

    def __post_init__(self) -> None:
        if self.location not in _VALID_LOCATIONS:
            raise ValueError(
                f"ParamInfo.location must be one of {sorted(_VALID_LOCATIONS)}, "
                f"got: {self.location!r}"
            )

    def to_openapi(self) -> dict:
        """Return this parameter in OpenAPI 3.1 parameter object format."""
        d: Dict[str, Any] = {
            "name": self.name,
            "in": self.location,
            "required": self.required,
            "schema": self.schema,
        }
        if self.description:
            d["description"] = self.description
        return d

    def to_dict(self) -> dict:
        """Return a JSON-serialisable dict for storage in the route manifest."""
        return {
            "name": self.name,
            "location": self.location,
            "required": self.required,
            "schema": self.schema,
            "description": self.description,
        }


# ---------------------------------------------------------------------------
# 3.3 — RouteInfo dataclass
# ---------------------------------------------------------------------------

_VALID_METHODS = {"GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"}

_METHOD_VERB_MAP = {
    "GET": "get",
    "POST": "create",
    "PUT": "update",
    "DELETE": "delete",
    "PATCH": "patch",
    "HEAD": "head",
    "OPTIONS": "options",
}

_VERSION_SEGMENT_RE = re.compile(r"^v\d+$", re.IGNORECASE)


@dataclass
class RouteInfo:
    """
    One discovered API route with all metadata needed for OpenAPI spec generation.

    Produced by Stage 1 (Scanner) and consumed by Stage 3 (Inferrer) and
    Stage 4 (Assembler).
    """

    method: str                  # GET | POST | PUT | DELETE | PATCH
    path: str                    # e.g. /v1/accounts/{accountId}
    handler: str                 # e.g. AccountController.createAccount
    file: str                    # relative path from repo root
    line: int                    # line number in source file
    framework: str               # spring | express | fastapi | django | gin
    params: List[ParamInfo] = field(default_factory=list)
    request_body_type: Optional[str] = None
    response_type: Optional[str] = None
    auth_schemes: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    summary: str = ""
    deprecated: bool = False

    def __post_init__(self) -> None:
        # Normalise method to uppercase rather than raising
        self.method = self.method.upper()
        if self.method not in _VALID_METHODS:
            raise ValueError(
                f"RouteInfo.method must be one of {sorted(_VALID_METHODS)}, "
                f"got: {self.method!r}"
            )
        if not self.path.startswith("/"):
            raise ValueError(
                f"RouteInfo.path must start with '/', got: {self.path!r}"
            )
        if self.line <= 0:
            raise ValueError(
                f"RouteInfo.line must be > 0, got: {self.line}"
            )

    @property
    def operation_id(self) -> str:
        """
        Generate a camelCase operationId from the HTTP method and path.

        Mapping rules:
          - HTTP method → RESTful verb prefix: POST→create, PUT→update, GET→get,
            DELETE→delete, PATCH→patch
          - Version path segments (v1, v2, v3 …) are skipped
          - Regular segments are converted to CamelCase (hyphens/underscores as word splits)
          - Path parameter segments {param} contribute "By" + CamelCase(param)

        Examples:
          POST /v1/accounts          → createAccounts
          GET  /v1/accounts/{id}     → getAccountsById
          DELETE /v1/accounts/{id}  → deleteAccountsById
          PUT /v1/users/{userId}/profile → updateUsersByUserIdProfile
          GET /api-keys              → getApiKeys
        """
        verb = _METHOD_VERB_MAP.get(self.method, self.method.lower())
        parts = [verb]

        for segment in self.path.split("/"):
            if not segment:
                continue
            if _VERSION_SEGMENT_RE.match(segment):
                continue
            if segment.startswith("{") and segment.endswith("}"):
                param_name = segment[1:-1]
                parts.append("By" + _segment_to_camel(param_name))
            else:
                parts.append(_segment_to_camel(segment))

        return "".join(parts)

    def to_dict(self) -> dict:
        """Return a JSON-serialisable dict for writing to the route manifest."""
        return {
            "method": self.method,
            "path": self.path,
            "handler": self.handler,
            "file": self.file,
            "line": self.line,
            "framework": self.framework,
            "params": [p.to_dict() for p in self.params],
            "request_body_type": self.request_body_type,
            "response_type": self.response_type,
            "auth_schemes": self.auth_schemes,
            "tags": self.tags,
            "summary": self.summary,
            "deprecated": self.deprecated,
        }


# ---------------------------------------------------------------------------
# 3.4 — SchemaResult dataclass
# ---------------------------------------------------------------------------

@dataclass
class SchemaResult:
    """
    The result of inferring a JSON Schema for a named type.

    Produced by Stage 3 (Inferrer) and consumed by Stage 4 (Assembler).
    The confidence level determines whether the spec can be auto-published.
    """

    type_name: str
    json_schema: Dict[str, Any]
    confidence: Confidence
    source_file: str
    refs: List[str] = field(default_factory=list)  # names of nested $ref types

    @property
    def is_empty(self) -> bool:
        """
        Return True if inference produced no usable schema.

        Triggers on:
          - Empty dict {}  (inferrer found nothing)
          - Dict with no "properties" key (type resolved but no fields extracted)
        """
        return not self.json_schema or "properties" not in self.json_schema

    @property
    def ref_count(self) -> int:
        """Number of nested type references that were discovered during inference."""
        return len(self.refs)

    def to_component_schema(self) -> dict:
        """
        Return json_schema augmented with Amex extension fields.

        The result is written directly into components/schemas in the OpenAPI doc.
        x-confidence drives publish gating in the Explorer catalog.
        """
        schema = dict(self.json_schema)
        schema["x-confidence"] = self.confidence.value
        schema["x-source-file"] = self.source_file
        return schema

    @classmethod
    def empty(cls, type_name: str, source_file: str) -> "SchemaResult":
        """
        Convenience constructor for when inference fails completely.

        Assigns MANUAL confidence so the spec is blocked from auto-publishing
        and flagged for manual authoring.
        """
        return cls(
            type_name=type_name,
            json_schema={},
            confidence=Confidence.MANUAL,
            source_file=source_file,
        )


# ---------------------------------------------------------------------------
# 3.5 — Route manifest writer & reader
# ---------------------------------------------------------------------------

def write_manifest(
    routes: List[RouteInfo],
    repo: str,
    framework: str,
    output_path: str,
) -> None:
    """
    Write the route manifest JSON file produced by Stage 1 (Scanner).

    The manifest is the hand-off artifact between Stage 1 and Stage 3.
    Parent directories are created automatically if they do not exist.
    """
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "repo": repo,
        "framework": framework,
        "route_count": len(routes),
        "routes": [r.to_dict() for r in routes],
    }
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2))


def read_manifest(manifest_path: str) -> List[RouteInfo]:
    """
    Read a route manifest JSON file and return a list of RouteInfo objects.

    Raises:
      FileNotFoundError — if manifest_path does not exist
      ValueError        — if the JSON is missing the required "routes" key
    """
    path = Path(manifest_path)
    if not path.exists():
        raise FileNotFoundError(
            f"Route manifest not found: {manifest_path}. "
            "Run 'spec-engine scan --repo <path>' first to generate it."
        )

    data = json.loads(path.read_text())

    if "routes" not in data:
        raise ValueError(
            f"Invalid manifest: missing 'routes' key in {manifest_path}. "
            "The file may be corrupted or from an incompatible version."
        )

    routes = []
    for r in data["routes"]:
        r = dict(r)  # copy — avoid mutating the original parsed dict
        params = [ParamInfo(**p) for p in r.pop("params", [])]
        routes.append(RouteInfo(**r, params=params))
    return routes
