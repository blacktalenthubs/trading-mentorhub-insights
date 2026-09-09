"""Robinhood fill import — thin client + PURE payload normalizers.

Robinhood publishes no official API. This module drives `robin_stocks`, an
unofficial reverse-engineered client, and is deliberately shaped so that:

  - it is opt-in behind ROBINHOOD_IMPORT_ENABLED (default OFF);
  - nothing else in the app imports robin_stocks directly — if the dependency
    is missing or Robinhood changes its private API, the blast radius is here;
  - the network client and the payload->TradeMonthly mapping are SEPARATE, so
    the mapping is unit-testable against recorded fixtures with no network.

This is an ETL layer. It contains no alert/signal business logic: it never
fires an alert, never reads a rule, and never writes to the alert tables.

Operational notes
-----------------
Non-interactive login needs authenticator-app 2FA (not SMS): enable it in
Robinhood, save the TOTP seed, and set ROBINHOOD_TOTP_SECRET. robin_stocks
persists a session pickle so most runs skip the MFA round-trip entirely.

Required env (all read via alert_config._get_secret, so .env or Railway vars):
    ROBINHOOD_IMPORT_ENABLED   "true" to arm the daily job (default "false")
    ROBINHOOD_USERNAME         account email
    ROBINHOOD_PASSWORD         account password
    ROBINHOOD_TOTP_SECRET      authenticator seed, for unattended re-login
    ROBINHOOD_USER_ID          app users.id the imported fills belong to
    ROBINHOOD_ACCOUNT_LABEL    label stored on each row (default "Robinhood")
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any, Iterable

from alert_config import _get_secret
from config import categorize_symbol
from models import TradeMonthly

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

ROBINHOOD_IMPORT_ENABLED = _get_secret("ROBINHOOD_IMPORT_ENABLED", "false").lower() == "true"
ROBINHOOD_USERNAME = _get_secret("ROBINHOOD_USERNAME")
ROBINHOOD_PASSWORD = _get_secret("ROBINHOOD_PASSWORD")
ROBINHOOD_TOTP_SECRET = _get_secret("ROBINHOOD_TOTP_SECRET")
ROBINHOOD_ACCOUNT_LABEL = _get_secret("ROBINHOOD_ACCOUNT_LABEL", "Robinhood")

try:
    ROBINHOOD_USER_ID = int(_get_secret("ROBINHOOD_USER_ID", "0") or 0)
except ValueError:
    ROBINHOOD_USER_ID = 0


class RobinhoodError(RuntimeError):
    """Raised when login or a fetch fails — always caught by the daily job."""


# ---------------------------------------------------------------------------
# Coercion helpers
#
# Robinhood returns every number as a STRING ("10.00000000"), and any field can
# be null on a partially-populated order. Every read goes through these.
# ---------------------------------------------------------------------------

def _f(value: Any, default: float = 0.0) -> float:
    """Coerce a Robinhood string/None numeric field to float."""
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _s(value: Any, default: str = "") -> str:
    """Coerce to a stripped string, mapping None to the default."""
    if value is None:
        return default
    return str(value).strip()


def _parse_ts(value: Any) -> date | None:
    """Parse a Robinhood ISO-8601 timestamp to a date.

    Robinhood stamps UTC with a trailing 'Z' and microseconds
    ("2026-09-08T20:14:33.412345Z"), which datetime.fromisoformat rejects on
    Python < 3.11 — so normalise the suffix before parsing.
    """
    raw = _s(value)
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).date()
    except ValueError:
        # Fall back to the leading YYYY-MM-DD, which is always present.
        try:
            return datetime.strptime(raw[:10], "%Y-%m-%d").date()
        except ValueError:
            return None


def _fill_date(order: dict, executions: list[dict] | None = None) -> date | None:
    """The date the order actually filled.

    Prefers the LAST execution's timestamp (an order placed pre-market and
    filled at the open belongs to the fill date, not the placement date) and
    falls back to the order's own timestamps.
    """
    for ex in reversed(executions or []):
        d = _parse_ts(ex.get("timestamp"))
        if d:
            return d
    return _parse_ts(order.get("last_transaction_at")) or _parse_ts(order.get("created_at"))


def _weighted_price(executions: list[dict], fallback: float) -> float:
    """Volume-weighted average price across an order's executions.

    Robinhood's order-level `average_price` is usually right, but it is null on
    some option orders and stale on others, so compute it from the executions
    when they are present and only then fall back.
    """
    total_qty = 0.0
    total_cost = 0.0
    for ex in executions or []:
        qty = _f(ex.get("quantity"))
        price = _f(ex.get("price"))
        if qty > 0 and price > 0:
            total_qty += qty
            total_cost += qty * price
    if total_qty > 0:
        return total_cost / total_qty
    return fallback


# ---------------------------------------------------------------------------
# Pure normalizers: Robinhood order payload -> TradeMonthly rows
#
# TradeMonthly is the shared "one executed buy/sell" record the PDF statement
# parser already emits, so normalising into it means Robinhood fills flow
# through analytics.trade_matcher.match_trades_fifo and every downstream
# report unchanged.
# ---------------------------------------------------------------------------

# FIFO pairs on (account, symbol), so an OPTION's symbol must identify the
# CONTRACT — otherwise a SPY 700 call buy would match against a SPY 690 put
# sell. Stocks use the plain ticker.
def option_contract_symbol(underlying: str, expiration: str, opt_type: str, strike: float) -> str:
    """Stable per-contract key, e.g. "SPY 2026-01-29 C 696.0"."""
    letter = "C" if _s(opt_type).lower().startswith("c") else "P"
    return f"{_s(underlying).upper()} {_s(expiration)} {letter} {strike:g}"


def normalize_stock_order(order: dict, symbol: str) -> TradeMonthly | None:
    """Map one filled Robinhood stock order to a TradeMonthly row.

    Returns None for anything not actually filled (queued, cancelled, rejected)
    or missing the quantity/price needed to compute P&L. `symbol` is passed in
    because Robinhood identifies the security by an instrument URL, not a
    ticker — the caller resolves and caches that lookup.
    """
    if _s(order.get("state")).lower() != "filled":
        return None

    executions = order.get("executions") or []
    # cumulative_quantity is what actually filled; `quantity` is what was asked
    # for, and the two differ on a partial fill.
    quantity = _f(order.get("cumulative_quantity")) or _f(order.get("quantity"))
    price = _weighted_price(executions, _f(order.get("average_price")))
    if quantity <= 0 or price <= 0:
        return None

    trade_date = _fill_date(order, executions)
    if trade_date is None:
        return None

    side = _s(order.get("side")).lower()
    if side not in ("buy", "sell"):
        return None
    txn_type = "Buy" if side == "buy" else "Sell"

    symbol = _s(symbol).upper()
    amount = quantity * price
    return TradeMonthly(
        account=ROBINHOOD_ACCOUNT_LABEL,
        description=f"{txn_type} {quantity:g} {symbol} @ {price:.4f}",
        symbol=symbol,
        cusip="",
        acct_type="",
        transaction_type=txn_type,
        trade_date=trade_date,
        # A buy is a debit (negative), a sell a credit — matches the statement
        # parser's sign convention so blended reports stay consistent.
        quantity=quantity,
        price=price,
        amount=-amount if txn_type == "Buy" else amount,
        is_option=False,
        option_detail="",
        is_recurring=False,
        asset_type="stock",
        category=categorize_symbol(symbol),
        underlying_symbol=symbol,
    )


def normalize_option_order(order: dict) -> list[TradeMonthly]:
    """Map one filled Robinhood option order to a TradeMonthly row PER LEG.

    A multi-leg order (spread, iron condor) fills several contracts under one
    order id, and each leg is its own position to pair — so each becomes its
    own row, keyed by contract.
    """
    if _s(order.get("state")).lower() != "filled":
        return []

    underlying = _s(order.get("chain_symbol")).upper()
    if not underlying:
        return []

    rows: list[TradeMonthly] = []
    for leg in order.get("legs") or []:
        executions = leg.get("executions") or []
        quantity = sum(_f(ex.get("quantity")) for ex in executions)
        if quantity <= 0:
            continue
        price = _weighted_price(executions, 0.0)
        if price <= 0:
            continue

        trade_date = _fill_date(order, executions)
        if trade_date is None:
            continue

        side = _s(leg.get("side")).lower()
        # position_effect is what makes an option row pairable: the same "buy"
        # side opens a long call and closes a short one.
        effect = _s(leg.get("position_effect")).lower()
        if side == "buy":
            txn_type = "BTO" if effect != "close" else "Buy"
        elif side == "sell":
            txn_type = "STC" if effect == "close" else "Sell"
        else:
            continue

        strike = _f(leg.get("strike_price"))
        expiration = _s(leg.get("expiration_date"))
        opt_type = _s(leg.get("option_type"))
        contract = option_contract_symbol(underlying, expiration, opt_type, strike)

        # Options are quoted per share but trade in 100-share contracts, so the
        # cash amount is premium x quantity x 100. Price stays per-share so the
        # FIFO matcher's per-unit P&L math stays in the same units.
        amount = quantity * price * 100.0
        rows.append(TradeMonthly(
            account=ROBINHOOD_ACCOUNT_LABEL,
            description=f"{txn_type} {quantity:g} {contract} @ {price:.4f}",
            symbol=contract,
            cusip="",
            acct_type="",
            transaction_type=txn_type,
            trade_date=trade_date,
            quantity=quantity,
            price=price,
            amount=-amount if txn_type in ("BTO", "Buy") else amount,
            is_option=True,
            option_detail=contract,
            is_recurring=False,
            asset_type="option",
            category=categorize_symbol(underlying),
            underlying_symbol=underlying,
        ))
    return rows


def stock_external_id(order: dict) -> str:
    """Idempotency key for a stock order — Robinhood's own order UUID."""
    return f"rh:stock:{_s(order.get('id'))}"


