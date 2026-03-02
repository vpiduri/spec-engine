#!/usr/bin/env bash
# tools/set_repo_variables.sh
# Sets GitHub repo variables for each row in the API inventory CSV.
#
# Usage:
#   export GH_TOKEN="ghp_xxxx"   # GitHub PAT with repo + admin:org scopes
#   bash tools/set_repo_variables.sh --csv api_inventory.csv
#   bash tools/set_repo_variables.sh --csv api_inventory.csv --dry-run
#
# Requires: gh CLI (https://cli.github.com/) authenticated with admin:org scope.
#
# What it does per repo:
#   - Sets API_GATEWAY, API_OWNER, API_LIFECYCLE variables
#   - Sets API_FRAMEWORK variable (only if non-empty in CSV)
#   - Applies the "api-service" topic so Required Workflow policy can target the repo

set -euo pipefail

CSV=""
DRY_RUN=0

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        --csv)       CSV="$2"; shift 2 ;;
        --dry-run)   DRY_RUN=1; shift ;;
        *) echo "Unknown argument: $1" >&2; exit 1 ;;
    esac
done

if [[ -z "$CSV" ]]; then
    echo "Usage: $0 --csv <api_inventory.csv> [--dry-run]" >&2
    exit 1
fi

if [[ ! -f "$CSV" ]]; then
    echo "ERROR: CSV file not found: $CSV" >&2
    exit 1
fi

if ! command -v gh &>/dev/null; then
    echo "ERROR: gh CLI not found. Install from https://cli.github.com/" >&2
    exit 1
fi

# ──────────────────────────────────────────────────────────────────────────────
# Helper: create-or-update a repo variable
# ──────────────────────────────────────────────────────────────────────────────
set_var() {
    local repo_slug="$1"
    local var_name="$2"
    local var_value="$3"

    if [[ $DRY_RUN -eq 1 ]]; then
        echo "    [DRY-RUN] would set ${var_name}=${var_value}"
        return 0
    fi

    # Try POST (create); fall back to PATCH (update) if it already exists
    gh api "repos/${repo_slug}/actions/variables" \
        --method POST \
        --field name="${var_name}" \
        --field value="${var_value}" 2>/dev/null \
    || gh api "repos/${repo_slug}/actions/variables/${var_name}" \
        --method PATCH \
        --field value="${var_value}"
}

# ──────────────────────────────────────────────────────────────────────────────
# Helper: apply topic to repo (needed for Required Workflow policy targeting)
# ──────────────────────────────────────────────────────────────────────────────
add_topic() {
    local repo_slug="$1"
    local topic="$2"

    if [[ $DRY_RUN -eq 1 ]]; then
        echo "    [DRY-RUN] would add topic: ${topic}"
        return 0
    fi

    # Get existing topics, add ours, PUT back
    existing=$(gh api "repos/${repo_slug}/topics" --jq '.names[]' 2>/dev/null | tr '\n' ' ')
    if echo "$existing" | grep -qw "$topic"; then
        return 0   # already present
    fi

    # Build new names array: "existing topic1 topic2 new-topic"
    new_names=$(echo "$existing $topic" | xargs -n1 | sort -u | jq -R . | jq -s .)
    gh api "repos/${repo_slug}/topics" \
        --method PUT \
        --input <(jq -n --argjson names "$new_names" '{"names": $names}') >/dev/null
}

# ──────────────────────────────────────────────────────────────────────────────
# Main loop — skip header row
# ──────────────────────────────────────────────────────────────────────────────
TOTAL=0
ERRORS=0

# Read CSV with header: api_name,team,gateway,repo_url,framework,lifecycle,owner,env,exclude_paths
{
    read -r _header   # skip header line
    while IFS=, read -r api_name team gateway repo_url framework lifecycle owner env exclude_paths; do
        # Trim whitespace (handles Windows line endings too)
        api_name="${api_name//[$'\r\n ']}"
        repo_url="${repo_url//[$'\r\n ']}"
        gateway="${gateway//[$'\r\n ']}"
        framework="${framework//[$'\r\n ']}"
        lifecycle="${lifecycle//[$'\r\n ']}"
        owner="${owner//[$'\r\n ']}"
        team="${team//[$'\r\n ']}"

        [[ -z "$api_name" || -z "$repo_url" ]] && continue

        # Derive org/repo slug from URL
        repo_slug=$(echo "$repo_url" | sed 's|https://github.com/||' | sed 's|\.git$||')

        echo "[$api_name] Setting variables for ${repo_slug} ..."

        set_var "$repo_slug" "API_GATEWAY"   "${gateway:-unknown}"
        set_var "$repo_slug" "API_OWNER"     "${owner:-$team}"
        set_var "$repo_slug" "API_LIFECYCLE" "${lifecycle:-production}"

        if [[ -n "$framework" ]]; then
            set_var "$repo_slug" "API_FRAMEWORK" "$framework"
        fi

        add_topic "$repo_slug" "api-service"

        echo "  Done: ${repo_slug}"
        TOTAL=$((TOTAL + 1))
    done
} < "$CSV" || { ERRORS=$((ERRORS + 1)); }

echo ""
echo "Processed ${TOTAL} repos."
[[ $ERRORS -gt 0 ]] && echo "Errors: ${ERRORS}" && exit 1
echo "All repo variables set successfully."
