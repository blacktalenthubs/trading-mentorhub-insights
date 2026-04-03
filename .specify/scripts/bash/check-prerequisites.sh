#!/usr/bin/env bash
set -euo pipefail

# Check prerequisites for speckit commands.
# Returns JSON with feature paths for the current branch.
# Usage: ./check-prerequisites.sh --json [--require-tasks]

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
SPECS_DIR="$REPO_ROOT/specs"

JSON_MODE=false
REQUIRE_TASKS=false

while [[ $# -gt 0 ]]; do
  case $1 in
    --json) JSON_MODE=true; shift ;;
    --require-tasks) REQUIRE_TASKS=true; shift ;;
    *) shift ;;
  esac
done

# Get current branch name
BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "main")
FEATURE_DIR="$SPECS_DIR/$BRANCH"

# If not on a feature branch, try to find the most recent spec
if [[ ! -d "$FEATURE_DIR" ]]; then
  # Look for any specs directory
  LATEST=$(ls -1d "$SPECS_DIR"/*/ 2>/dev/null | tail -1 || echo "")
  if [[ -n "$LATEST" ]]; then
    FEATURE_DIR="${LATEST%/}"
  else
    echo "Error: No feature directory found at $FEATURE_DIR" >&2
    exit 1
  fi
fi

FEATURE_SPEC="$FEATURE_DIR/spec.md"
IMPL_PLAN="$FEATURE_DIR/plan.md"
TASKS_FILE="$FEATURE_DIR/tasks.md"

# Check what docs exist
AVAILABLE_DOCS="["
[[ -f "$FEATURE_SPEC" ]] && AVAILABLE_DOCS+="\"spec.md\","
[[ -f "$IMPL_PLAN" ]] && AVAILABLE_DOCS+="\"plan.md\","
[[ -f "$TASKS_FILE" ]] && AVAILABLE_DOCS+="\"tasks.md\","
[[ -f "$FEATURE_DIR/data-model.md" ]] && AVAILABLE_DOCS+="\"data-model.md\","
[[ -f "$FEATURE_DIR/research.md" ]] && AVAILABLE_DOCS+="\"research.md\","
AVAILABLE_DOCS="${AVAILABLE_DOCS%,}]"

if $REQUIRE_TASKS && [[ ! -f "$TASKS_FILE" ]]; then
  echo "Error: tasks.md required but not found at $TASKS_FILE" >&2
  exit 1
fi

if $JSON_MODE; then
  TASKS_LINE=""
  if [[ -f "$TASKS_FILE" ]]; then
    TASKS_LINE="\"TASKS\": \"$TASKS_FILE\","
  fi
  cat <<ENDJSON
{
  "FEATURE_DIR": "$FEATURE_DIR",
  "FEATURE_SPEC": "$FEATURE_SPEC",
  "IMPL_PLAN": "$IMPL_PLAN",
  $TASKS_LINE
  "AVAILABLE_DOCS": $AVAILABLE_DOCS
}
ENDJSON
else
  echo "Feature dir: $FEATURE_DIR"
  echo "Available: $AVAILABLE_DOCS"
fi
