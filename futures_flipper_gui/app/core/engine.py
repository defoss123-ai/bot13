from __future__ import annotations

import json
import random
import threading
import time
from typing import Any

from app.core.executor import place_entry
from app.core.exits import PositionState, close_position, compute_tp_sl, configure_exits, evaluate_exit, utc_iso
from app.core.logger import logger
from app.core.sizing import compute_margin_to_use, compute_order_amount
from app.core.state_sync import sync_exchange_state
from app.core.storage import Storage
from app.exchange.mexc_swap import MexcSwapClient
from app.strategies.builder import load_config
from app.strategies.evaluator import SignalEvaluator
from app.strategies.indicators import atr, donchian_high, donchian_low, ema, impulse_pct, rsi


class TradingEngine:
    def __init__(self, storage: Storage) -> None:
        self.storage = storage
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._positions: dict[str, PositionState] = {}
        self._round_robin_index = 0
        self._last_stale_check_ts = 0.0

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        with self._lock:
            if self.is_running():
                return

        self._safe_state_sync()
        self._restore_positions_from_storage()

        with self._lock:
            self._stop_event.clear()
            self._thread = threading.Thread(target=self._run_loop, name="TradingEngineLoop", daemon=True)
            self._thread.start()
            logger.info("Engine started")

    def stop(self) -> None:
        with self._lock:
            thread = self._thread
            if thread is None:
                return
            self._stop_event.set()

        thread.join(timeout=5)
        with self._lock:
            self._thread = None
        self.storage.close_thread_connection()
        logger.info("Engine stopped")


    def cancel_all_open_orders(self, symbol: str | None = None) -> int:
        client = self._build_client()
        if client is None:
            logger.warning("Cancel all open orders skipped: MEXC API keys are not configured")
            return 0

        canceled = 0
        try:
            open_orders = client.fetch_open_orders()
        except Exception as exc:
            logger.warning(f"Failed to fetch open orders for cancel: {exc}")
            return 0

        for order in open_orders:
            order_symbol = str(order.get("symbol") or "")
            if symbol and order_symbol.upper() != symbol.upper():
                continue

            order_id = str(order.get("id") or "")
            if not order_id:
                continue

            try:
                client.cancel_order(order_id=order_id, symbol=order_symbol or None)
                canceled += 1
                logger.info(f"Canceled open order {order_id} ({order_symbol})")
            except Exception as exc:
                logger.warning(f"Failed to cancel order {order_id} ({order_symbol}): {exc}")

        return canceled

    def panic_stop(self) -> None:
        paper_mode = self._setting_bool("paper_mode", True)
        self.stop()

        if paper_mode:
            logger.warning("Panic stop in paper mode: only logging, no exchange cancel calls")
            return

        canceled = self.cancel_all_open_orders()
        logger.warning(f"Panic stop completed: canceled {canceled} open orders")

    def _run_loop(self) -> None:
        try:
            while not self._stop_event.is_set():
                interval = self._setting_int("check_interval_sec", 5, minimum=1)
                try:
                    self._loop_iteration()
                except Exception:
                    logger.exception("Engine loop error")
                self._stop_event.wait(interval)
        finally:
            self.storage.close_thread_connection()


    def _safe_state_sync(self) -> None:
        client = self._build_client()
        if client is None:
            logger.warning("State sync skipped: MEXC API keys are not configured")
            return

        try:
            sync_exchange_state(self.storage, client, logger)
        except Exception as exc:
            logger.warning(f"State sync failed: {exc}")

    def _restore_positions_from_storage(self) -> None:
        restored: dict[str, PositionState] = {}
        open_orders = self.storage.list_open_orders()

        tp_sl_by_symbol: dict[str, dict[str, str | None]] = {}
        for order in open_orders:
            symbol = str(order.get("symbol") or "")
            if not symbol:
                continue
            slot = tp_sl_by_symbol.setdefault(symbol, {"tp": None, "sl": None})
            kind = str(order.get("kind") or "").lower()
            meta = str(order.get("meta_json") or "").lower()
            if "tp" in kind or '"reduceonly": true' in meta:
                slot["tp"] = str(order.get("order_id") or "")
            if "sl" in kind or "stop" in kind or '"stopprice"' in meta:
                slot["sl"] = str(order.get("order_id") or "")

        for row in self.storage.list_positions():
            symbol = str(row.get("symbol") or "")
            if not symbol:
                continue

            side = str(row.get("side") or "buy").lower()
            amount = float(row.get("amount") or 0.0)
            entry_price = float(row.get("entry_price") or 0.0)
            if amount <= 0 or entry_price <= 0:
                continue

            tp_pct = float(self._pair_value(symbol, "tp_pct", 0.12))
            sl_pct = float(self._pair_value(symbol, "sl_pct", 0.25))
            tp_price, sl_price = compute_tp_sl(entry_price=entry_price, side="buy" if side in {"long", "buy"} else "sell", tp_pct=tp_pct, sl_pct=sl_pct)

            ref = tp_sl_by_symbol.get(symbol, {})
            restored[symbol] = PositionState(
                symbol=symbol,
                side="buy" if side in {"long", "buy"} else "sell",
                amount=amount,
                entry_price=entry_price,
                opened_ts=time.time(),
                tp_price=tp_price,
                sl_price=sl_price,
                initial_sl_price=sl_price,
                tp_order_id=ref.get("tp"),
                sl_order_id=ref.get("sl"),
            )

        self._positions = restored
        logger.info(f"Restored {len(self._positions)} positions into engine state")

    def _pair_value(self, symbol: str, key: str, default: float) -> float:
        for pair in self.storage.list_pairs():
            if str(pair.get("symbol") or "") == symbol:
                try:
                    return float(pair.get(key) or default)
                except (TypeError, ValueError):
                    return default
        return default

    def _loop_iteration(self) -> None:
        client = self._build_client()
        if client is None:
            logger.warning("Engine tick skipped: MEXC API keys are not configured")
            return

        self._maybe_cleanup_stale_orders(client)
        config = load_config(self.storage)
        paper_mode = self._setting_bool("paper_mode", True)

        self._process_open_positions(client, paper_mode)

        pairs = [p for p in self.storage.list_pairs() if int(p.get("enabled", 0)) == 1]
        active_pairs = [p for p in pairs if str(p.get("symbol", "")) not in self._positions]
        active_pairs = self._apply_zero_fee_filter(active_pairs)
        logger.info(f"Loop tick: {len(active_pairs)} active symbols")

        candidates: list[dict[str, Any]] = []

        for pair in active_pairs:
            symbol = str(pair.get("symbol", "")).strip()
            if not symbol:
                continue

            try:
                swap_symbol = client.resolve_symbol(symbol)
                ohlcv = client.fetch_ohlcv(swap_symbol, timeframe="1m", limit=200)
                market_data = self._prepare_market_data(ohlcv)
                result = SignalEvaluator.evaluate(config, market_data)

                if result.signal:
                    reason = "; ".join(result.reasons)
                    logger.info(f"Signal {symbol} reasons={reason} score={result.score}")
                    market_info = (client.exchange.markets or {}).get(swap_symbol, {})
                    candidates.append(
                        {
                            "symbol": symbol,
                            "score": result.score,
                            "reason": reason,
                            "leverage": int(pair.get("leverage", 1) or 1),
                            "price": float(market_data["closes"][-1]),
                            "tp_pct": float(pair.get("tp_pct", 0.0) or 0.0),
                            "sl_pct": float(pair.get("sl_pct", 0.0) or 0.0),
                            "market_info": market_info,
                        }
                    )
                else:
                    logger.info(f"No signal {symbol} reasons={'; '.join(result.reasons)} score={result.score}")
            except Exception as exc:
                logger.warning(f"Symbol processing failed for {symbol}: {exc}")

        if not candidates:
            return

        selected = self._apply_position_limit(candidates)
        free_balance = self._fetch_free_usdt_balance(client)
        sizing_settings = self._sizing_settings()
        execution_settings = self._execution_settings()

        for item in selected:
            margin_usdt = compute_margin_to_use(free_balance, sizing_settings)
            amount, sizing_error, sizing_details = compute_order_amount(
                price=float(item["price"]),
                margin_usdt=margin_usdt,
                leverage=int(item["leverage"]),
                market_info=item.get("market_info") or {},
                symbol=item["symbol"],
                client=client,
            )

            logger.info(
                "Market limits resolved: min_qty=%s step=%s precision=%s"
                % (
                    sizing_details.get("min_qty"),
                    sizing_details.get("step"),
                    sizing_details.get("precision_amount"),
                )
            )

            logger.info(
                "Sizing: mode=%s margin_usdt=%.4f price=%.8f qty_raw=%.8f qty_rounded=%.8f minQty=%s minCost=%s"
                % (
                    sizing_settings.get("sizing_mode", "percent"),
                    margin_usdt,
                    float(item["price"]),
                    float(sizing_details.get("qty_raw") or 0.0),
                    float(sizing_details.get("qty_rounded") or 0.0),
                    sizing_details.get("min_qty"),
                    sizing_details.get("min_cost"),
                )
            )

            if amount is None:
                logger.warning(
                    f"Cannot enter {item['symbol']}: qty too small after precision/minQty/minCost. "
                    f"Increase sizing_fixed_usdt/sizing_percent or lower reserve. ({sizing_error})"
                )
                continue

            if paper_mode:
                logger.info(
                    f"Would enter trade {item['symbol']} score={item['score']} reason={item['reason']} "
                    f"margin={margin_usdt:.4f} amount={amount:.8f} lev={item['leverage']}"
                )
                entry_success = True
                entry_price = float(item["price"])
                filled = amount
                order_id = "paper-entry"
                entry_status = "paper"
            else:
                logger.info(f"Placing entry order {item['symbol']} amount={amount:.8f} side=buy")
                result = place_entry(
                    symbol=item["symbol"],
                    side="buy",
                    amount=amount,
                    settings=execution_settings,
                    client=client,
                )
                logger.info(
                    f"Entry result symbol={item['symbol']} success={result.success} status={result.status} "
                    f"filled={result.filled:.8f} reason={result.reason}"
                )
                entry_success = result.success
                entry_price = float(result.avg_price or item["price"])
                filled = float(result.filled)
                order_id = result.order_id or ""
                entry_status = result.status
                if entry_success:
                    logger.info(
                        f"Order filled {item['symbol']} qty={filled:.8f} avg_price={entry_price:.8f} status={entry_status}"
                    )

            if not entry_success:
                continue

            position = self._open_position(
                symbol=item["symbol"],
                amount=filled,
                entry_price=entry_price,
                tp_pct=float(item["tp_pct"]),
                sl_pct=float(item["sl_pct"]),
                settings=execution_settings,
                client=client,
                paper_mode=paper_mode,
            )
            self._positions[position.symbol] = position
            self.storage.insert_order(
                ts=utc_iso(),
                symbol=position.symbol,
                kind="entry",
                order_id=order_id,
                status=entry_status,
                meta_json=json.dumps({"amount": filled, "entry_price": entry_price}),
            )

    def _open_position(
        self,
        symbol: str,
        amount: float,
        entry_price: float,
        tp_pct: float,
        sl_pct: float,
        settings: dict[str, Any],
        client: MexcSwapClient,
        paper_mode: bool,
    ) -> PositionState:
        tp_price, sl_price = compute_tp_sl(entry_price=entry_price, side="buy", tp_pct=tp_pct, sl_pct=sl_pct)
        position = PositionState(
            symbol=symbol,
            side="buy",
            amount=amount,
            entry_price=entry_price,
            opened_ts=time.time(),
            tp_price=tp_price,
            sl_price=sl_price,
            initial_sl_price=sl_price,
        )
        return configure_exits(position=position, settings=settings, client=client, paper_mode=paper_mode)

    def _process_open_positions(self, client: MexcSwapClient, paper_mode: bool) -> None:
        if not self._positions:
            return

        execution_settings = self._execution_settings()
        now_ts = time.time()

        for symbol in list(self._positions.keys()):
            position = self._positions[symbol]
            try:
                ticker = client.fetch_ticker(symbol)
                last_price = float(ticker.get("last") or ticker.get("close") or position.entry_price)
            except Exception as exc:
                logger.warning(f"Ticker fetch failed for open position {symbol}: {exc}")
                continue

            decision = evaluate_exit(position, last_price, execution_settings, now_ts)

            if decision.break_even_moved:
                logger.info(f"Break-even moved symbol={symbol} new_sl={position.sl_price:.8f}")

            if not decision.should_close:
                continue

            try:
                order = close_position(
                    position=position,
                    decision=decision,
                    client=client,
                    settings=execution_settings,
                    paper_mode=paper_mode,
                )
                filled = float(order.get("filled") or position.amount)
                exit_price = float(order.get("average") or decision.exit_price or last_price)
                pnl = (exit_price - position.entry_price) * filled

                self.storage.insert_trade(
                    ts=utc_iso(),
                    symbol=position.symbol,
                    side=position.side,
                    qty=filled,
                    entry=position.entry_price,
                    exit=exit_price,
                    pnl=pnl,
                    mode="paper" if paper_mode else "live",
                    reason=decision.reason,
                )
                self.storage.insert_order(
                    ts=utc_iso(),
                    symbol=position.symbol,
                    kind="exit",
                    order_id=str(order.get("id") or ""),
                    status=str(order.get("status") or "closed"),
                    meta_json=json.dumps({"reason": decision.reason, "exit_price": exit_price}),
                )
                logger.info(
                    f"Position closed symbol={position.symbol} reason={decision.reason} "
                    f"entry={position.entry_price:.8f} exit={exit_price:.8f} pnl={pnl:.8f}"
                )
            except Exception as exc:
                logger.warning(f"Failed to close position {symbol}: {exc}")
                continue

            self._positions.pop(symbol, None)

    def _apply_position_limit(self, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
        max_positions_raw = (self.storage.get_setting("max_concurrent_positions", "1") or "1").strip().upper()

        if max_positions_raw == "ALL":
            limit = len(candidates)
        else:
            try:
                limit = max(1, int(max_positions_raw))
            except ValueError:
                limit = 1

        selection_mode = (self.storage.get_setting("selection_mode", "best_score") or "best_score").strip().lower()
        ordered = sorted(candidates, key=lambda c: float(c.get("score", 0)), reverse=True)

        if selection_mode == "round_robin":
            return self._select_round_robin(ordered, limit)
        if selection_mode == "random_top_k":
            return self._select_random_top_k(ordered, limit)
        return ordered[:limit]


    def _apply_zero_fee_filter(self, pairs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not self._setting_bool("trade_only_zero_fee", False):
            return pairs

        allowed = {symbol.upper() for symbol in self.storage.list_zero_fee_symbols()}
        filtered = [p for p in pairs if str(p.get("symbol", "")).upper() in allowed]
        return filtered

    def _select_round_robin(self, ordered: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
        if not ordered or limit <= 0:
            return []

        start = self._round_robin_index % len(ordered)
        selected = [ordered[(start + i) % len(ordered)] for i in range(min(limit, len(ordered)))]
        self._round_robin_index = (start + min(limit, len(ordered))) % len(ordered)
        return selected

    def _select_random_top_k(self, ordered: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
        if not ordered or limit <= 0:
            return []

        random_top_k = self._setting_int("random_top_k", 3, minimum=1)
        pool = ordered[: min(random_top_k, len(ordered))]
        if limit >= len(pool):
            random.shuffle(pool)
            return pool
        return random.sample(pool, k=limit)


    def _build_client(self) -> MexcSwapClient | None:
        api_keys = self.storage.get_api_keys("MEXC")
        if not api_keys:
            return None
        return MexcSwapClient(api_key=api_keys.get("api_key", ""), api_secret=api_keys.get("api_secret", ""))

    def _maybe_cleanup_stale_orders(self, client: MexcSwapClient) -> None:
        now_ts = time.time()
        if now_ts - self._last_stale_check_ts < 30:
            return
        self._last_stale_check_ts = now_ts

        ttl_sec = self._setting_int("stale_order_ttl_sec", 300, minimum=1)

        try:
            open_orders = client.fetch_open_orders()
        except Exception as exc:
            logger.warning(f"Stale order cleaner failed to fetch open orders: {exc}")
            return

        for order in open_orders:
            order_id = str(order.get("id") or "")
            symbol = str(order.get("symbol") or "")
            if not order_id:
                continue

            order_ts = self._order_timestamp_seconds(order)
            if order_ts is None:
                continue

            if now_ts - order_ts <= ttl_sec:
                continue

            try:
                client.cancel_order(order_id=order_id, symbol=symbol or None)
                logger.warning(f"Canceled stale order {order_id} ({symbol})")
            except Exception as exc:
                logger.warning(f"Failed to cancel stale order {order_id} ({symbol}): {exc}")

    @staticmethod
    def _order_timestamp_seconds(order: dict[str, Any]) -> float | None:
        raw_ts = order.get("timestamp")
        if raw_ts is None:
            return None
        try:
            value = float(raw_ts)
        except (TypeError, ValueError):
            return None

        return value / 1000.0 if value > 10_000_000_000 else value

    def _execution_settings(self) -> dict[str, str]:
        keys = [
            "entry_order_type",
            "exit_order_type",
            "limit_offset_bps",
            "entry_timeout_sec",
            "entry_retry_count",
            "allow_market_fallback",
            "min_fill_pct",
            "max_trade_duration_sec",
            "break_even_enabled",
            "break_even_trigger_pct",
            "break_even_offset_pct",
        ]
        return {k: self.storage.get_setting(k, "") or "" for k in keys}

    def _sizing_settings(self) -> dict[str, str]:
        keys = [
            "sizing_mode",
            "sizing_percent",
            "sizing_fixed_usdt",
            "sizing_reserve_usdt",
            "max_margin_per_trade_usdt",
        ]
        return {k: self.storage.get_setting(k, "") or "" for k in keys}

    def _fetch_free_usdt_balance(self, client: MexcSwapClient) -> float:
        try:
            balance = client.exchange.fetch_balance()
            usdt = balance.get("USDT", {}) if isinstance(balance, dict) else {}
            free_value = usdt.get("free") if isinstance(usdt, dict) else None
            if free_value is None and isinstance(balance, dict):
                free_value = (balance.get("free") or {}).get("USDT")
            if free_value is None:
                raise ValueError("USDT free balance is unavailable")
            return float(free_value)
        except Exception:
            logger.warning("Using paper mode balance fallback: 100 USDT")
            return 100.0

    def _setting_bool(self, key: str, default: bool) -> bool:
        value = self.storage.get_setting(key, "1" if default else "0")
        if value is None:
            return default
        return str(value).strip().lower() in {"1", "true", "yes", "on"}

    def _setting_int(self, key: str, default: int, minimum: int = 0) -> int:
        value = self.storage.get_setting(key, str(default)) or str(default)
        try:
            parsed = int(float(value))
        except ValueError:
            parsed = default
        return max(minimum, parsed)

    def _prepare_market_data(self, ohlcv: list[list[float]]) -> dict[str, Any]:
        if len(ohlcv) < 2:
            raise ValueError("Not enough OHLCV data")

        highs = [float(c[2]) for c in ohlcv]
        lows = [float(c[3]) for c in ohlcv]
        closes = [float(c[4]) for c in ohlcv]
        volumes = [float(c[5]) for c in ohlcv]

        indicators = {
            "ema_21": self._safe_last(ema(closes, 21)),
            "ema_50": self._safe_last(ema(closes, 50)),
            "ema_200": self._safe_last(ema(closes, 200)),
            "rsi_14": self._safe_last(rsi(closes, 14)),
            "atr_14": self._safe_last(atr(highs, lows, closes, 14)),
            "donchian_high_30": donchian_high(highs, 30),
            "donchian_low_30": donchian_low(lows, 30),
            "impulse_5": impulse_pct(closes, 5),
        }

        return {
            "highs": highs,
            "lows": lows,
            "closes": closes,
            "volumes": volumes,
            "indicators": indicators,
        }

    @staticmethod
    def _safe_last(values: list[float]) -> float:
        if not values:
            raise ValueError("Indicator produced no values")
        return float(values[-1])
