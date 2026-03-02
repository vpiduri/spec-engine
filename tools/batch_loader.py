#!/usr/bin/env python3
"""
batch_loader.py — CSV-driven bulk spec generator.

Usage:
    python3 tools/batch_loader.py \
        --csv api_inventory.csv \
        --config config.yaml \
        --spec-dir ./specs \
        --log-dir  ./logs \
        --workers  16 \
        --publish \
        --retry-failed  # re-run only rows that previously failed

Requires:
    - spec-engine installed in active virtualenv
    - GIT_TOKEN env var (for HTTPS clone auth) or SSH key configured
    - EXPLORER_API_TOKEN env var (for --publish)
"""

import argparse
import concurrent.futures
import csv
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("batch_loader")

# ──────────────────────────────────────────────────────────────────────────────
# Data structures
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class RepoRow:
    api_name: str
    team: str
    gateway: str
    repo_url: str
    framework: str = ""
    lifecycle: str = "production"
    owner: str = ""
    env: str = "production"
    exclude_paths: str = ""

    def effective_owner(self) -> str:
        return self.owner or self.team


@dataclass
class RepoResult:
    api_name: str
    repo_url: str
    success: bool
    routes_found: int = 0
    confidence_high: int = 0
    confidence_medium: int = 0
    confidence_manual: int = 0
    spec_path: str = ""
    error: str = ""
    duration_seconds: float = 0.0


# ──────────────────────────────────────────────────────────────────────────────
# CSV loading
# ──────────────────────────────────────────────────────────────────────────────

def load_csv(csv_path: Path) -> List[RepoRow]:
    rows = []
    with csv_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader, start=2):
            api_name = row.get("api_name", "").strip()
            repo_url = row.get("repo_url", "").strip()
            if not api_name or not repo_url:
                log.warning("Row %d: missing api_name or repo_url — skipped", i)
                continue
            rows.append(RepoRow(
                api_name=api_name,
                team=row.get("team", "").strip(),
                gateway=row.get("gateway", "unknown").strip(),
                repo_url=repo_url,
                framework=row.get("framework", "").strip(),
                lifecycle=row.get("lifecycle", "production").strip() or "production",
                owner=row.get("owner", "").strip(),
                env=row.get("env", "production").strip() or "production",
                exclude_paths=row.get("exclude_paths", "").strip(),
            ))
    log.info("Loaded %d rows from %s", len(rows), csv_path)
    return rows


def load_failed_from_report(report_path: Path) -> List[str]:
    """Return api_names that failed in a previous batch_report.csv run."""
    failed = []
    with report_path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("success", "true").lower() != "true":
                failed.append(row["api_name"])
    return failed


# ──────────────────────────────────────────────────────────────────────────────
# Git clone helper
# ──────────────────────────────────────────────────────────────────────────────

