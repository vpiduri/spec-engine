"""
Command-line interface for spec-engine.

Provides the main entry point and sub-commands for each pipeline stage:
  generate  — full pipeline: scan → infer → assemble → validate → (optionally) publish
  scan      — Stage 1 only: traverse repo and emit route manifest
  schema    — Stage 3 only: run AST inference from a manifest
  assemble  — Stage 4 only: build OpenAPI YAML from manifest + schemas
  validate  — Stage 5 only: validate an existing spec file
  publish   — push a validated spec to the Explorer catalog
"""

import click
import logging
import sys
import json
from pathlib import Path
from spec_engine.config import Config
from spec_engine.models import write_manifest, read_manifest

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(levelname)s %(name)s: %(message)s")


def _publish_spec(spec_path: str, config: Config, dry_run: bool = False) -> None:
    from spec_engine.publisher import publish as _pub
    result = _pub(spec_path, config, dry_run=dry_run)
    log.info("Publish result: %s", result)


# ---------------------------------------------------------------------------
# CLI group
# ---------------------------------------------------------------------------

@click.group()
def cli() -> None:
    """spec-engine — automated OpenAPI 3.1 spec generator."""


# ---------------------------------------------------------------------------
# generate — full pipeline
# ---------------------------------------------------------------------------

@cli.command("generate")
@click.option("--repo", default=".", show_default=True, help="Repository root path.")
@click.option("--config", "config_path", default=None, help="Path to config YAML file.")
@click.option("--gateway", default=None, help="Gateway name override.")
@click.option("--owner", default=None, help="Owner override.")
@click.option("--env", default=None, help="Environment override.")
@click.option("--publish/--no-publish", "do_publish", default=False, help="Publish after generating.")
@click.option("--dry-run", is_flag=True, default=False, help="Dry-run publish (no HTTP calls).")
@click.option("--out", default=None, help="Output YAML path (defaults to config.out).")
@click.option("--framework", default=None,
              help="Override framework detection (spring, fastapi, django, express, nestjs, gin, echo).")
@click.option("--verbose", is_flag=True, default=False, help="Enable debug logging.")
def generate(repo, config_path, gateway, owner, env, framework, do_publish, dry_run, out, verbose):
    """Full pipeline: scan → infer → assemble → validate → (optionally) publish."""
    _configure_logging(verbose)

    overrides = {}
    if gateway:
        overrides["gateway"] = gateway
    if owner:
        overrides["owner"] = owner
    if env:
        overrides["env"] = env
    if framework:
        overrides["framework"] = framework

    cfg = Config.load(config_path, overrides=overrides)

    from spec_engine.scanner import get_scanner
    from spec_engine.inferrer import run_inference
    from spec_engine.assembler import assemble
    from spec_engine.validator import validate

    scanner = get_scanner(repo, cfg)
    routes = scanner.scan()

    if not routes:
        click.echo(
            f"ERROR: No routes found in {repo}. "
            "Verify --repo points to the project root and the framework was detected correctly.",
            err=True,
        )
        sys.exit(1)

    framework = routes[0].framework
    log.info("Scanned %d routes (framework=%s)", len(routes), framework)

    schemas = run_inference(routes, repo, framework, cfg)
    log.info("Inferred %d schemas", len(schemas))

    yaml_str = assemble(routes, schemas, repo, cfg)

    out_path = out or cfg.out
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_text(yaml_str)
    log.info("Spec written to %s", out_path)

    # Validate — catch ValueError from strict_mode but still print errors
    try:
        result = validate(out_path, cfg)
    except ValueError as exc:
        click.echo(str(exc), err=True)
        sys.exit(1)

    for err in result.errors:
        click.echo(f"ERROR: {err}", err=True)
    for warn in result.warnings:
        click.echo(f"WARN:  {warn}")

    if not result.passed:
        sys.exit(1)

    if do_publish:
        _publish_spec(out_path, cfg, dry_run=dry_run)


# ---------------------------------------------------------------------------
# scan
# ---------------------------------------------------------------------------

@cli.command("scan")
@click.option("--repo", default=".", show_default=True, help="Repository root path.")
@click.option("--config", "config_path", default=None, help="Path to config YAML file.")
@click.option("--manifest", default="./manifest.json", show_default=True, help="Output manifest path.")
@click.option("--framework", default=None,
              help="Override framework detection (spring, fastapi, django, express, nestjs, gin, echo).")
