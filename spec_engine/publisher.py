"""
Explorer API Catalog publisher.

Publishes or updates OpenAPI specs to the Amex API Explorer catalog via HTTP.
Requires EXPLORER_API_TOKEN env var and catalog_url set in config.

Endpoints used:
  POST {catalog_url}/apis        — create new entry
  PUT  {catalog_url}/apis/{id}   — update existing entry
"""

import os
import logging
from pathlib import Path
from typing import Optional
import httpx
import yaml
from spec_engine.config import Config

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _extract_api_name(spec_content: str) -> str:
    """Extract API title from a YAML spec string; fallback to 'unknown'."""
    try:
        doc = yaml.safe_load(spec_content)
        return doc["info"]["title"]
    except Exception:
        return "unknown"


def _check_existing(catalog_url: str, api_name: str, token: str) -> Optional[str]:
    """Return the existing API id if found in the catalog, else None."""
    try:
        resp = httpx.get(
            f"{catalog_url}/apis",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
        resp.raise_for_status()
        items = resp.json()
        if isinstance(items, list):
            for item in items:
                if item.get("title") == api_name:
                    return item.get("id")
    except Exception as exc:
        log.debug("Could not check existing APIs: %s", exc)
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def publish(spec_path: str, config: Config, dry_run: bool = False) -> dict:
    """POST/PUT spec to catalog_url. Returns response dict."""
    catalog_url = getattr(config, "catalog_url", None)
    if not catalog_url:
        raise ValueError(
            "catalog_url is not set in config. "
            "Add 'catalog_url: https://...' to config.yaml or pass it as an override."
        )

    token = os.environ.get("EXPLORER_API_TOKEN")
    if not token and not dry_run:
        raise ValueError(
            "EXPLORER_API_TOKEN environment variable is not set. "
            "Export it before running the publish command."
        )

    spec_content = Path(spec_path).read_text()

    if dry_run:
        log.info("Dry run — would publish %s to %s", spec_path, catalog_url)
        return {"status": "dry-run", "spec_path": spec_path}

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/yaml",
    }

    api_name = _extract_api_name(spec_content)
    existing_id = _check_existing(catalog_url, api_name, token)

    if existing_id:
        log.info("Updating existing API '%s' (id=%s)", api_name, existing_id)
        resp = httpx.put(
            f"{catalog_url}/apis/{existing_id}",
            content=spec_content.encode(),
            headers=headers,
            timeout=30,
        )
    else:
        log.info("Creating new API '%s'", api_name)
        resp = httpx.post(
            f"{catalog_url}/apis",
            content=spec_content.encode(),
            headers=headers,
            timeout=30,
        )

    resp.raise_for_status()
    return resp.json()