def clone_repo(repo_url: str, clone_dir: Path, git_token: Optional[str]) -> bool:
    """Shallow-clone repo_url into clone_dir. Returns True on success."""
    # Inject token for HTTPS URLs if available
    url = repo_url
    if git_token and url.startswith("https://"):
        # https://github.com/org/repo → https://TOKEN@github.com/org/repo
        url = url.replace("https://", f"https://{git_token}@", 1)

    try:
        result = subprocess.run(
            ["git", "clone", "--depth", "1", "--quiet", url, str(clone_dir)],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            log.debug("git clone failed for %s: %s", repo_url, result.stderr.strip())
            return False
        return True
    except subprocess.TimeoutExpired:
        log.debug("git clone timeout for %s", repo_url)
        return False
    except FileNotFoundError:
        log.error("git not found in PATH")
        return False


# ──────────────────────────────────────────────────────────────────────────────
# Parse spec-engine stdout for metrics
# ──────────────────────────────────────────────────────────────────────────────

def _parse_routes(output: str) -> int:
    m = re.search(r"Scanned (\d+) routes", output)
    return int(m.group(1)) if m else 0

def _parse_confidence(output: str, level: str) -> int:
    m = re.search(rf"{level}:\s*(\d+)", output, re.IGNORECASE)
    return int(m.group(1)) if m else 0


# ──────────────────────────────────────────────────────────────────────────────
# Process one row
# ──────────────────────────────────────────────────────────────────────────────

def process_row(
    row: RepoRow,
    spec_dir: Path,
    log_dir: Path,
    config_path: str,
    do_publish: bool,
    git_token: Optional[str],
) -> RepoResult:
    started = datetime.now(timezone.utc)
    out_path = spec_dir / f"{row.api_name}.yaml"
    log_path = log_dir / f"{row.api_name}.log"

    with tempfile.TemporaryDirectory(prefix=f"spec_batch_{row.api_name}_") as tmp:
        clone_dir = Path(tmp) / "repo"

        # Step 1: clone
        if not clone_repo(row.repo_url, clone_dir, git_token):
            duration = (datetime.now(timezone.utc) - started).total_seconds()
            return RepoResult(
                api_name=row.api_name,
                repo_url=row.repo_url,
                success=False,
                error="git clone failed",
                duration_seconds=duration,
            )

        # Step 2: write per-repo .spec-engine.yaml if exclude_paths are set
        if row.exclude_paths:
            patterns = [p.strip() for p in row.exclude_paths.split(";") if p.strip()]
            repo_cfg = clone_dir / ".spec-engine.yaml"
            lines = ["exclude_paths:"]
            for p in patterns:
                lines.append(f'  - "{p}"')
            repo_cfg.write_text("\n".join(lines) + "\n")

        # Step 3: build spec-engine command
        cmd = [
            "spec-engine", "generate",
            "--repo",      str(clone_dir),
            "--config",    config_path,
            "--gateway",   row.gateway,
            "--owner",     row.effective_owner(),
            "--env",       row.env,
            "--out",       str(out_path),
            "--verbose",
        ]
        if row.framework:
            cmd += ["--framework", row.framework]
        if do_publish:
            cmd.append("--publish")

        # Step 4: run
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=180,
                env={**os.environ, "PYTHONUNBUFFERED": "1"},
            )
            combined = result.stdout + "\n" + result.stderr
            log_path.write_text(combined)

            success = result.returncode == 0
            duration = (datetime.now(timezone.utc) - started).total_seconds()

            return RepoResult(
                api_name=row.api_name,
                repo_url=row.repo_url,
                success=success,
                routes_found=_parse_routes(combined),
                confidence_high=_parse_confidence(combined, "HIGH"),
                confidence_medium=_parse_confidence(combined, "MEDIUM"),
                confidence_manual=_parse_confidence(combined, "MANUAL"),
                spec_path=str(out_path) if success else "",
                error="" if success else result.stderr.strip().splitlines()[-1] if result.stderr.strip() else "unknown",
                duration_seconds=duration,
            )
        except subprocess.TimeoutExpired:
            duration = (datetime.now(timezone.utc) - started).total_seconds()
            log_path.write_text("TIMEOUT after 180 seconds\n")
            return RepoResult(
                api_name=row.api_name,
                repo_url=row.repo_url,
                success=False,
                error="timeout (180s)",
                duration_seconds=duration,
            )


# ──────────────────────────────────────────────────────────────────────────────
# Report writers
# ──────────────────────────────────────────────────────────────────────────────

def write_batch_report(results: List[RepoResult], report_path: Path) -> None:
    with report_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "api_name", "success", "routes_found",
            "confidence_high", "confidence_medium", "confidence_manual",
            "spec_path", "error", "duration_seconds",
        ])
        writer.writeheader()
        for r in results:
            writer.writerow(asdict(r))
    log.info("Batch report written to %s", report_path)


