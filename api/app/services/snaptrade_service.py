"""SnapTrade integration service.

Wraps the SnapTrade REST SDK to:
  1. register a per-user SnapTrade identity,
  2. mint Connection Portal URLs so a user links their broker (Robinhood, etc.),
  3. pull executed fills and upsert them into `trades_monthly`, and
  4. reconcile each fill back to a documented alert pattern (via TradeAnnotation)
     so the EOD report can show "setup we flagged" vs. "trade you took".

Design constraints matched to this codebase:
  * The SDK (`snaptrade-python-sdk`) is an OPTIONAL dependency. Everything imports
    lazily so the API boots without it. Callers get a clear RuntimeError only when
    they actually invoke a SnapTrade-backed path with credentials missing.
  * All SnapTrade calls are blocking HTTP — async endpoints wrap them in a thread.
  * Persistence uses a SYNC SQLAlchemy Session (the same `sync_session_factory`
    the APScheduler jobs use), so the scheduled daily sync and the on-demand
    endpoint share one code path.
  * Synced fills reuse the existing `trades_monthly` table; provenance is stamped
    in the `account` column (e.g. "ROBINHOOD"). Dedup makes re-syncs idempotent.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Any, Iterable, Optional

logger = logging.getLogger("snaptrade")

# SnapTrade activity `type` values that represent an executed trade fill.
_TRADE_TYPES = {"BUY", "SELL"}


class SnapTradeNotConfigured(RuntimeError):
    """Raised when a SnapTrade path is hit without credentials/SDK available."""


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

def is_configured(settings) -> bool:
    """True when SnapTrade credentials are present. Cheap — no SDK import."""
    return bool(
        getattr(settings, "SNAPTRADE_CLIENT_ID", "")
        and getattr(settings, "SNAPTRADE_CONSUMER_KEY", "")
    )


def get_client(settings):
    """Construct a SnapTrade SDK client. Lazy import keeps the dep optional."""
    if not is_configured(settings):
        raise SnapTradeNotConfigured(
            "SnapTrade is not configured — set SNAPTRADE_CLIENT_ID and "
            "SNAPTRADE_CONSUMER_KEY."
        )
    try:
        from snaptrade_client import SnapTrade  # type: ignore
    except ImportError as exc:  # pragma: no cover - env-dependent
        raise SnapTradeNotConfigured(
            "snaptrade-python-sdk is not installed — add it to requirements.txt."
        ) from exc

    return SnapTrade(
        client_id=settings.SNAPTRADE_CLIENT_ID,
        consumer_key=settings.SNAPTRADE_CONSUMER_KEY,
    )


def snaptrade_user_id_for(user_id: int) -> str:
    """Namespaced SnapTrade userId so it never collides with other apps."""
    return f"btd_{user_id}"


def _body(resp: Any) -> Any:
    """SDK responses expose parsed data on `.body`; fall back to the object."""
    return getattr(resp, "body", resp)


def _pluck(obj: Any, *keys: str, default: Any = None) -> Any:
    """Read a key from a dict OR attribute from an object, trying several names.

    SnapTrade's SDK returns camelCase in some versions and snake_case in others,
    and sometimes typed objects rather than dicts — so we probe defensively.
    """
    for key in keys:
        if isinstance(obj, dict):
            if key in obj and obj[key] is not None:
                return obj[key]
        else:
            val = getattr(obj, key, None)
            if val is not None:
                return val
    return default


# ---------------------------------------------------------------------------
# SnapTrade API wrappers (blocking) — thin, so endpoints stay readable
# ---------------------------------------------------------------------------

def register_user(client, snaptrade_user_id: str) -> str:
    """Register a SnapTrade user; return the userSecret.

    Idempotent-ish: if the user already exists SnapTrade returns a 4xx; the
    caller is expected to already hold the secret in that case and skip this.
    """
    resp = client.authentication.register_snap_trade_user(
        body={"userId": snaptrade_user_id}
    )
    body = _body(resp)
    secret = _pluck(body, "userSecret", "user_secret")
    if not secret:
        raise RuntimeError("SnapTrade registration returned no userSecret")
    return secret


def connection_portal_url(
    client,
    snaptrade_user_id: str,
    user_secret: str,
    *,
    broker: Optional[str] = None,
    redirect_uri: Optional[str] = None,
) -> str:
    """Mint a one-time Connection Portal URL for linking a brokerage."""
    body: dict[str, Any] = {}
    if broker:
        body["broker"] = broker
    if redirect_uri:
        body["customRedirect"] = redirect_uri
    resp = client.authentication.login_snap_trade_user(
        query_params={"userId": snaptrade_user_id, "userSecret": user_secret},
        body=body,
    )
    parsed = _body(resp)
    uri = _pluck(parsed, "redirectURI", "redirect_uri")
    if not uri:
        raise RuntimeError("SnapTrade login returned no redirectURI")
    return uri


def list_accounts(client, snaptrade_user_id: str, user_secret: str) -> list[dict]:
    """List the user's connected brokerage accounts."""
    resp = client.account_information.list_user_accounts(
        query_params={"userId": snaptrade_user_id, "userSecret": user_secret}
    )
    body = _body(resp)
    return list(body) if body else []


