"""STUB — Spec 49 cleanup deleted the original confluence.py.

The original module computed multi-source confluence scores. The only
remaining consumer is `analytics/game_plan.py:32`, which imports lazily
inside `generate_game_plan`. Without this stub, /intel/game-plan would
fail at runtime when game_plan computes confluence.

This stub returns a neutral "no confluence" result so the game-plan
endpoint continues to respond rather than 500.

ACTION REQUIRED: restore the original file from git history to get
real confluence scoring back.
"""

from __future__ import annotations

import logging

logger = logging.getLogger("confluence_stub")
_warned = False


def compute_confluence(*args, **kwargs) -> dict:
    """Return a neutral confluence result.

    Original signature: compute_confluence(scan_result, ...) → dict with
    keys like {'score': int, 'sources': list, 'label': str}.
    """
    global _warned
    if not _warned:
        logger.warning(
            "analytics.confluence is a STUB (Spec 49 cleanup). "
            "Returning neutral confluence scores."
        )
        _warned = True
    return {"score": 0, "sources": [], "label": "neutral"}
