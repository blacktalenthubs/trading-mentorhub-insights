"""AI-generated short-term / long-term view for a watchlist symbol.

Synthesizes the fundamentals + analyst ratings (and, when available, the
symbol's recent price momentum) into two short paragraphs:

  short_term — days-to-weeks lean (momentum, ratings, EPS surprise potential)
  long_term  — quarters+ lean (business quality, growth, valuation)

Reuses the Anthropic plumbing from alerting/narrator.py: the per-user-or-env
key resolution (`_resolve_api_key`, which honors the ANTHROPIC_ENABLED kill
switch), the haiku model from alert_config, ephemeral prompt caching, and the
"return empty string on any failure" contract.

Uses CLAUDE_MODEL (haiku) deliberately: these are descriptive context
paragraphs, not high-conviction trade theses, so the cheap/fast model keeps an
on-demand multi-symbol refresh affordable.
"""

from __future__ import annotations

import json
import logging
import os

from alert_config import CLAUDE_MODEL
from alerting.narrator import _resolve_api_key
from analytics.fundamentals_fetcher import SymbolFundamentalsData

logger = logging.getLogger(__name__)

# The structured "brief" uses a stronger model than the throwaway short/long
# paragraphs — it's generated once per symbol (admin / on-add) and read by every
# user, so the quality matters more than the per-call cost. Overridable via env.
BRIEF_MODEL = os.environ.get("FUNDAMENTALS_AI_MODEL", "claude-sonnet-4-6")

# Sections the model must return — also the render order on the card.
BRIEF_SECTIONS = (
    "summary", "business", "growth", "valuation",
    "analyst", "bull_case", "risks", "short_term", "long_term",
)

_SYSTEM_PROMPT = """\
You are a trading analyst writing concise, data-grounded context for a stock on \
a trader's watchlist. Given the company's fundamentals, analyst ratings, and \
(optionally) recent price momentum, write TWO views using these exact markers:

SHORT_TERM: A 2-3 sentence read on the next few days to weeks. Lean on momentum, \
analyst sentiment, and any near-term EPS/valuation signal.

LONG_TERM: A 2-3 sentence read on the next several quarters. Lean on business \
quality, earnings growth trajectory, and valuation.

Rules:
- Cite the actual numbers you were given (EPS, P/E, rating counts). Never invent data.
- If a field is missing, reason from what's present — don't mention the gap.
- Plain text only, no markdown.
- Neutral analyst tone, no hype. Education only, not financial advice."""


def _build_user_prompt(f: SymbolFundamentalsData, score: int | None) -> str:
    lines = [
        f"Symbol: {f.symbol}",
        f"Company: {f.company_name}" if f.company_name else "",
        f"Sector / Industry: {f.sector or '?'} / {f.industry or '?'}",
        f"Business: {f.description[:600]}" if f.description else "",
        f"Trailing EPS: {f.trailing_eps}" if f.trailing_eps is not None else "",
        f"Forward EPS: {f.forward_eps}" if f.forward_eps is not None else "",
        f"EPS growth: {f.eps_growth_pct}%" if f.eps_growth_pct is not None else "",
        f"P/E (TTM): {f.pe_ratio}" if f.pe_ratio is not None else "",
        f"Analyst consensus: {f.consensus}" if f.consensus else "",
    ]
    if f.rec_strong_buy is not None:
        lines.append(
            "Analyst ratings — "
            f"strong buy {f.rec_strong_buy}, buy {f.rec_buy}, hold {f.rec_hold}, "
            f"sell {f.rec_sell}, strong sell {f.rec_strong_sell}"
        )
    if score is not None:
        lines.append(f"Recent momentum score: {score}/100")
    return "\n".join(line for line in lines if line)


def _parse_views(text: str) -> tuple[str, str]:
    """Split the model output on the SHORT_TERM / LONG_TERM markers."""
    short_term, long_term = "", ""
    marker = None
    for raw in text.splitlines():
        line = raw.strip()
        upper = line.upper()
        if upper.startswith("SHORT_TERM"):
            marker = "short"
            line = line.split(":", 1)[1].strip() if ":" in line else ""
        elif upper.startswith("LONG_TERM"):
            marker = "long"
            line = line.split(":", 1)[1].strip() if ":" in line else ""
        if not line:
            continue
        if marker == "short":
            short_term += (" " if short_term else "") + line
        elif marker == "long":
            long_term += (" " if long_term else "") + line
    return short_term.strip(), long_term.strip()


def generate_views(
    fundamentals: SymbolFundamentalsData, score: int | None = None,
) -> tuple[str, str]:
    """Return (short_term_view, long_term_view).

    Returns ("", "") when Anthropic is disabled/unkeyed or on any failure —
    the card still renders, the views just show an "unavailable" hint.
    """
    api_key = _resolve_api_key()
    if not api_key:
        return "", ""

    try:
        import anthropic

        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=400,
            system=[{
                "type": "text",
                "text": _SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }],
            messages=[{"role": "user", "content": _build_user_prompt(fundamentals, score)}],
            timeout=15.0,
        )
        return _parse_views(response.content[0].text)
    except Exception:
        logger.exception("Failed to generate views for %s", fundamentals.symbol)
        return "", ""