def write_batch_summary(results: List[RepoResult], started: datetime, summary_path: Path) -> None:
    succeeded = [r for r in results if r.success]
    failed = [r for r in results if not r.success]
    duration = (datetime.now(timezone.utc) - started).total_seconds()

    all_high = sum(
        1 for r in succeeded
        if r.confidence_medium == 0 and r.confidence_manual == 0
    )
    has_medium = sum(1 for r in succeeded if r.confidence_medium > 0)
    has_manual = sum(1 for r in succeeded if r.confidence_manual > 0)

    summary = {
        "run_date": started.isoformat(),
        "total_repos": len(results),
        "succeeded": len(succeeded),
        "failed": len(failed),
        "duration_minutes": round(duration / 60, 1),
        "confidence_breakdown": {
            "all_high": all_high,
            "has_medium": has_medium,
            "has_manual": has_manual,
        },
        "failed_repos": [{"api_name": r.api_name, "error": r.error} for r in failed],
    }
    summary_path.write_text(json.dumps(summary, indent=2))
    log.info("Batch summary written to %s", summary_path)

    # Print to stdout
    print(f"\n{'='*60}")
    print(f"  Batch complete: {len(succeeded)}/{len(results)} succeeded")
    print(f"  Duration:       {duration/60:.1f} minutes")
    print(f"  All-HIGH:       {all_high} specs")
    print(f"  Has MEDIUM:     {has_medium} specs (review recommended)")
    print(f"  Has MANUAL:     {has_manual} specs (review required)")
    if failed:
        print(f"\n  FAILED ({len(failed)}):")
        for r in failed:
            print(f"    - {r.api_name}: {r.error}")
    print(f"{'='*60}\n")


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description="CSV-driven spec-engine batch loader")
    parser.add_argument("--csv",          required=True, help="Path to API inventory CSV")
    parser.add_argument("--config",       default="config.yaml", help="Path to spec-engine config.yaml")
    parser.add_argument("--spec-dir",     default="./specs",     help="Output directory for generated specs")
    parser.add_argument("--log-dir",      default="./logs",      help="Output directory for per-repo logs")
    parser.add_argument("--report",       default="./batch_report.csv",   help="Output batch report CSV")
    parser.add_argument("--summary",      default="./batch_summary.json", help="Output batch summary JSON")
    parser.add_argument("--workers",      type=int, default=8,   help="Parallel workers")
    parser.add_argument("--publish",      action="store_true",   help="Publish specs to Explorer catalog")
    parser.add_argument("--retry-failed", metavar="PREV_REPORT", help="Only process rows that failed in a previous report")
    parser.add_argument("--dry-run",      action="store_true",   help="Clone and validate only; skip publish")
    args = parser.parse_args()

    spec_dir = Path(args.spec_dir)
    log_dir  = Path(args.log_dir)
    spec_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)

    # Git auth token (for HTTPS clones)
    git_token = os.environ.get("GIT_TOKEN") or os.environ.get("GITHUB_TOKEN")

    # Load CSV
    rows = load_csv(Path(args.csv))
    if not rows:
        log.error("No valid rows found in CSV. Exiting.")
        return 1

    # Filter to retry-failed only if requested
    if args.retry_failed:
        failed_names = set(load_failed_from_report(Path(args.retry_failed)))
        rows = [r for r in rows if r.api_name in failed_names]
        log.info("Retry mode: %d rows to re-process", len(rows))

    do_publish = args.publish and not args.dry_run
    started = datetime.now(timezone.utc)
    results: List[RepoResult] = []

    log.info("Starting batch: %d repos, %d workers, publish=%s", len(rows), args.workers, do_publish)

    with concurrent.futures.ProcessPoolExecutor(max_workers=args.workers) as executor:
        future_to_row = {
            executor.submit(
                process_row, row, spec_dir, log_dir, args.config, do_publish, git_token
            ): row
            for row in rows
        }
        for future in concurrent.futures.as_completed(future_to_row):
            row = future_to_row[future]
            try:
                result = future.result()
            except Exception as exc:
                result = RepoResult(
                    api_name=row.api_name,
                    repo_url=row.repo_url,
                    success=False,
                    error=str(exc),
                )
            results.append(result)
            status = "OK  " if result.success else "FAIL"
            print(f"[{status}] {result.api_name:40s}  routes={result.routes_found:4d}  {result.duration_seconds:.1f}s")

    write_batch_report(results, Path(args.report))
    write_batch_summary(results, started, Path(args.summary))

    failed_count = sum(1 for r in results if not r.success)
    return 0 if failed_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
