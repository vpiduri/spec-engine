#!/usr/bin/env bash
# tools/validate_all_specs.sh
# Validates all generated specs in the specs/ directory.
#
# Usage:
#   bash tools/validate_all_specs.sh
#   bash tools/validate_all_specs.sh --specs-dir ./specs --config config.yaml
#   bash tools/validate_all_specs.sh --redocly     # also run redocly lint
#
# Exit code: 0 if all pass, 1 if any fail.

set -euo pipefail

SPECS_DIR="./specs"
CONFIG="config.yaml"
RUN_REDOCLY=0
PASS=0
FAIL=0
FAIL_NAMES=()

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        --specs-dir) SPECS_DIR="$2"; shift 2 ;;
        --config)    CONFIG="$2";    shift 2 ;;
        --redocly)   RUN_REDOCLY=1;  shift ;;
        *) echo "Unknown argument: $1" >&2; exit 1 ;;
    esac
done

if [[ ! -d "$SPECS_DIR" ]]; then
    echo "ERROR: specs directory not found: $SPECS_DIR" >&2
    exit 1
fi

shopt -s nullglob
specs=("$SPECS_DIR"/*.yaml "$SPECS_DIR"/*.yml)
shopt -u nullglob

if [[ ${#specs[@]} -eq 0 ]]; then
    echo "No spec files found in $SPECS_DIR"
    exit 0
fi

echo "Validating ${#specs[@]} spec(s) in ${SPECS_DIR} ..."
echo ""

for spec in "${specs[@]}"; do
    name=$(basename "$spec")

    # Run spec-engine validate
    if spec-engine validate "$spec" --config "$CONFIG" 2>/dev/null; then
        echo "  [PASS] $name"
        PASS=$((PASS + 1))

        # Optionally run redocly lint for extra OpenAPI conformance checks
        if [[ $RUN_REDOCLY -eq 1 ]] && command -v redocly &>/dev/null; then
            if ! redocly lint "$spec" --format=summary 2>/dev/null; then
                echo "  [WARN] $name — redocly found issues (see above)"
            fi
        fi
    else
        echo "  [FAIL] $name"
        FAIL=$((FAIL + 1))
        FAIL_NAMES+=("$name")
    fi
done

echo ""
echo "Validation summary: ${PASS} passed, ${FAIL} failed"

if [[ $FAIL -gt 0 ]]; then
    echo ""
    echo "Failed specs:"
    for n in "${FAIL_NAMES[@]}"; do
        echo "  - $n"
    done
    echo ""
    echo "Re-run with verbose output for a specific spec:"
    echo "  spec-engine validate ${SPECS_DIR}/<name>.yaml --config ${CONFIG}"
    exit 1
fi

exit 0
