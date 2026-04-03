#!/usr/bin/env bash
set -euo pipefail

# Update agent-specific context files with new technology from the plan.
# Usage: ./update-agent-context.sh opencode

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
AGENT_TYPE="${1:-opencode}"

# For Claude Code, the context is in CLAUDE.md — we don't auto-modify it.
# Instead, report what should be reviewed.
echo "Agent context update for: $AGENT_TYPE"
echo "Project root: $REPO_ROOT"
echo ""
echo "Review CLAUDE.md and .specify/memory/constitution.md for any needed updates."
echo "No automatic modifications made — constitution and CLAUDE.md are manually maintained."
