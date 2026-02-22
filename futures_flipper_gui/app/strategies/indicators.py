from __future__ import annotations

from typing import Iterable


def _as_float_list(values: Iterable[float]) -> list[float]:
    return [float(v) for v in values]


def ema(values: list[float], period: int) -> list[float]:
    if period <= 0:
        raise ValueError("period must be > 0")
    vals = _as_float_list(values)
    if len(vals) < period:
        raise ValueError("not enough values for ema")

    multiplier = 2.0 / (period + 1)
    seed = sum(vals[:period]) / period
    result: list[float] = [seed]

    prev = seed
    for price in vals[period:]:
        prev = (price - prev) * multiplier + prev
        result.append(prev)
    return result


def rsi(values: list[float], period: int = 14) -> list[float]:
    if period <= 0:
        raise ValueError("period must be > 0")
    vals = _as_float_list(values)
    if len(vals) < period + 1:
        raise ValueError("not enough values for rsi")

    gains: list[float] = []
    losses: list[float] = []
    for i in range(1, period + 1):
        delta = vals[i] - vals[i - 1]
        gains.append(max(delta, 0.0))
        losses.append(max(-delta, 0.0))

    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period

    def _rsi(g: float, l: float) -> float:
        if l == 0:
            return 100.0
        rs = g / l
        return 100.0 - (100.0 / (1.0 + rs))

    result = [_rsi(avg_gain, avg_loss)]

    for i in range(period + 1, len(vals)):
        delta = vals[i] - vals[i - 1]
        gain = max(delta, 0.0)
        loss = max(-delta, 0.0)
        avg_gain = ((avg_gain * (period - 1)) + gain) / period
        avg_loss = ((avg_loss * (period - 1)) + loss) / period
        result.append(_rsi(avg_gain, avg_loss))

    return result


def atr(highs: list[float], lows: list[float], closes: list[float], period: int = 14) -> list[float]:
    if period <= 0:
        raise ValueError("period must be > 0")
    h = _as_float_list(highs)
    l = _as_float_list(lows)
    c = _as_float_list(closes)

    if not (len(h) == len(l) == len(c)):
        raise ValueError("highs, lows, closes must have same length")
    if len(c) < period + 1:
        raise ValueError("not enough values for atr")

    true_ranges: list[float] = []
    for i in range(1, len(c)):
        tr = max(
            h[i] - l[i],
            abs(h[i] - c[i - 1]),
            abs(l[i] - c[i - 1]),
        )
        true_ranges.append(tr)

    initial_atr = sum(true_ranges[:period]) / period
    result = [initial_atr]
    prev_atr = initial_atr

    for tr in true_ranges[period:]:
        prev_atr = ((prev_atr * (period - 1)) + tr) / period
        result.append(prev_atr)

    return result


def donchian_high(highs: list[float], lookback: int) -> float:
    if lookback <= 0:
        raise ValueError("lookback must be > 0")
    h = _as_float_list(highs)
    if len(h) < lookback:
        raise ValueError("not enough values for donchian_high")
    return max(h[-lookback:])


def donchian_low(lows: list[float], lookback: int) -> float:
    if lookback <= 0:
        raise ValueError("lookback must be > 0")
    l = _as_float_list(lows)
    if len(l) < lookback:
        raise ValueError("not enough values for donchian_low")
    return min(l[-lookback:])


def impulse_pct(closes: list[float], lookback_bars: int) -> float:
    if lookback_bars <= 0:
        raise ValueError("lookback_bars must be > 0")
    c = _as_float_list(closes)
    if len(c) <= lookback_bars:
        raise ValueError("not enough values for impulse_pct")

    start = c[-(lookback_bars + 1)]
    end = c[-1]
    if start == 0:
        raise ValueError("start close is zero, cannot compute percent change")
    return ((end - start) / start) * 100.0


if __name__ == "__main__":
    closes = [100, 101, 102, 101, 103, 104, 106, 105, 107, 108, 110, 109, 111, 113, 112, 114]
    highs = [c + 1.5 for c in closes]
    lows = [c - 1.5 for c in closes]

    ema_vals = ema(closes, period=5)
    assert len(ema_vals) == len(closes) - 5 + 1

    rsi_vals = rsi(closes, period=14)
    assert len(rsi_vals) == len(closes) - 14
    assert all(0.0 <= x <= 100.0 for x in rsi_vals)

    atr_vals = atr(highs, lows, closes, period=14)
    assert len(atr_vals) == len(closes) - 14
    assert all(x >= 0.0 for x in atr_vals)

    d_high = donchian_high(highs, lookback=5)
    d_low = donchian_low(lows, lookback=5)
    assert d_high >= d_low

    imp = impulse_pct(closes, lookback_bars=5)
    assert isinstance(imp, float)

    print("All indicator checks passed.")
