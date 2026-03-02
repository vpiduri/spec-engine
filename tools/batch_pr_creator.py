#!/usr/bin/env python3
"""
batch_pr_creator.py — Opens a PR in each repo from the CSV to add the spec-engine CI step.

Usage:
    python3 tools/batch_pr_creator.py \
        --csv api_inventory.csv \
        --template tools/templates/spec-engine-step.yml \
        --workers 8

Requires:
    - gh CLI authenticated (gh auth login)
    - git configured with push access to target repos
    - GIT_TOKEN env var or SSH key for clone auth
"""

import argparse
import csv
import concurrent.futures
import os
import subprocess
import sys
import tempfile
from pathlib import Path


PR_TITLE = "chore: add spec-engine OpenAPI spec generation step"
PR_BODY = """\
## Summary

Adds an automated OpenAPI 3.1 spec generation step using spec-engine.

- Runs on every push to `main`
- Generates and publishes spec to the API Explorer catalog
- No application code changes required

**Review:** The step is non-blocking — it will not fail your build if spec generation fails
during the initial stabilization period.

Raised by the SRE Frameworks team as part of the API catalog rollout.
"""


def _inject_token(repo_url: str) -> str:
    """Inject GIT_TOKEN into HTTPS clone URL for authentication."""
    git_token = os.environ.get("GIT_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if git_token and repo_url.startswith("https://"):
        return repo_url.replace("https://", f"https://{git_token}@", 1)
    return repo_url


def add_spec_step_pr(row: dict, template: str) -> dict:
    api_name = row["api_name"]
    repo_url = row["repo_url"]

    with tempfile.TemporaryDirectory(prefix=f"spec_pr_{api_name}_") as tmp:
        clone_dir = Path(tmp) / "repo"
        try:
            subprocess.run(
                ["git", "clone", "--depth", "1", "--quiet",
                 _inject_token(repo_url), str(clone_dir)],
                check=True, timeout=90, capture_output=True,
            )
        except subprocess.CalledProcessError as e:
            return {"api_name": api_name, "pr_url": "", "success": False,
                    "error": f"clone failed: {e.stderr.decode().strip()[:120]}"}
        except subprocess.TimeoutExpired:
            return {"api_name": api_name, "pr_url": "", "success": False,
                    "error": "clone timeout"}

        # Write workflow file
        wf_dir = clone_dir / ".github" / "workflows"
        wf_dir.mkdir(parents=True, exist_ok=True)
        (wf_dir / "spec-engine.yml").write_text(template)

        # Commit and push branch
        branch = "chore/add-spec-engine"
        try:
            subprocess.run(
                ["git", "-C", str(clone_dir), "checkout", "-b", branch],
                check=True, capture_output=True,
            )
            subprocess.run(
                ["git", "-C", str(clone_dir), "add",
                 ".github/workflows/spec-engine.yml"],
                check=True, capture_output=True,
            )
            subprocess.run(
                ["git", "-C", str(clone_dir), "commit", "-m", PR_TITLE],
                check=True, capture_output=True,
            )
            subprocess.run(
                ["git", "-C", str(clone_dir), "push", "origin", branch],
                check=True, capture_output=True,
            )
        except subprocess.CalledProcessError as e:
            return {"api_name": api_name, "pr_url": "", "success": False,
                    "error": f"git error: {e.stderr.decode().strip()[:120]}"}

        # Open PR via GitHub CLI
        result = subprocess.run(
            ["gh", "pr", "create",
             "--title", PR_TITLE,
             "--body", PR_BODY,
             "--base", "main",
             "--head", branch,
             ],
            capture_output=True, text=True, cwd=str(clone_dir), timeout=30,
        )
        pr_url = result.stdout.strip()
        if result.returncode != 0:
            return {"api_name": api_name, "pr_url": "", "success": False,
                    "error": result.stderr.strip()[:120]}
        return {"api_name": api_name, "pr_url": pr_url, "success": True, "error": ""}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Open PRs to add spec-engine CI step to repos in a CSV"
    )
    parser.add_argument("--csv",      required=True,
                        help="Path to API inventory CSV (same format as batch_loader.py)")
    parser.add_argument("--template", default="tools/templates/spec-engine-step.yml",
                        help="Path to workflow YAML template to add to each repo")
    parser.add_argument("--workers",  type=int, default=4,
                        help="Parallel workers (keep low to avoid GitHub rate limits)")
    parser.add_argument("--dry-run",  action="store_true",
                        help="Print what would happen without opening any PRs")
    args = parser.parse_args()

    template_path = Path(args.template)
    if not template_path.exists():
        print(f"ERROR: template not found: {template_path}", file=sys.stderr)
        return 1
    template = template_path.read_text()

    rows = []
    with open(args.csv, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("api_name", "").strip() and row.get("repo_url", "").strip():
                rows.append(row)

    if not rows:
        print("ERROR: no valid rows found in CSV", file=sys.stderr)
        return 1

    print(f"Processing {len(rows)} repos with {args.workers} workers")

    if args.dry_run:
        for row in rows:
            print(f"[DRY-RUN] Would open PR in: {row['repo_url']}")
        return 0

    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(add_spec_step_pr, row, template): row
            for row in rows
        }
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            if result["success"]:
                print(f"[PR OPENED] {result['api_name']}: {result['pr_url']}")
            else:
                print(f"[FAILED]    {result['api_name']}: {result.get('error', 'unknown')}")
            results.append(result)

    opened = sum(1 for r in results if r["success"])
    failed = len(results) - opened
    print(f"\nPRs opened: {opened}/{len(results)}" + (f"  ({failed} failed)" if failed else ""))
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
