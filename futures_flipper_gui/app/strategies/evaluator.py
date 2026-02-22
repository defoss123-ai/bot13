from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.strategies.builder import BlockConfig, StrategyConfig


@dataclass
class SignalResult:
    signal: bool
    score: int
    reason: str
    reasons: list[str] = field(default_factory=list)


class SignalEvaluator:
    @staticmethod
    def evaluate(config: StrategyConfig, data: dict[str, Any]) -> SignalResult:
        closes: list[float] = data.get("closes", [])
        highs: list[float] = data.get("highs", [])
        volumes: list[float] = data.get("volumes", [])
        indicators: dict[str, float] = data.get("indicators", {})

        if not closes:
            return SignalResult(False, 0, "no_data", ["No close data"])

        passed: list[bool] = []
        reasons: list[str] = []
        score = 0

        for block_name, block in config.enabled_blocks.items():
            if not block.enabled:
                continue

            ok, detail = SignalEvaluator._eval_block(
                block_name=block_name,
                block=block,
                closes=closes,
                highs=highs,
                volumes=volumes,
                indicators=indicators,
            )
            passed.append(ok)
            reasons.append(f"{block_name}:{'ok' if ok else 'fail'}({detail})")
            if ok:
                score += max(0, int(block.weight))

        if config.mode == "and":
            signal = all(passed) if passed else False
        else:
            signal = score >= int(config.min_score)

        return SignalResult(signal=signal, score=score, reason="signal" if signal else "no_signal", reasons=reasons)

    @staticmethod
    def _eval_block(
        block_name: str,
        block: BlockConfig,
        closes: list[float],
        highs: list[float],
        volumes: list[float],
        indicators: dict[str, float],
    ) -> tuple[bool, str]:
        params = block.params
        close = closes[-1]

        if block_name == "trend_ema":
            fast = indicators.get("ema_50")
            slow = indicators.get("ema_200")
            if fast is None or slow is None:
                return False, "ema_unavailable"
            ok = fast > slow
            return ok, f"ema50={fast:.6f} ema200={slow:.6f}"

        if block_name == "impulse_gate":
            min_pct = float(params.get("min_pct", 0.25))
            impulse = indicators.get("impulse_5")
            if impulse is None:
                return False, "impulse_unavailable"
            return impulse >= min_pct, f"impulse={impulse:.4f} min_pct={min_pct}"

        if block_name == "volume_filter":
            lookback = int(params.get("lookback", 20))
            mult = float(params.get("mult", 1.2))
            if len(volumes) <= lookback:
                return False, "not_enough_volume"
            baseline = sum(volumes[-(lookback + 1):-1]) / lookback
            if baseline <= 0:
                return False, "baseline_volume_zero"
            ratio = volumes[-1] / baseline
            return ratio >= mult, f"ratio={ratio:.4f} min={mult}"

        if block_name == "pullback_ema":
            ema_value = indicators.get("ema_21")
            if ema_value is None:
                return False, "ema21_unavailable"
            confirm_close = bool(params.get("confirm_close", True))
            near_ema = close <= ema_value * 1.01
            confirmed = close > closes[-2] if confirm_close and len(closes) > 1 else True
            return near_ema and confirmed, f"near_ema={near_ema} confirmed={confirmed}"

        if block_name == "breakout_donchian":
            channel_high = indicators.get("donchian_high_30")
            if channel_high is None:
                return False, "donchian_unavailable"
            return close > channel_high, f"close={close:.6f} channel_high={channel_high:.6f}"

        if block_name == "rsi_filter":
            rsi_value = indicators.get("rsi_14")
            if rsi_value is None:
                return False, "rsi_unavailable"
            rsi_min = float(params.get("rsi_min", 35))
            rsi_max = float(params.get("rsi_max", 70))
            ok = rsi_min <= rsi_value <= rsi_max
            return ok, f"rsi={rsi_value:.4f} range=[{rsi_min}, {rsi_max}]"

        return True, "unknown_block_skipped"