def option_external_id(order: dict, leg_index: int) -> str:
    """Idempotency key for one leg of an option order."""
    return f"rh:option:{_s(order.get('id'))}:{leg_index}"


def normalize_orders(
    stock_orders: Iterable[dict],
    option_orders: Iterable[dict],
    symbol_lookup,
) -> list[tuple[str, TradeMonthly]]:
    """Normalize both order families into (external_id, TradeMonthly) pairs.

    `symbol_lookup` maps an instrument URL to a ticker; it is injected so tests
    can pass a dict and the live job can pass a cached Robinhood call. A lookup
    that fails returns "" and the order is skipped rather than stored under a
    wrong ticker.
    """
    out: list[tuple[str, TradeMonthly]] = []

    for order in stock_orders or []:
        try:
            symbol = _s(symbol_lookup(_s(order.get("instrument"))))
            if not symbol:
                logger.warning("Robinhood: no symbol for order %s — skipped", order.get("id"))
                continue
            row = normalize_stock_order(order, symbol)
            if row:
                out.append((stock_external_id(order), row))
        except Exception:
            logger.exception("Robinhood: failed to normalize stock order %s", order.get("id"))

    for order in option_orders or []:
        try:
            for leg_index, row in enumerate(normalize_option_order(order)):
                out.append((option_external_id(order, leg_index), row))
        except Exception:
            logger.exception("Robinhood: failed to normalize option order %s", order.get("id"))

    return out


