# Contract — Image-input variant of `POST /api/v1/intel/analyze-chart`

**Phase**: A (Image upload from browser)
**Affected file**: `api/app/routers/intel.py`

## Request shape (Pydantic discriminated union)

```python
from typing import Literal, Annotated, Union
from pydantic import BaseModel, Field

class OHLCBar(BaseModel):
    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: int | float

class AnalyzeChartContext(BaseModel):
    """Existing flow — symbol + bars from the chart already on screen."""
    kind: Literal["context"] = "context"
    symbol: str = Field(..., min_length=1, max_length=10)
    timeframe: str = Field(..., pattern="^[0-9]+[mhdwM]$")
    ohlcv_bars: list[OHLCBar] | None = Field(None, max_length=120)

class AnalyzeChartImage(BaseModel):
    """New flow — base64-encoded screenshot."""
    kind: Literal["image"] = "image"
    image_data: str = Field(..., description="base64-encoded PNG or JPEG, max ~4 MB after b64 decoding")
    mime_type: Literal["image/png", "image/jpeg"] = "image/png"
    hint_symbol: str | None = Field(None, max_length=10, description="Optional symbol hint if the screenshot doesn't include the ticker clearly")
    hint_timeframe: str | None = Field(None, pattern="^[0-9]+[mhdwM]$")

AnalyzeChartRequest = Annotated[
    Union[AnalyzeChartContext, AnalyzeChartImage],
    Field(discriminator="kind"),
]
```

**Backward compat**: existing clients that POST without `kind` get rejected by Pydantic with a clear error. Frontend rolls out the new shape before the backend rejects the old.

## Validation rules

| Field | Rule | On fail |
|-------|------|---------|
| `image_data` length (decoded) | ≤ 4 MB | 413 "Image too large; max 4 MB" |
| `image_data` magic bytes | Match PNG (`\x89PNG`) or JPEG (`\xff\xd8\xff`) | 400 "Unsupported image format" |
| `hint_symbol` | Optional; regex `^[A-Z0-9\-]+$` if provided | 400 "Invalid symbol hint" |
| `hint_timeframe` | Optional; same regex as context | 400 |

## Response shape (unchanged)

Still SSE with events: `chunk`, `plan`, `reasoning`, `higher_tf`, `done`. The `plan` event payload shape is the same regardless of `kind`. The `done` event includes:

```json
{
  "event": "done",
  "data": {
    "analysis_id": 12345,
    "remaining": 23,
    "input_kind": "image",
    "extraction_confidence": 0.87
  }
}
```

When `extraction_confidence < 0.60` (configurable threshold), the endpoint MUST instead emit an `event: error` with `code: "low_confidence_extraction"` and a recommendation to re-capture (FR-318), AND MUST NOT decrement quota (FR-317 parallel).

## Error events (extended)

| `event` | `code` | When | Quota decrement? |
|---------|--------|------|-------------------|
| `error` | `low_confidence_extraction` | Vision parse confidence < 0.60 | No |
| `error` | `vision_provider_degraded` | 5xx from Anthropic vision | No |
| `error` | `quota_exhausted` | `check_usage_limit` returns 0 | (already decremented) |
| `error` | `image_too_large` | Pre-validation fail | No |
| `error` | `unsupported_format` | Pre-validation fail | No |

## Routing & dispatch in the endpoint

```python
async def analyze_chart(body: AnalyzeChartRequest, ...):
    if body.kind == "context":
        # Existing path: assemble_analysis_context → build_analysis_prompt → ask_coach (text)
        ...
    else:  # body.kind == "image"
        # New path: build_vision_prompt → vision-capable model
        prompt = build_vision_prompt(body.image_data, body.mime_type, body.hint_symbol, body.hint_timeframe)
        confidence = await _run_sync(_extract_confidence, body.image_data)
        if confidence < VISION_CONFIDENCE_THRESHOLD:
            yield {"event": "error", "data": json.dumps({"code": "low_confidence_extraction", "confidence": confidence})}
            return  # NO quota decrement, NO partial save
        # ... otherwise proceed identically to context path
```

## Frontend payload examples

**Existing (context) — no change**:
```json
{
  "kind": "context",
  "symbol": "NVDA",
  "timeframe": "5m",
  "ohlcv_bars": [...]
}
```

**New (image)**:
```json
{
  "kind": "image",
  "image_data": "iVBORw0KGgoAAAANSUhEUgAA...",
  "mime_type": "image/png",
  "hint_symbol": "NVDA",
  "hint_timeframe": "5m"
}
```

## Acceptance gate

The image path ships when:
1. POST with valid image returns SSE `plan` event within 15 s for 90% of test images (FR-302).
2. Free-tier POST without `kind` discriminator OR exceeding quota returns appropriate error event.
3. Low-confidence images return `low_confidence_extraction` and do NOT decrement quota.
4. DB row is created with `input_kind="image"` and `image_ref` populated per storage policy.
