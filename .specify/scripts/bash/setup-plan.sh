#!/usr/bin/env bash
set -euo pipefail

# Set up planning phase — copy plan template and return paths.
# Usage: ./setup-plan.sh --json

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
SPECS_DIR="$REPO_ROOT/specs"

JSON_MODE=false
while [[ $# -gt 0 ]]; do
  case $1 in
    --json) JSON_MODE=true; shift ;;
    *) shift ;;
  esac
done

# Get current branch
BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "main")
FEATURE_DIR="$SPECS_DIR/$BRANCH"

# Fallback: find most recent feature dir
if [[ ! -d "$FEATURE_DIR" ]]; then
  LATEST=$(ls -1d "$SPECS_DIR"/*/ 2>/dev/null | tail -1 || echo "")
  if [[ -n "$LATEST" ]]; then
    FEATURE_DIR="${LATEST%/}"
    BRANCH=$(basename "$FEATURE_DIR")
  else
    echo "Error: No feature directory found" >&2
    exit 1
  fi
fi

FEATURE_SPEC="$FEATURE_DIR/spec.md"
IMPL_PLAN="$FEATURE_DIR/plan.md"

# Verify spec exists
if [[ ! -f "$FEATURE_SPEC" ]]; then
  echo "Error: spec.md not found at $FEATURE_SPEC. Run /speckit.specify first." >&2
  exit 1
fi

# Copy plan template if plan doesn't exist yet
if [[ ! -f "$IMPL_PLAN" ]]; then
  TEMPLATE="$REPO_ROOT/.specify/templates/plan-template.md"
  if [[ -f "$TEMPLATE" ]]; then
    cp "$TEMPLATE" "$IMPL_PLAN"
  else
    echo "# Implementation Plan" > "$IMPL_PLAN"
  fi
fi

if $JSON_MODE; then
  cat <<ENDJSON
{
  "FEATURE_SPEC": "$FEATURE_SPEC",
  "IMPL_PLAN": "$IMPL_PLAN",
  "SPECS_DIR": "$SPECS_DIR",
  "BRANCH": "$BRANCH"
}
ENDJSON
else
  echo "Spec: $FEATURE_SPEC"
  echo "Plan: $IMPL_PLAN"
  echo "Branch: $BRANCH"
fi
