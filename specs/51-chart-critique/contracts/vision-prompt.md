# Contract — Vision-input prompt template (Phase A engine)

**Phase**: A
**Affected file**: `analytics/chart_analyzer.py` — add `build_vision_prompt()` and `_extract_confidence()` functions.

## `build_vision_prompt(image_b64, mime_type, hint_symbol, hint_timeframe) → list[message]`

Returns an Anthropic Messages API payload (list of message dicts) ready to pass to the SDK's `messages.create(...)`.

### System prompt (the role)

```
You are a trading-chart analyst. The user will paste a screenshot of a price chart
from TradingView or another charting platform. Your job is to read the chart and
return a structured trade plan.

You analyze the chart you can SEE. Do not make up details that aren't visible. If
the chart is unclear, blurry, partial, or doesn't show enough context, say so
explicitly instead of guessing.

Output format: respond as a single fenced JSON block. After the JSON block, you
MAY include 1-3 short paragraphs of reasoning. The JSON block is REQUIRED.

The JSON schema:
{
  "extraction": {
    "confidence": 0.0-1.0,             // your confidence the chart is readable
    "symbol_detected": "string or null", // what you see on the chart
    "timeframe_detected": "string or null"
  },
  "bias": "LONG" | "SHORT" | "NO_TRADE",
  "setup": "string",                   // e.g., "Bull Flag breakout", "VWAP reclaim"
  "key_levels": {
    "support": [<float>, ...],          // 1-3 prices
    "resistance": [<float>, ...]
  },
  "plan": {
    "entry": <float>,
    "stop": <float>,
    "first_target": <float>,
    "runner_target": <float | null>,
    "invalidation": "string"
  },
  "confidence_note": "string"          // 1-2 sentences on what could go wrong
}

When bias is "NO_TRADE", you MAY omit the "plan" block.
When extraction.confidence < 0.60, you MUST omit "plan" and explain in
confidence_note what made the chart unreadable.
```

### User message (the image + hints)

```python
[
  {
    "role": "user",
    "content": [
      {
        "type": "image",
        "source": {
          "type": "base64",
          "media_type": mime_type,
          "data": image_b64,
        },
      },
      {
        "type": "text",
        "text": _build_hint_text(hint_symbol, hint_timeframe),
      },
    ],
  },
]
```

### Hint text helper

```python
def _build_hint_text(hint_symbol, hint_timeframe) -> str:
    parts = ["Analyze this chart and return the structured trade plan."]
    if hint_symbol:
        parts.append(f"The symbol on the chart is probably {hint_symbol}.")
    if hint_timeframe:
        parts.append(f"The timeframe is probably {hint_timeframe}.")
    if not hint_symbol and not hint_timeframe:
        parts.append("Try to read the symbol and timeframe from the chart itself.")
    return " ".join(parts)
```

## Model choice

- **Default**: `claude-3-5-sonnet-20241022` (or the latest vision-capable Sonnet at implementation time)
- **Configurable** via env: `CHART_CRITIQUE_VISION_MODEL`
- **Fallback** if model unavailable: NONE (text-only Haiku is not a viable fallback for image input — surface the failure as `vision_provider_degraded`)

## `_extract_confidence(image_b64) → float`

Extracts the model's `extraction.confidence` from its response. Used by the endpoint to short-circuit before saving / streaming if too low. Implementation: call the vision model with a tiny version of the prompt that only asks for `{extraction: {confidence}}`, OR (cheaper) run the full prompt and parse the confidence field from the response.

**Recommendation**: skip the separate confidence pre-call. Run the full prompt, parse the response, check `extraction.confidence`. If low, emit `low_confidence_extraction` error event and don't persist. Costs one full call either way, simpler.

## Parsing the response

Existing `parse_trade_plan(text)` expects a specific text shape. The vision flow's response is JSON. Add a sibling:

```python
def parse_vision_response(text: str) -> dict:
    """Extract the JSON block from a vision response.

    Returns the parsed dict, or raises VisionParseError if the JSON block is
    missing or malformed.
    """
    import json, re

    # Find ```json ... ``` block
    m = re.search(r"```(?:json)?\s*\n(.*?)```", text, re.DOTALL)
    payload = m.group(1).strip() if m else text.strip()

    try:
        data = json.loads(payload)
    except json.JSONDecodeError as e:
        raise VisionParseError(f"could not parse JSON: {e}") from e

    if "extraction" not in data or "bias" not in data:
        raise VisionParseError("missing required fields (extraction, bias)")

    return data
```

## Disclaimer (FR-304 / SC-307)

The endpoint MUST include the disclaimer in the `done` event:

```json
{
  "event": "done",
  "data": {
    "analysis_id": ...,
    "remaining": ...,
    "disclaimer": "AI guidance, not investment advice. Always verify against your own analysis."
  }
}
```

The frontend renders this disclaimer with every analysis (FR-304). UI snapshot test (SC-307) asserts presence.

## Token budget

- Image input: ~1000-3000 input tokens (depends on image dimensions; Anthropic resizes large images automatically)
- Text output: cap at 1024 tokens (enough for the JSON + reasoning; the existing context flow uses 512)
- Per-call cost estimate: ~$0.05-0.10 with Sonnet 3.5 (vs ~$0.005 for the existing text-only Haiku context flow). **10-20× more expensive** — drives the daily cost cap requirement (see plan.md Phase E).
