from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from app.core.logger import logger


@dataclass
class PositionState:
    symbol: str
    side: str
    amount: float
    entry_price: float
    opened_ts: float
    tp_price: float
    sl_price: float
    initial_sl_price: float
    break_even_moved: bool = False
    tp_order_id: str | None = None
    sl_order_id: str | None = None


@dataclass
class ExitDecision:
    should_close: bool
    reason: str = ""
    exit_price: float | None = None
    break_even_moved: bool = False


def configure_exits(
    position: PositionState,
    settings: dict[str, Any],
    client: Any,
    paper_mode: bool,
) -> PositionState:
    exit_order_type = str(settings.get("exit_order_type", "market")).strip().lower()

    if paper_mode:
        logger.info(
            f"Paper exits configured symbol={position.symbol} tp={position.tp_price:.8f} sl={position.sl_price:.8f}"
        )
        return position

    if exit_order_type == "limit":
        try:
            tp_side = "sell" if position.side == "buy" else "buy"
            tp = client.create_order(
                symbol=position.symbol,
                type="limit",
                side=tp_side,
                amount=position.amount,
                price=position.tp_price,
                params={"reduceOnly": True},
            )
            position.tp_order_id = str(tp.get("id") or "") or None
            logger.info(f"TP order placed symbol={position.symbol} order_id={position.tp_order_id}")
        except Exception as exc:
            logger.warning(f"Failed to place TP limit order symbol={position.symbol}: {exc}")

    try:
        sl_side = "sell" if position.side == "buy" else "buy"
        sl = client.create_order(
            symbol=position.symbol,
            type="stop",
            side=sl_side,
            amount=position.amount,
            params={"stopPrice": position.sl_price, "reduceOnly": True},
        )
        position.sl_order_id = str(sl.get("id") or "") or None
        logger.info(f"Native SL order placed symbol={position.symbol} order_id={position.sl_order_id}")
    except Exception as exc:
        logger.warning(f"Native SL unavailable symbol={position.symbol}, using software SL: {exc}")

    return position


def evaluate_exit(
    position: PositionState,
    last_price: float,
    settings: dict[str, Any],
    now_ts: float,
) -> ExitDecision:
    max_duration = _as_int(settings.get("max_trade_duration_sec", 45), 45)

    trigger_pct = _as_float(settings.get("break_even_trigger_pct", 0.10), 0.10)
    offset_pct = _as_float(settings.get("break_even_offset_pct", 0.02), 0.02)
    break_even_enabled = _as_bool(settings.get("break_even_enabled", 1))

    if break_even_enabled and not position.break_even_moved:
        if position.side == "buy":
            trigger_price = position.entry_price * (1 + trigger_pct / 100.0)
            if last_price >= trigger_price:
                position.sl_price = position.entry_price * (1 + offset_pct / 100.0)
                position.break_even_moved = True
                return ExitDecision(False, reason="break_even_moved", break_even_moved=True)
        else:
            trigger_price = position.entry_price * (1 - trigger_pct / 100.0)
            if last_price <= trigger_price:
                position.sl_price = position.entry_price * (1 - offset_pct / 100.0)
                position.break_even_moved = True
                return ExitDecision(False, reason="break_even_moved", break_even_moved=True)

    if position.side == "buy":
        if last_price >= position.tp_price:
            return ExitDecision(True, reason="tp_hit", exit_price=last_price)
        if last_price <= position.sl_price:
            return ExitDecision(True, reason="sl_hit", exit_price=last_price)
    else:
        if last_price <= position.tp_price:
            return ExitDecision(True, reason="tp_hit", exit_price=last_price)
        if last_price >= position.sl_price:
            return ExitDecision(True, reason="sl_hit", exit_price=last_price)

    if now_ts - position.opened_ts >= max_duration:
        return ExitDecision(True, reason="time_stop", exit_price=last_price)

    return ExitDecision(False)


def close_position(
    position: PositionState,
    decision: ExitDecision,
    client: Any,
    settings: dict[str, Any],
    paper_mode: bool,
) -> dict[str, Any]:
    exit_order_type = str(settings.get("exit_order_type", "market")).strip().lower()
    exit_side = "sell" if position.side == "buy" else "buy"

    if paper_mode:
        logger.info(
            f"Paper exit symbol={position.symbol} reason={decision.reason} price={decision.exit_price:.8f}"
        )
        return {"status": "closed", "average": decision.exit_price, "filled": position.amount, "id": "paper-exit"}

    if exit_order_type == "limit" and decision.reason == "tp_hit":
        try:
            order = client.create_order(
                symbol=position.symbol,
                type="limit",
                side=exit_side,
                amount=position.amount,
                price=decision.exit_price,
                params={"reduceOnly": True},
            )
            logger.info(f"Exit limit order placed symbol={position.symbol} reason={decision.reason}")
            return order
        except Exception as exc:
            logger.warning(f"Limit exit failed symbol={position.symbol}, fallback to market: {exc}")

    return client.create_order(
        symbol=position.symbol,
        type="market",
        side=exit_side,
        amount=position.amount,
        params={"reduceOnly": True},
    )


def compute_tp_sl(entry_price: float, side: str, tp_pct: float, sl_pct: float) -> tuple[float, float]:
    if side == "buy":
        return entry_price * (1 + tp_pct / 100.0), entry_price * (1 - sl_pct / 100.0)
    return entry_price * (1 - tp_pct / 100.0), entry_price * (1 + sl_pct / 100.0)


def utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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