# ── Structured "investment brief" (the upgraded, admin-generated view) ──

_BRIEF_SYSTEM_PROMPT = """\
You are an equity analyst writing a concise, data-grounded brief to help a \
retail investor understand a stock and make their own decision. You are given \
the company's fundamentals, analyst ratings, margins/growth, and price-vs-moving-\
average trend.

Return ONLY a JSON object (no prose, no markdown fences) with these exact string \
keys, each 1-3 plain sentences:
- "summary": one-line plain-English takeaway of the setup.
- "business": what the company does, the sector/theme it sits in, and its edge.
- "growth": read on revenue/EPS growth and margins — accelerating or slowing?
- "valuation": is the P/E reasonable for the growth? cheap/fair/expensive and why.
- "analyst": what the analyst consensus + distribution imply (don't just restate counts).
- "bull_case": the strongest reasons this could be a long-term winner.
- "risks": the key risks / what would break the thesis (the bear case).
- "short_term": the next few days-to-weeks lean (trend vs 50/200MA, momentum, catalysts).
- "long_term": the multi-quarter / multi-year thesis.

Rules:
- Cite the ACTUAL numbers given (EPS, P/E, margins, growth %, analyst counts, price vs MAs). Never invent data.
- If a field is missing, reason from what's present; don't mention the gap.
- Neutral analyst tone, no hype. Education only — not financial advice.
- Output must be valid JSON and nothing else."""


def _build_brief_prompt(f: SymbolFundamentalsData) -> str:
    def pct(v):
        return f"{v}%" if v is not None else None

    trend = None
    if f.last_price is not None and (f.ma50 is not None or f.ma200 is not None):
        parts = [f"price ${f.last_price}"]
        if f.ma50 is not None:
            parts.append(f"{'above' if f.last_price >= f.ma50 else 'below'} 50DMA ${round(f.ma50, 2)}")
        if f.ma200 is not None:
            parts.append(f"{'above' if f.last_price >= f.ma200 else 'below'} 200DMA ${round(f.ma200, 2)}")
        trend = "Price trend: " + ", ".join(parts)

    lines = [
        f"Symbol: {f.symbol}",
        f"Company: {f.company_name}" if f.company_name else "",
        f"Sector / Industry: {f.sector or '?'} / {f.industry or '?'}",
        f"Market cap: {f.market_cap}" if f.market_cap is not None else "",
        f"Business: {f.description[:800]}" if f.description else "",
        f"Trailing EPS: {f.trailing_eps}" if f.trailing_eps is not None else "",
        f"Forward EPS: {f.forward_eps}" if f.forward_eps is not None else "",
        f"EPS growth: {pct(f.eps_growth_pct)}" if f.eps_growth_pct is not None else "",
        f"Revenue growth (TTM YoY): {pct(f.revenue_growth_pct)}" if f.revenue_growth_pct is not None else "",
        f"Gross margin: {pct(f.gross_margin_pct)}" if f.gross_margin_pct is not None else "",
        f"Net margin: {pct(f.net_margin_pct)}" if f.net_margin_pct is not None else "",
        f"P/E (TTM): {f.pe_ratio}" if f.pe_ratio is not None else "",
        f"52-week range: {f.week52_low} – {f.week52_high}" if f.week52_high is not None else "",
        trend or "",
        f"Analyst consensus: {f.consensus}" if f.consensus else "",
    ]
    if f.rec_strong_buy is not None:
        lines.append(
            "Analyst ratings — "
            f"strong buy {f.rec_strong_buy}, buy {f.rec_buy}, hold {f.rec_hold}, "
            f"sell {f.rec_sell}, strong sell {f.rec_strong_sell}"
        )
    return "\n".join(line for line in lines if line)


def generate_brief(fundamentals: SymbolFundamentalsData) -> dict | None:
    """Generate the structured investment brief (a dict of BRIEF_SECTIONS).

    Returns None when Anthropic is disabled/unkeyed or on any failure, so the
    caller preserves the prior brief instead of wiping it.
    """
    api_key = _resolve_api_key()
    if not api_key:
        return None

    try:
        import anthropic

        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model=BRIEF_MODEL,
            max_tokens=1200,
            system=[{
                "type": "text",
                "text": _BRIEF_SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }],
            messages=[{"role": "user", "content": _build_brief_prompt(fundamentals)}],
            timeout=40.0,
        )
        text = response.content[0].text.strip()
        # Tolerate a stray ```json … ``` fence if the model adds one.
        if text.startswith("```"):
            text = text.split("```", 2)[1].lstrip("json").strip() if "```" in text[3:] else text.strip("`")
        brief = json.loads(text)
        if not isinstance(brief, dict):
            return None
        # Keep only known string sections; drop empties.
        out = {k: str(brief[k]).strip() for k in BRIEF_SECTIONS if brief.get(k)}
        if not out:
            return None
        out["model"] = BRIEF_MODEL
        return out
    except Exception:
        logger.exception("Failed to generate brief for %s", fundamentals.symbol)
        return None
