# Data Model Delta — Spec 51

**Purpose**: Spec 51 is an extension of an existing live feature; the only schema change is adding two columns to the existing `chart_analysis` table to distinguish image-input rows from chart-context rows.

## Existing table

`chart_analysis` (per `api/app/models/chart_analysis.py`, verified to exist in Spec 49 audit):

| Column | Type | Notes |
|--------|------|-------|
| `id` | int PK | |
| `user_id` | int FK → users.id | Account scope |
| `symbol` | str | e.g. "NVDA" |
| `timeframe` | str | e.g. "5m", "1h", "1d" |
| `plan` | JSON | Structured trade plan (entry, stop, t1, t2, invalidation, etc.) |
| `reasoning` | text | LLM reasoning text |
| `higher_tf_summary` | text | Higher-TF context |
| `model` | str | LLM model used |
| `created_at` | timestamp | |
| `confluence_score` | int / float | Optional scoring |

*Verify the exact column list at implementation time — this is a best-effort summary.*

## Added columns (Phase A)

| Column | Type | Default | Notes |
|--------|------|---------|-------|
| `input_kind` | varchar(16) NOT NULL | `"context"` | Discriminator: `"context"` (today's flow — symbol + bars) OR `"image"` (paste/upload OR TV MCP capture) |
| `image_ref` | varchar(512) NULL | `NULL` | Reference to the source image. Two storage modes (operator chooses): inline base64 hash for retrieval from a sibling table, OR S3/R2 object key. NULL when `input_kind="context"`. |
| `extraction_confidence` | float NULL | `NULL` | Vision-extraction confidence score 0..1. Populated when `input_kind="image"`. NULL when `input_kind="context"`. Used by FR-318 ("low confidence → recapture, no hallucination"). |

## Alembic migration outline

```python
# alembic/versions/XXXX_spec51_image_input.py
"""spec 51 — add image-input columns to chart_analysis."""

revision = "XXXX_spec51"
down_revision = "<previous>"

def upgrade() -> None:
    op.add_column(
        "chart_analysis",
        sa.Column("input_kind", sa.String(16), nullable=False, server_default="context"),
    )
    op.add_column(
        "chart_analysis",
        sa.Column("image_ref", sa.String(512), nullable=True),
    )
    op.add_column(
        "chart_analysis",
        sa.Column("extraction_confidence", sa.Float(), nullable=True),
    )

def downgrade() -> None:
    op.drop_column("chart_analysis", "extraction_confidence")
    op.drop_column("chart_analysis", "image_ref")
    op.drop_column("chart_analysis", "input_kind")
```

Backward compat: existing rows get `input_kind="context"` via the default; `image_ref` and `extraction_confidence` stay NULL. Frontend `AnalysisHistory.tsx` doesn't need a migration — it just renders whatever the row has.

## Other model changes

None. No new tables. No FK additions. No index changes (the existing per-user index handles both kinds).

## Per-image storage policy

| Mode | Pros | Cons |
|------|------|------|
| **Inline base64 hash + sibling table** (`chart_analysis_image(hash PK, bytes BLOB)`) | No object-store dep | DB bloat; ~150 KB per image × 1000 daily images = 150 MB/day in Postgres |
| **S3/R2 key** | Clean, scalable | New dep, IAM, lifecycle, presigned URLs |
| **Discard after analysis** (don't store image) | Smallest footprint | Can't replay analysis; can't troubleshoot bad responses |

**Recommendation**: ship Phase A with **discard after analysis** (image is sent to Claude, response saved, image bytes dropped). Add `image_ref="discarded"` as a sentinel. If retention is needed later, add S3 in a follow-up spec. This matches spec 49's posture for screen-capture frames (extract text, drop raw frame).

## Tests

| Test | File | Status |
|------|------|--------|
| Existing | `tests/test_chart_analyzer.py` | Verified passing post-Spec 49 |
| New (Phase A) | `tests/test_chart_analyzer_vision.py` | Mocks vision API; asserts schema + parse |
| New (Phase E) | Manual 30-chart audit | Operator-driven; SC-307 |
