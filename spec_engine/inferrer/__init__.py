"""
Stage 3 — Schema Inferrer package.

Uses AST parsing to resolve request/response type names (from RouteInfo) into
JSON Schema definitions. Dispatches to the appropriate language inferrer based
on framework. Implements shared cycle detection before delegating to
language-specific inferrers.

Usage:
  from spec_engine.inferrer import run_inference
  schemas = run_inference(routes, repo_path, framework, config)
"""

import importlib
import logging
from collections import Counter
from typing import Dict, List, Type

from spec_engine.models import RouteInfo, SchemaResult
from spec_engine.config import Config
from spec_engine.inferrer.base import BaseInferrer, _PRIMITIVE_MAP

log = logging.getLogger(__name__)

# Framework → inferrer dotted class path
FRAMEWORK_INFERRER_MAP: Dict[str, str] = {
    "spring": "spec_engine.inferrer.java_ast.JavaASTInferrer",
    "fastapi": "spec_engine.inferrer.python_ast.PythonASTInferrer",
    "django": "spec_engine.inferrer.python_ast.PythonASTInferrer",
    "express": "spec_engine.inferrer.typescript_ast.TypeScriptASTInferrer",
    "nestjs": "spec_engine.inferrer.typescript_ast.TypeScriptASTInferrer",
    "gin": "spec_engine.inferrer.go_ast.GoASTInferrer",
    "echo": "spec_engine.inferrer.go_ast.GoASTInferrer",
}


def _load_inferrer_class(dotted_path: str) -> Type[BaseInferrer]:
    """Import and return an inferrer class from its dotted module path."""
    module_path, class_name = dotted_path.rsplit(".", 1)
    module = importlib.import_module(module_path)
    return getattr(module, class_name)


def run_inference(
    routes: List[RouteInfo],
    repo_path: str,
    framework: str,
    config: Config,
) -> Dict[str, SchemaResult]:
    """
    Resolve request/response types for all routes into JSON Schema definitions.

    Uses a single shared inferrer instance so the schema_registry is shared
    across all routes (avoiding duplicate work for repeated types).

    Returns a dict of {type_name: SchemaResult}.
    """
    framework = (framework or "").lower()
    inferrer_path = FRAMEWORK_INFERRER_MAP.get(framework)

    if not inferrer_path:
        log.warning("No inferrer for framework %r — skipping schema inference", framework)
        return {}

    try:
        inferrer_class = _load_inferrer_class(inferrer_path)
    except (ImportError, AttributeError) as e:
        log.error("Failed to load inferrer for %s: %s", framework, e)
        return {}

    inferrer: BaseInferrer = inferrer_class(repo_path, config)

    # Collect all unique type names from routes
    seen: set = set()
    unique_types: List[str] = []
    for route in routes:
        for type_name in (route.request_body_type, route.response_type):
            if type_name and type_name not in seen:
                seen.add(type_name)
                unique_types.append(type_name)

    # Resolve non-primitive types
    resolved: Dict[str, SchemaResult] = {}
    for type_name in unique_types:
        if _PRIMITIVE_MAP.get(type_name) is not None:
            continue
        result = inferrer.resolve_type(type_name)
        resolved[type_name] = result
        log.debug("Inferred %r → confidence=%s", type_name, result.confidence.value)

    # Include transitively discovered types from the shared registry
    for type_name, result in inferrer.schema_registry.items():
        if type_name not in resolved:
            resolved[type_name] = result

    # Log summary
    if resolved:
        conf_counts = Counter(r.confidence.value for r in resolved.values())
        log.info(
            "Inference complete: %d types resolved (%s)",
            len(resolved),
            ", ".join(f"{k}={v}" for k, v in sorted(conf_counts.items())),
        )

    return resolved
