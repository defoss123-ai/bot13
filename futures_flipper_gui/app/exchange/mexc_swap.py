from __future__ import annotations

from typing import Any

import ccxt


class MexcSwapClient:
    def __init__(self, api_key: str, api_secret: str) -> None:
        self.exchange = ccxt.mexc(
            {
                "apiKey": api_key,
                "secret": api_secret,
                "enableRateLimit": True,
            }
        )
        self._markets_loaded = False

    def load_markets(self) -> dict[str, Any]:
        try:
            markets = self.exchange.load_markets()
            self._markets_loaded = True
            return markets
        except Exception as exc:
            raise RuntimeError(f"Failed to load MEXC markets: {exc}") from exc

    def resolve_symbol(self, user_symbol: str) -> str:
        if not user_symbol or not user_symbol.strip():
            raise ValueError("Symbol is empty. Use formats like BTC/USDT, BTCUSDT, BTC/USDT:USDT.")

        if not self._markets_loaded:
            self.load_markets()

        raw = user_symbol.strip().upper()

        candidates = {raw}
        if "/" not in raw and ":" not in raw and raw.endswith("USDT") and len(raw) > 4:
            base = raw[:-4]
            candidates.add(f"{base}/USDT")
            candidates.add(f"{base}/USDT:USDT")
        if "/" in raw and ":" not in raw:
            candidates.add(f"{raw}:USDT")

        markets = self.exchange.markets or {}
        for symbol, market in markets.items():
            if not market.get("swap") or market.get("quote") != "USDT":
                continue
            normalized = symbol.upper()
            market_id = str(market.get("id", "")).upper()
            if normalized in candidates or market_id in candidates:
                return symbol

        raise ValueError(
            f"USDT swap symbol not found for '{user_symbol}'. Supported inputs: BTC/USDT, BTCUSDT, BTC/USDT:USDT."
        )

    def healthcheck(self) -> bool:
        try:
            self.load_markets()
            self.exchange.fetch_time()
            return True
        except Exception:
            return False

    def fetch_ohlcv(self, symbol: str, timeframe: str = "1m", limit: int = 200) -> list[list[float]]:
        try:
            swap_symbol = self.resolve_symbol(symbol)
            return self.exchange.fetch_ohlcv(swap_symbol, timeframe=timeframe, limit=limit)
        except Exception as exc:
            raise RuntimeError(f"Failed to fetch OHLCV for {symbol}: {exc}") from exc

    def fetch_ticker(self, symbol: str) -> dict[str, Any]:
        try:
            swap_symbol = self.resolve_symbol(symbol)
            return self.exchange.fetch_ticker(swap_symbol)
        except Exception as exc:
            raise RuntimeError(f"Failed to fetch ticker for {symbol}: {exc}") from exc

    def set_leverage(self, symbol: str, leverage: int) -> dict[str, Any]:
        try:
            swap_symbol = self.resolve_symbol(symbol)
            return self.exchange.set_leverage(leverage, swap_symbol)
        except Exception as exc:
            raise RuntimeError(f"Failed to set leverage for {symbol}: {exc}") from exc

    def create_order(
        self,
        symbol: str,
        type: str,
        side: str,
        amount: float,
        price: float | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            swap_symbol = self.resolve_symbol(symbol)
            return self.exchange.create_order(
                symbol=swap_symbol,
                type=type,
                side=side,
                amount=amount,
                price=price,
                params=params or {},
            )
        except Exception as exc:
            raise RuntimeError(f"Failed to create order for {symbol}: {exc}") from exc

    def cancel_order(self, order_id: str, symbol: str | None = None) -> dict[str, Any]:
        try:
            swap_symbol = self.resolve_symbol(symbol) if symbol else None
            return self.exchange.cancel_order(order_id, symbol=swap_symbol)
        except Exception as exc:
            raise RuntimeError(f"Failed to cancel order {order_id}: {exc}") from exc

    def fetch_order(self, order_id: str, symbol: str | None = None) -> dict[str, Any]:
        try:
            swap_symbol = self.resolve_symbol(symbol) if symbol else None
            return self.exchange.fetch_order(order_id, symbol=swap_symbol)
        except Exception as exc:
            raise RuntimeError(f"Failed to fetch order {order_id}: {exc}") from exc

    def fetch_open_orders(self) -> list[dict[str, Any]]:
        try:
            return self.exchange.fetch_open_orders()
        except Exception as exc:
            raise RuntimeError(f"Failed to fetch open orders: {exc}") from exc

    def fetch_positions(self) -> list[dict[str, Any]]:
        try:
            fetch_positions = getattr(self.exchange, "fetch_positions", None)
            if fetch_positions is None:
                raise NotImplementedError("fetch_positions is not supported by this exchange client")
            return fetch_positions()
        except NotImplementedError:
            raise
        except Exception as exc:
            raise RuntimeError(f"Failed to fetch positions: {exc}") from exc