# ---------------------------------------------------------------------------
# Network client — the only place robin_stocks is touched
# ---------------------------------------------------------------------------

class RobinhoodClient:
    """Thin authenticated wrapper over robin_stocks.

    robin_stocks is imported lazily so the package stays optional: with the
    feature disabled the app runs with the dependency absent.
    """

    def __init__(self) -> None:
        self._rh = None
        self._symbol_cache: dict[str, str] = {}

    def login(self) -> None:
        """Authenticate, reusing the stored session when it is still valid.

        robin_stocks persists a session pickle, so the TOTP is only consumed
        when that session has expired.
        """
        if not ROBINHOOD_USERNAME or not ROBINHOOD_PASSWORD:
            raise RobinhoodError("ROBINHOOD_USERNAME / ROBINHOOD_PASSWORD not set")

        try:
            import robin_stocks.robinhood as rh
        except ImportError as exc:
            raise RobinhoodError(
                "robin_stocks is not installed — add it to requirements.txt"
            ) from exc

        mfa_code = None
        if ROBINHOOD_TOTP_SECRET:
            try:
                import pyotp
                mfa_code = pyotp.TOTP(ROBINHOOD_TOTP_SECRET).now()
            except ImportError as exc:
                raise RobinhoodError("pyotp is not installed — needed for TOTP login") from exc

        try:
            rh.login(
                username=ROBINHOOD_USERNAME,
                password=ROBINHOOD_PASSWORD,
                mfa_code=mfa_code,
                store_session=True,
            )
        except Exception as exc:
            # Never let a Robinhood credential reach a log line.
            raise RobinhoodError(f"Robinhood login failed: {type(exc).__name__}") from exc

        self._rh = rh

    def symbol_for_instrument(self, instrument_url: str) -> str:
        """Resolve an instrument URL to a ticker, cached per run.

        Robinhood returns one order per row with only an instrument URL, and a
        busy day repeats the same handful of instruments — without the cache
        this is one HTTP round-trip per order.
        """
        if not instrument_url:
            return ""
        if instrument_url in self._symbol_cache:
            return self._symbol_cache[instrument_url]
        if self._rh is None:
            raise RobinhoodError("symbol_for_instrument called before login()")
        try:
            symbol = _s(self._rh.get_symbol_by_url(instrument_url)).upper()
        except Exception:
            logger.exception("Robinhood: instrument lookup failed for %s", instrument_url)
            symbol = ""
        self._symbol_cache[instrument_url] = symbol
        return symbol

    def fetch_orders(self) -> tuple[list[dict], list[dict]]:
        """Fetch all stock and option orders. Either family may be empty.

        Robinhood's order endpoints have no server-side date filter, so the
        caller does the date narrowing after normalization.
        """
        if self._rh is None:
            raise RobinhoodError("fetch_orders called before login()")
        try:
            stock_orders = self._rh.get_all_stock_orders() or []
        except Exception as exc:
            raise RobinhoodError(f"stock order fetch failed: {type(exc).__name__}") from exc
        try:
            option_orders = self._rh.get_all_option_orders() or []
        except Exception:
            # An options-free account still has a usable stock import.
            logger.exception("Robinhood: option order fetch failed — continuing with stocks")
            option_orders = []
        return stock_orders, option_orders
