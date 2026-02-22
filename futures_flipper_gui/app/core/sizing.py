from __future__ import annotations

import math
from typing import Any


def compute_margin_to_use(balance_free: float, settings: dict[str, Any]) -> float:
    mode = str(settings.get("sizing_mode", "percent")).strip().lower()
    reserve = _as_float(settings.get("sizing_reserve_usdt", 0.0), 0.0)
    max_margin = _as_float(settings.get("max_margin_per_trade_usdt", balance_free), balance_free)
    usable = max(0.0, float(balance_free) - reserve)

    if mode == "full":
        margin = usable
    elif mode == "fixed":
        margin = _as_float(settings.get("sizing_fixed_usdt", 20.0), 20.0)
    else:
        percent = _as_float(settings.get("sizing_percent", 10.0), 10.0)
        margin = usable * (percent / 100.0)

    margin = max(0.0, min(margin, usable, max_margin))
    return float(margin)


def compute_order_amount(
    price: float,
    margin_usdt: float,
    leverage: int,
    market_info: dict[str, Any] | None = None,
    symbol: str | None = None,
    client: Any | None = None,
) -> tuple[float | None, str | None, dict[str, float | None]]:
    if price <= 0:
        raise ValueError("price must be > 0")
    if leverage <= 0:
        raise ValueError("leverage must be > 0")

    market = _resolve_market(market_info=market_info, symbol=symbol, client=client)
    limits = market.get("limits") or {}
    precision = market.get("precision") or {}

    min_qty, step, precision_amount = _resolve_min_qty(price=price, market=market)
    min_cost = _nested_float(limits, "cost", "min")

    qty_raw = 0.0
    qty_rounded = 0.0

    if margin_usdt <= 0:
        details = {
            "qty_raw": qty_raw,
            "qty_rounded": qty_rounded,
            "min_qty": min_qty,
            "min_cost": min_cost,
            "step": step,
            "precision_amount": precision_amount,
            "cost": 0.0,
        }
        return None, "Non-positive margin", details

    notional = float(margin_usdt) * float(leverage)
    qty_raw = notional / float(price)
    qty_rounded, _ = apply_precision(qty_raw, precision=precision_amount, step=step)

    cost = qty_rounded * float(price)
    details = {
        "qty_raw": qty_raw,
        "qty_rounded": qty_rounded,
        "min_qty": min_qty,
        "min_cost": min_cost,
        "step": step,
        "precision_amount": precision_amount,
        "cost": cost,
    }

    if qty_rounded <= 0:
        return None, "qty_after_round <= 0", details
    if min_qty is not None and qty_rounded < min_qty:
        return None, f"qty_rounded < minQty ({qty_rounded} < {min_qty})", details
    if min_cost is not None and cost < min_cost:
        return None, f"notional < minCost ({cost} < {min_cost})", details

    return qty_rounded, None, details


def _resolve_market(market_info: dict[str, Any] | None, symbol: str | None, client: Any | None) -> dict[str, Any]:
    if market_info:
        return market_info

    if client is not None and symbol:
        exchange = getattr(client, "exchange", None)
        if exchange is not None:
            try:
                market = exchange.market(symbol)
                if market:
                    return market
            except Exception:
                pass
            try:
                markets = getattr(exchange, "markets", {}) or {}
                if symbol in markets:
                    return markets[symbol]
            except Exception:
                pass

    return {}


def _resolve_min_qty(price: float, market: dict[str, Any]) -> tuple[float | None, float | None, int | None]:
    limits = market.get("limits") or {}
    precision = market.get("precision") or {}
    info = market.get("info") or {}

    precision_amount = _as_int(precision.get("amount"))
    step = _nested_float(limits, "amount", "step")

    min_qty = _nested_float(limits, "amount", "min")
    if min_qty is None:
        min_qty = _first_float(info, ["minQty", "minVol", "min_volume", "min_order_qty"])

    contract_size = _as_float_or_none(market.get("contractSize"))
    if contract_size and min_qty and min_qty >= 1:
        min_qty = min_qty * contract_size

    # MEXC perp sometimes reports min amount as 1 contract for high-price assets.
    # If min_qty looks obviously too large for BTC-like price, fallback to step/precision-derived minimum.
    if min_qty is not None and min_qty >= 1 and price >= 100:
        if step and step > 0:
            min_qty = step
        elif precision_amount is not None and precision_amount >= 0:
            min_qty = 10 ** (-precision_amount)

    if step is None and precision_amount is not None and precision_amount >= 0:
        step = 10 ** (-precision_amount)

    return min_qty, step, precision_amount


def apply_precision(amount: float, precision: int | float | None = None, step: float | None = None) -> tuple[float, bool]:
    if amount <= 0:
        return 0.0, False

    original = float(amount)
    result = original

    if precision is not None:
        try:
            p = int(precision)
            if p >= 0:
                result = round(result, p)
        except (TypeError, ValueError):
            pass

    if step is not None:
        try:
            step_val = float(step)
            if step_val > 0:
                units = math.floor(result / step_val)
                result = units * step_val
        except (TypeError, ValueError):
            pass

    changed = abs(result - original) > 1e-12
    return max(0.0, float(result)), changed


def _nested_float(obj: dict[str, Any], key1: str, key2: str) -> float | None:
    raw = (obj.get(key1) or {}).get(key2)
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _as_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _as_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _first_float(data: dict[str, Any], keys: list[str]) -> float | None:
    for key in keys:
        if key in data:
            maybe = _as_float_or_none(data.get(key))
            if maybe is not None:
                return maybe
    return None
