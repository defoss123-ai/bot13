from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError


class BlockConfig(BaseModel):
    enabled: bool = True
    weight: int = 1
    params: dict[str, Any] = Field(default_factory=dict)


class StrategyConfig(BaseModel):
    mode: Literal["and", "score"] = "and"
    min_score: int = 1
    enabled_blocks: dict[str, BlockConfig] = Field(default_factory=dict)


def default_config() -> StrategyConfig:
    return StrategyConfig(
        mode="and",
        min_score=2,
        enabled_blocks={
            "trend_ema": BlockConfig(
                enabled=True,
                weight=1,
                params={"ema_fast": 50, "ema_slow": 200},
            ),
            "impulse_gate": BlockConfig(
                enabled=True,
                weight=1,
                params={"lookback": 5, "min_pct": 0.25},
            ),
            "volume_filter": BlockConfig(
                enabled=True,
                weight=1,
                params={"mult": 1.2, "lookback": 20},
            ),
            "pullback_ema": BlockConfig(
                enabled=True,
                weight=1,
                params={"ema": 21, "confirm_close": True},
            ),
            "breakout_donchian": BlockConfig(
                enabled=True,
                weight=1,
                params={"lookback": 30},
            ),
            "rsi_filter": BlockConfig(
                enabled=True,
                weight=1,
                params={"rsi_min": 35, "rsi_max": 70},
            ),
        },
    )


def load_config(storage: Any) -> StrategyConfig:
    raw_value = storage.get_setting("strategy_config_json", "")
    if not raw_value:
        return default_config()

    try:
        data = json.loads(raw_value)
        return StrategyConfig.model_validate(data)
    except (json.JSONDecodeError, ValidationError, TypeError, ValueError):
        return default_config()


def save_config(storage: Any, config: StrategyConfig) -> None:
    payload = config.model_dump_json()
    storage.set_setting("strategy_config_json", payload)
