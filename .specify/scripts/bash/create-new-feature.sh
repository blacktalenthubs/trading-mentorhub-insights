#!/usr/bin/env bash
set -euo pipefail

# Create a new feature branch and spec file structure.
# Usage: ./create-new-feature.sh --json "feature description" --number N --short-name "name"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
SPECS_DIR="$REPO_ROOT/specs"

# Parse arguments
JSON_MODE=false
NUMBER=""
SHORT_NAME=""
DESCRIPTION=""

while [[ $# -gt 0 ]]; do
  case $1 in
    --json) JSON_MODE=true; shift ;;
    --number) NUMBER="$2"; shift 2 ;;
    --short-name) SHORT_NAME="$2"; shift 2 ;;
    *) DESCRIPTION="$1"; shift ;;
  esac
done

if [[ -z "$SHORT_NAME" || -z "$NUMBER" ]]; then
  echo "Error: --number and --short-name are required" >&2
  exit 1
fi

BRANCH_NAME="${NUMBER}-${SHORT_NAME}"
FEATURE_DIR="$SPECS_DIR/$BRANCH_NAME"
SPEC_FILE="$FEATURE_DIR/spec.md"

# Create feature directory structure
mkdir -p "$FEATURE_DIR/checklists"
mkdir -p "$FEATURE_DIR/contracts"

# Create spec file from template
TEMPLATE="$REPO_ROOT/.specify/templates/spec-template.md"
if [[ -f "$TEMPLATE" ]]; then
  cp "$TEMPLATE" "$SPEC_FILE"
else
  echo "# Feature Specification: $SHORT_NAME" > "$SPEC_FILE"
  echo "" >> "$SPEC_FILE"
  echo "$DESCRIPTION" >> "$SPEC_FILE"
fi

# Create and checkout branch
git checkout -b "$BRANCH_NAME" 2>/dev/null || git checkout "$BRANCH_NAME"

if $JSON_MODE; then
  cat <<ENDJSON
{
  "BRANCH_NAME": "$BRANCH_NAME",
  "SPEC_FILE": "$SPEC_FILE",
  "FEATURE_DIR": "$FEATURE_DIR"
}
ENDJSON
else
  echo "Created feature: $BRANCH_NAME"
  echo "Spec file: $SPEC_FILE"
fi