def fetch_activities(
    client,
    snaptrade_user_id: str,
    user_secret: str,
    start_date: date,
    end_date: date,
) -> list[dict]:
    """Fetch account activities (fills, dividends, transfers) in a date range."""
    resp = client.transactions_and_reporting.get_activities(
        query_params={
            "userId": snaptrade_user_id,
            "userSecret": user_secret,
            "startDate": start_date.isoformat(),
            "endDate": end_date.isoformat(),
        }
    )
    body = _body(resp)
    return list(body) if body else []


def remove_all_connections(client, snaptrade_user_id: str, user_secret: str) -> int:
    """Remove every brokerage authorization for the user. Returns count removed."""
    resp = client.connections.list_brokerage_authorizations(
        query_params={"userId": snaptrade_user_id, "userSecret": user_secret}
    )
    auths = _body(resp) or []
    removed = 0
    for auth in auths:
        auth_id = _pluck(auth, "id")
        if not auth_id:
            continue
        client.connections.remove_brokerage_authorization(
            path_params={"authorizationId": auth_id},
            query_params={"userId": snaptrade_user_id, "userSecret": user_secret},
        )
        removed += 1
    return removed


# ---------------------------------------------------------------------------
# Pure transforms (unit-tested without any network or DB)
# ---------------------------------------------------------------------------

def _extract_symbol(activity: dict) -> Optional[str]:
    """Pull the ticker from an activity's nested symbol structure.

    SnapTrade nests equity symbols as `symbol.symbol.symbol` and options under
    `option_symbol`. We handle equities and fall back through the shapes.
    """
    sym = _pluck(activity, "symbol")
    if isinstance(sym, dict):
        inner = _pluck(sym, "symbol", "raw_symbol")
        if isinstance(inner, dict):
            return _pluck(inner, "symbol", "raw_symbol")
        if isinstance(inner, str):
            return inner
    elif isinstance(sym, str):
        return sym
    # Options fallback — use the underlying if present.
    opt = _pluck(activity, "option_symbol")
    if isinstance(opt, dict):
        return _pluck(opt, "underlying_symbol", "ticker")
    return None


def _normalize_date(value: Any) -> Optional[str]:
    """Coerce a SnapTrade date/datetime string to YYYY-MM-DD."""
    if not value:
        return None
    if isinstance(value, (datetime, date)):
        return value.isoformat()[:10]
    text = str(value)
    return text[:10] if len(text) >= 10 else None


def activity_to_monthly_row(activity: dict, *, account_label: str) -> Optional[dict]:
    """Normalize a SnapTrade activity into a `trades_monthly`-shaped dict.

    Returns None for non-trade activities (dividends, transfers, fees) or rows
    missing the essentials (symbol / date / quantity).
    """
    act_type = str(_pluck(activity, "type", default="")).upper()
    if act_type not in _TRADE_TYPES:
        return None

    symbol = _extract_symbol(activity)
    trade_date = _normalize_date(
        _pluck(activity, "trade_date", "tradeDate", "settlement_date")
    )
    units = _pluck(activity, "units", "quantity")
    if not symbol or not trade_date or units is None:
        return None

    price = _pluck(activity, "price", default=0.0) or 0.0
    amount = _pluck(activity, "amount", default=None)
    quantity = abs(float(units))
    if amount is None:
        # Reconstruct signed cash flow: BUY is money out (negative).
        gross = quantity * float(price)
        amount = -gross if act_type == "BUY" else gross

    is_option = 1 if _pluck(activity, "option_symbol") else 0

    return {
        "symbol": str(symbol).upper(),
        "description": str(_pluck(activity, "description", default="") or ""),
        "transaction_type": act_type,
        "trade_date": trade_date,
        "quantity": quantity,
        "price": float(price),
        "amount": float(amount),
        "is_option": is_option,
        "account": account_label,
    }


