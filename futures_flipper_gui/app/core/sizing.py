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
) -> tuple[float | None, list[str]]:
    warnings: list[str] = []

    if price <= 0:
        raise ValueError("price must be > 0")
    if leverage <= 0:
        raise ValueError("leverage must be > 0")
    if margin_usdt <= 0:
        return None, ["Non-positive margin"]

    notional = float(margin_usdt) * float(leverage)
    raw_amount = notional / float(price)

    limits = (market_info or {}).get("limits") or {}
    precision = (market_info or {}).get("precision") or {}

    amount_precision = precision.get("amount")
    amount_step = _nested_float(limits, "amount", "step")
    min_amount = _nested_float(limits, "amount", "min")
    max_amount = _nested_float(limits, "amount", "max")

    adjusted_amount, changed = apply_precision(raw_amount, precision=amount_precision, step=amount_step)
    if changed:
        warnings.append("Precision adjusted")

    if adjusted_amount <= 0:
        return None, warnings + ["Amount became zero after precision"]

    if min_amount is not None and adjusted_amount < min_amount:
        return None, warnings + [f"Below min amount ({adjusted_amount} < {min_amount})"]

    if max_amount is not None and adjusted_amount > max_amount:
        adjusted_amount = max_amount
        adjusted_amount, changed_max = apply_precision(adjusted_amount, precision=amount_precision, step=amount_step)
        if changed_max:
            warnings.append("Clamped to max amount")

    price_precision = precision.get("price")
    price_step = _nested_float(limits, "price", "step")
    adjusted_price, price_changed = apply_precision(float(price), precision=price_precision, step=price_step)
    if price_changed:
        warnings.append("Price precision adjusted")

    cost = adjusted_amount * adjusted_price
    min_cost = _nested_float(limits, "cost", "min")
    max_cost = _nested_float(limits, "cost", "max")

    if min_cost is not None and cost < min_cost:
        return None, warnings + [f"Below min cost ({cost} < {min_cost})"]

    if max_cost is not None and cost > max_cost:
        target_amount = max_cost / adjusted_price
        adjusted_amount, changed_cost = apply_precision(target_amount, precision=amount_precision, step=amount_step)
        if changed_cost:
            warnings.append("Adjusted by max cost")
        if adjusted_amount <= 0:
            return None, warnings + ["Amount became zero after max cost adjustment"]

    if min_amount is not None and adjusted_amount < min_amount:
        return None, warnings + [f"Below min amount ({adjusted_amount} < {min_amount})"]

    return adjusted_amount, warnings


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
