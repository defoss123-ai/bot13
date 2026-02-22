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
) -> tuple[float | None, str | None, dict[str, float | None]]:
    if price <= 0:
        raise ValueError("price must be > 0")
    if leverage <= 0:
        raise ValueError("leverage must be > 0")

    market = market_info or {}
    limits = market.get("limits") or {}
    precision = market.get("precision") or {}

    min_qty = _nested_float(limits, "amount", "min")
    min_cost = _nested_float(limits, "cost", "min")
    amount_precision = precision.get("amount")
    amount_step = _nested_float(limits, "amount", "step")

    qty_raw = 0.0
    qty_rounded = 0.0

    if margin_usdt <= 0:
        details = {
            "qty_raw": qty_raw,
            "qty_rounded": qty_rounded,
            "min_qty": min_qty,
            "min_cost": min_cost,
            "cost": 0.0,
        }
        return None, "Non-positive margin", details

    notional = float(margin_usdt) * float(leverage)
    qty_raw = notional / float(price)
    qty_rounded, _ = apply_precision(qty_raw, precision=amount_precision, step=amount_step)

    cost = qty_rounded * float(price)
    details = {
        "qty_raw": qty_raw,
        "qty_rounded": qty_rounded,
        "min_qty": min_qty,
        "min_cost": min_cost,
        "cost": cost,
    }

    if qty_rounded <= 0:
        return None, "qty_after_round <= 0", details
    if min_qty is not None and qty_rounded < min_qty:
        return None, f"qty_rounded < minQty ({qty_rounded} < {min_qty})", details
    if min_cost is not None and cost < min_cost:
        return None, f"notional < minCost ({cost} < {min_cost})", details

    return qty_rounded, None, details


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