@click.option("--verbose", is_flag=True, default=False, help="Enable debug logging.")
def scan(repo, config_path, manifest, framework, verbose):
    """Stage 1 only: traverse repo and emit route manifest."""
    _configure_logging(verbose)

    overrides = {}
    if framework:
        overrides["framework"] = framework
    cfg = Config.load(config_path, overrides=overrides if overrides else None)

    from spec_engine.scanner import get_scanner

    scanner = get_scanner(repo, cfg)
    routes = scanner.scan()
    framework = routes[0].framework if routes else "unknown"
    write_manifest(routes, repo, framework, manifest)
    click.echo(f"Manifest written to {manifest} ({len(routes)} routes, framework={framework})")


# ---------------------------------------------------------------------------
# schema
# ---------------------------------------------------------------------------

@cli.command("schema")
@click.option("--manifest", required=True, help="Path to manifest JSON file.")
@click.option("--repo", default=".", show_default=True, help="Repository root path.")
@click.option("--config", "config_path", default=None, help="Path to config YAML file.")
@click.option("--out", default="./schemas.json", show_default=True, help="Output schemas JSON path.")
@click.option("--verbose", is_flag=True, default=False, help="Enable debug logging.")
def schema(manifest, repo, config_path, out, verbose):
    """Stage 3 only: run AST inference from a manifest."""
    _configure_logging(verbose)

    from spec_engine.inferrer import run_inference

    cfg = Config.load(config_path)
    routes = read_manifest(manifest)
    framework = routes[0].framework if routes else "unknown"
    schemas = run_inference(routes, repo, framework, cfg)

    out_data = {name: sr.json_schema for name, sr in schemas.items()}
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(json.dumps(out_data, indent=2))
    click.echo(f"Schemas written to {out} ({len(schemas)} types)")


# ---------------------------------------------------------------------------
# assemble
# ---------------------------------------------------------------------------

@cli.command("assemble")
@click.option("--manifest", required=True, help="Path to manifest JSON file.")
@click.option("--repo", default=".", show_default=True, help="Repository root path.")
@click.option("--config", "config_path", default=None, help="Path to config YAML file.")
@click.option("--gateway", default=None, help="Gateway name override.")
@click.option("--owner", default=None, help="Owner override.")
@click.option("--out", default="./openapi.yaml", show_default=True, help="Output YAML path.")
@click.option("--verbose", is_flag=True, default=False, help="Enable debug logging.")
def assemble_cmd(manifest, repo, config_path, gateway, owner, out, verbose):
    """Stage 4 only: build OpenAPI YAML from manifest + inferred schemas."""
    _configure_logging(verbose)

    from spec_engine.inferrer import run_inference
    from spec_engine.assembler import assemble

    overrides = {}
    if gateway:
        overrides["gateway"] = gateway
    if owner:
        overrides["owner"] = owner

    cfg = Config.load(config_path, overrides=overrides)
    routes = read_manifest(manifest)
    framework = routes[0].framework if routes else "unknown"
    schemas = run_inference(routes, repo, framework, cfg)
    yaml_str = assemble(routes, schemas, repo, cfg)

    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(yaml_str)
    click.echo(f"Spec written to {out}")


# ---------------------------------------------------------------------------
# validate
# ---------------------------------------------------------------------------

@cli.command("validate")
@click.argument("spec_file")
@click.option("--config", "config_path", default=None, help="Path to config YAML file.")
@click.option("--verbose", is_flag=True, default=False, help="Enable debug logging.")
def validate_cmd(spec_file, config_path, verbose):
    """Stage 5 only: validate an existing spec YAML file."""
    _configure_logging(verbose)

    from spec_engine.validator import validate

    cfg = Config.load(config_path)
    cfg.strict_mode = False  # report all errors, don't raise
    result = validate(spec_file, cfg)

    for err in result.errors:
        click.echo(f"ERROR: {err}", err=True)
    for warn in result.warnings:
        click.echo(f"WARN:  {warn}")
    for info in result.infos:
        click.echo(f"INFO:  {info}")

    if result.passed:
        click.echo("Validation passed.")
    else:
        click.echo(f"Validation failed ({len(result.errors)} error(s)).", err=True)
        sys.exit(1)


# ---------------------------------------------------------------------------
# publish
# ---------------------------------------------------------------------------

@cli.command("publish")
@click.argument("spec_file")
@click.option("--config", "config_path", default=None, help="Path to config YAML file.")
@click.option("--dry-run", is_flag=True, default=False, help="Dry-run (no HTTP calls).")
@click.option("--verbose", is_flag=True, default=False, help="Enable debug logging.")
def publish_cmd(spec_file, config_path, dry_run, verbose):
    """Push a validated spec to the Explorer catalog."""
    _configure_logging(verbose)

    cfg = Config.load(config_path)
    _publish_spec(spec_file, cfg, dry_run=dry_run)
