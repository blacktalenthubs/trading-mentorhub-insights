# Contract — Spec 46 Supersedence Notice

**Status**: Phase 1 design artifact for Spec 49 FR-416. Apply in Phase D T-D2.
**Target file**: `/Users/mentorhub/Documents/master-domain-hub/trade-analytics/specs/46-stable-state-reference/spec.md`
**Action**: prepend the block below ABOVE all existing content. Existing V1 baseline content stays untouched as historical record.

---

## Text to prepend (copy exactly)

```markdown
> ⚠️ **SUPERSEDED — 2026-05-16**
>
> This spec is the V1 stable-state reference (captured 2026-04-16, git anchor `known-good-2026-04-16`, commit `17d60a1`). It documented the production behavior of the V1 stack at the moment V1 work was frozen.
>
> **The V1 stack itself has since been retired.** Production now runs on the V2 Pine + `tv_webhook` + `triage-agent` pipeline. Many of the modules this spec calls "protected" have been deleted as part of [Spec 49 (V1 Cleanup)](../49-v1-cleanup/spec.md), which is the buildable child of [Spec 48 (V3 Cleanup & Paid AI Revamp manifest)](../48-v3-cleanup-and-paid-ai-revamp/spec.md).
>
> **What this means**:
>
> - **For historical / forensic reading**: the V1 baseline content below is preserved unchanged. Use it to understand what V1 did and why specific decisions were made.
> - **For ANY decision about current production behavior**: read the [V3 manifest](../48-v3-cleanup-and-paid-ai-revamp/spec.md) and its children (49–54). Do not treat the "protected files" list below as current.
> - **For "what files can I touch?"**: read the post-cleanup root `CLAUDE.md`, which lists the current V2 protected files. The list below is V1-era and now misleading.
> - **The git anchor `known-good-2026-04-16`** still exists and remains the V1 baseline you can restore to if you ever need to. Restoring it would un-ship V2 — only do this if you have a very specific reason.
>
> Original V1 baseline content begins below this notice.

---

```

(Note: the trailing horizontal rule `---` separates the notice from the V1 content.)

---

## Verification

After prepending:

1. Open the file. The first content visible MUST be the SUPERSEDED block.
2. The V1 "How to use this spec" section MUST appear below the notice, unchanged.
3. No other edits to the file body.

Commit message: `docs: mark spec 46 superseded by spec 48 V3 manifest (spec 49 FR-416)`.