def match_fill_to_pattern(
    row: dict, candidate_alerts: Iterable[dict]
) -> Optional[str]:
    """Reconcile a fill to a documented pattern.

    A candidate alert is a dict with `symbol`, `session_date`, `alert_type` and
    optional `direction`. We match on same symbol + same session date, and,
    when the fill direction is known, prefer a same-direction alert (a BUY fill
    pairs with a long alert). Returns the winning `alert_type`, or None.
    """
    symbol = row.get("symbol")
    trade_date = row.get("trade_date")
    if not symbol or not trade_date:
        return None

    txn = str(row.get("transaction_type", "")).upper()
    want_dir = "LONG" if txn == "BUY" else "SHORT" if txn == "SELL" else None

    same_day = [
        a
        for a in candidate_alerts
        if str(a.get("symbol", "")).upper() == symbol
        and a.get("session_date") == trade_date
        and a.get("alert_type")
    ]
    if not same_day:
        return None

    if want_dir:
        directional = [
            a
            for a in same_day
            if str(a.get("direction", "")).upper() in (want_dir, "")
        ]
        if directional:
            return directional[0]["alert_type"]
    return same_day[0]["alert_type"]


# ---------------------------------------------------------------------------
# Persistence (sync Session) — shared by the scheduler and the /sync endpoint
# ---------------------------------------------------------------------------

