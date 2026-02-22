from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Any

from app.core.logger import logger


@dataclass
class EntryResult:
    success: bool
    status: str
    order_id: str | None = None
    filled: float = 0.0
    avg_price: float | None = None
    reason: str = ""


def place_entry(
    symbol: str,
    side: str,
    amount: float,
    settings: dict[str, Any],
    client: Any,
) -> EntryResult:
    if amount <= 0:
        return EntryResult(False, "rejected", reason="amount<=0")

    order_type = str(settings.get("entry_order_type", "market")).strip().lower()
    min_fill_pct = _as_float(settings.get("min_fill_pct", 80), 80.0)

    logger.info(f"place_entry start symbol={symbol} side={side} amount={amount:.8f} type={order_type}")

    if order_type == "market":
        return _place_market(symbol, side, amount, min_fill_pct, client)

    if order_type == "limit":
        return _place_limit_with_timeout(symbol, side, amount, settings, min_fill_pct, client)

    return EntryResult(False, "rejected", reason=f"unsupported_entry_order_type={order_type}")


def _place_market(symbol: str, side: str, amount: float, min_fill_pct: float, client: Any) -> EntryResult:
    try:
        order = client.create_order(symbol=symbol, type="market", side=side, amount=amount)
    except Exception as exc:
        logger.warning(f"Market entry failed symbol={symbol}: {exc}")
        return EntryResult(False, "error", reason=str(exc))

    return _result_from_order(order, amount, min_fill_pct)


def _place_limit_with_timeout(
    symbol: str,
    side: str,
    amount: float,
    settings: dict[str, Any],
    min_fill_pct: float,
    client: Any,
) -> EntryResult:
    retry_count = max(0, _as_int(settings.get("entry_retry_count", 0), 0))
    timeout_sec = max(1, _as_int(settings.get("entry_timeout_sec", 30), 30))
    allow_market_fallback = _as_bool(settings.get("allow_market_fallback", 0))
    limit_offset_bps = _as_float(settings.get("limit_offset_bps", 2), 2.0)

    attempts = retry_count + 1
    for attempt in range(1, attempts + 1):
        try:
            ticker = client.fetch_ticker(symbol)
            last_price = float(ticker.get("last") or ticker.get("close") or 0)
            if last_price <= 0:
                raise ValueError("ticker price unavailable")

            if side.lower() == "buy":
                limit_price = last_price * (1.0 - limit_offset_bps / 10_000.0)
            else:
                limit_price = last_price * (1.0 + limit_offset_bps / 10_000.0)

            logger.info(
                f"Limit entry attempt={attempt}/{attempts} symbol={symbol} side={side} "
                f"amount={amount:.8f} price={limit_price:.8f}"
            )
            order = client.create_order(
                symbol=symbol,
                type="limit",
                side=side,
                amount=amount,
                price=limit_price,
            )
        except Exception as exc:
            logger.warning(f"Limit order submit failed symbol={symbol}: {exc}")
            if attempt >= attempts:
                if allow_market_fallback:
                    logger.info(f"Fallback to market for {symbol}")
                    return _place_market(symbol, side, amount, min_fill_pct, client)
                return EntryResult(False, "error", reason=str(exc))
            continue

        order_id = str(order.get("id") or "")
        start = time.time()

        while time.time() - start < timeout_sec:
            try:
                refreshed = client.fetch_order(order_id, symbol=symbol)
            except Exception as exc:
                logger.warning(f"Order poll failed order_id={order_id}: {exc}")
                time.sleep(1.0)
                continue

            status = str(refreshed.get("status", "")).lower()
            if status in {"closed", "filled"}:
                return _result_from_order(refreshed, amount, min_fill_pct)

            time.sleep(1.0)

        logger.info(f"Entry timeout order_id={order_id}, canceling")
        try:
            client.cancel_order(order_id, symbol=symbol)
        except Exception as exc:
            logger.warning(f"Cancel failed order_id={order_id}: {exc}")

        try:
            latest = client.fetch_order(order_id, symbol=symbol)
            res = _result_from_order(latest, amount, min_fill_pct)
            if res.success:
                return res
        except Exception:
            pass

        if attempt >= attempts:
            if allow_market_fallback:
                logger.info(f"Limit retries exhausted, fallback to market for {symbol}")
                return _place_market(symbol, side, amount, min_fill_pct, client)
            return EntryResult(False, "timeout", order_id=order_id, reason="entry timeout")

    return EntryResult(False, "timeout", reason="entry retries exhausted")


def _result_from_order(order: dict[str, Any], requested_amount: float, min_fill_pct: float) -> EntryResult:
    order_id = str(order.get("id") or "") or None
    status = str(order.get("status") or "unknown")
    filled = _as_float(order.get("filled", 0.0), 0.0)
    avg_price_raw = order.get("average")
    avg_price = _as_float(avg_price_raw, 0.0) if avg_price_raw is not None else None

    fill_pct = (filled / requested_amount * 100.0) if requested_amount > 0 else 0.0
    success = fill_pct >= min_fill_pct

    if success:
        logger.info(
            f"Entry accepted order_id={order_id} status={status} filled={filled:.8f} fill_pct={fill_pct:.2f}"
        )
        return EntryResult(True, status, order_id=order_id, filled=filled, avg_price=avg_price)

    logger.warning(
        f"Entry rejected by min_fill_pct order_id={order_id} status={status} "
        f"filled={filled:.8f} fill_pct={fill_pct:.2f} min_required={min_fill_pct:.2f}"
    )
    return EntryResult(
        False,
        status,
        order_id=order_id,
        filled=filled,
        avg_price=avg_price,
        reason=f"fill_pct {fill_pct:.2f} < min_fill_pct {min_fill_pct:.2f}",
    )


def _as_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _as_int(value: Any, default: int) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return int(default)


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return int(value) != 0
    return str(value).strip().lower() in {"1", "true", "yes", "on"}