def sync_user_fills(
    sync_session_factory,
    settings,
    user_id: int,
    *,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    client=None,
) -> dict:
    """Pull fills for one user and upsert them into `trades_monthly`.

    Idempotent: a fill already present (same user/symbol/date/type/qty/price) is
    skipped. Newly imported fills are reconciled against the user's own alerts
    for that day and tagged via `TradeAnnotation(source="snaptrade")`.

    Returns a summary dict (also the shape the /sync endpoint serializes).
    """
    from app.models.snaptrade import (
        STATUS_DISABLED,
        SnapTradeConnection,
    )
    from app.models.trade import TradeAnnotation, TradeMonthly
    from app.models.alert import Alert

    end_date = end_date or date.today()
    lookback = getattr(settings, "SNAPTRADE_SYNC_LOOKBACK_DAYS", 7)
    start_date = start_date or (end_date - timedelta(days=lookback))

    summary = {
        "fills_fetched": 0,
        "fills_imported": 0,
        "fills_skipped": 0,
        "patterns_matched": 0,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
    }

    client = client or get_client(settings)

    with sync_session_factory() as session:
        conn = (
            session.query(SnapTradeConnection)
            .filter(SnapTradeConnection.user_id == user_id)
            .one_or_none()
        )
        if conn is None or conn.status == STATUS_DISABLED:
            logger.info("SnapTrade sync: user %s has no active connection", user_id)
            return summary

        account_label = (conn.broker_slug or "SNAPTRADE").upper()

        activities = fetch_activities(
            client, conn.snaptrade_user_id, conn.user_secret, start_date, end_date
        )
        rows = [
            r
            for r in (
                activity_to_monthly_row(a, account_label=account_label)
                for a in activities
            )
            if r is not None
        ]
        summary["fills_fetched"] = len(rows)
        if not rows:
            conn.last_synced_at = datetime.utcnow()
            session.commit()
            return summary

        # Existing fills in range for this user → dedup set.
        existing = session.query(
            TradeMonthly.symbol,
            TradeMonthly.trade_date,
            TradeMonthly.transaction_type,
            TradeMonthly.quantity,
            TradeMonthly.price,
        ).filter(
            TradeMonthly.user_id == user_id,
            TradeMonthly.trade_date >= start_date.isoformat(),
            TradeMonthly.trade_date <= end_date.isoformat(),
        ).all()
        seen = {
            (e.symbol, e.trade_date, e.transaction_type, e.quantity, e.price)
            for e in existing
        }

        # Candidate alerts for reconciliation, one query for the whole range.
        alert_rows = session.query(
            Alert.symbol, Alert.session_date, Alert.alert_type, Alert.direction
        ).filter(
            Alert.user_id == user_id,
            Alert.session_date >= start_date.isoformat(),
            Alert.session_date <= end_date.isoformat(),
        ).all()
        candidate_alerts = [
            {
                "symbol": a.symbol,
                "session_date": a.session_date,
                "alert_type": a.alert_type,
                "direction": a.direction,
            }
            for a in alert_rows
        ]

        for row in rows:
            key = (
                row["symbol"],
                row["trade_date"],
                row["transaction_type"],
                row["quantity"],
                row["price"],
            )
            if key in seen:
                summary["fills_skipped"] += 1
                continue
            seen.add(key)

            session.add(
                TradeMonthly(
                    user_id=user_id,
                    account=row["account"],
                    description=row["description"],
                    symbol=row["symbol"],
                    transaction_type=row["transaction_type"],
                    trade_date=row["trade_date"],
                    quantity=row["quantity"],
                    price=row["price"],
                    amount=row["amount"],
                    is_option=row["is_option"],
                )
            )
            summary["fills_imported"] += 1

            pattern = match_fill_to_pattern(row, candidate_alerts)
            if pattern:
                # Upsert-ish: skip if an annotation for this fill already exists.
                dupe = (
                    session.query(TradeAnnotation.id)
                    .filter(
                        TradeAnnotation.user_id == user_id,
                        TradeAnnotation.source == "snaptrade",
                        TradeAnnotation.symbol == row["symbol"],
                        TradeAnnotation.trade_date == row["trade_date"],
                        TradeAnnotation.quantity == row["quantity"],
                    )
                    .first()
                )
                if not dupe:
                    session.add(
                        TradeAnnotation(
                            user_id=user_id,
                            source="snaptrade",
                            symbol=row["symbol"],
                            trade_date=row["trade_date"],
                            quantity=row["quantity"],
                            strategy_tag=pattern,
                            notes="Auto-matched from SnapTrade fill",
                        )
                    )
                    summary["patterns_matched"] += 1

        conn.last_synced_at = datetime.utcnow()
        conn.last_sync_count = summary["fills_imported"]
        session.commit()

    logger.info(
        "SnapTrade sync user=%s: fetched=%d imported=%d skipped=%d matched=%d",
        user_id,
        summary["fills_fetched"],
        summary["fills_imported"],
        summary["fills_skipped"],
        summary["patterns_matched"],
    )
    return summary


def run_daily_sync(sync_session_factory, settings) -> dict:
    """Scheduler entrypoint — sync every connected user. Never raises."""
    from app.models.snaptrade import STATUS_DISABLED, SnapTradeConnection

    totals = {"users": 0, "imported": 0, "matched": 0}
    if not is_configured(settings):
        logger.info("SnapTrade daily sync skipped — not configured")
        return totals

    try:
        client = get_client(settings)
        with sync_session_factory() as session:
            user_ids = [
                c.user_id
                for c in session.query(SnapTradeConnection.user_id)
                .filter(SnapTradeConnection.status != STATUS_DISABLED)
                .all()
            ]
    except Exception:
        logger.exception("SnapTrade daily sync: failed to enumerate connections")
        return totals

    for uid in user_ids:
        try:
            res = sync_user_fills(sync_session_factory, settings, uid, client=client)
            totals["users"] += 1
            totals["imported"] += res["fills_imported"]
            totals["matched"] += res["patterns_matched"]
        except Exception:
            logger.exception("SnapTrade daily sync failed for user %s", uid)

    logger.info(
        "SnapTrade daily sync complete: users=%d imported=%d matched=%d",
        totals["users"],
        totals["imported"],
        totals["matched"],
    )
    return totals
