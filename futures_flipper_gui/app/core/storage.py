import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json


DB_DIR = Path(__file__).resolve().parents[2] / "data"
DB_PATH = DB_DIR / "app.db"

DEFAULT_SETTINGS: dict[str, str] = {
    "check_interval_sec": "5",
    "max_concurrent_positions": "1",
    "ultra_scalp_enabled": "1",
    "ultra_tp_pct": "0.12",
    "ultra_sl_pct": "0.25",
    "max_trade_duration_sec": "45",
    "break_even_enabled": "1",
    "break_even_trigger_pct": "0.10",
    "break_even_offset_pct": "0.02",
    "sizing_mode": "percent",
    "sizing_percent": "10",
    "sizing_fixed_usdt": "20",
    "sizing_reserve_usdt": "10",
    "max_margin_per_trade_usdt": "200",
    "daily_loss_limit_pct": "3.0",
    "entry_order_type": "market",
    "exit_order_type": "market",
    "limit_offset_bps": "2",
    "entry_timeout_sec": "30",
    "entry_retry_count": "0",
    "allow_market_fallback": "0",
    "min_fill_pct": "80",
    "trade_only_zero_fee": "0",
    "selection_mode": "best_score",
    "random_top_k": "3",
    "stale_order_ttl_sec": "300",
    "paper_mode": "1",
    "strategy_config_json": json.dumps(
        {
            "mode": "and",
            "min_score": 2,
            "enabled_blocks": {
                "trend_ema": {
                    "enabled": True,
                    "weight": 1,
                    "params": {"ema_fast": 50, "ema_slow": 200},
                },
                "impulse_gate": {
                    "enabled": True,
                    "weight": 1,
                    "params": {"lookback": 5, "min_pct": 0.25},
                },
                "volume_filter": {
                    "enabled": True,
                    "weight": 1,
                    "params": {"mult": 1.2, "lookback": 20},
                },
                "pullback_ema": {
                    "enabled": True,
                    "weight": 1,
                    "params": {"ema": 21, "confirm_close": True},
                },
                "breakout_donchian": {
                    "enabled": True,
                    "weight": 1,
                    "params": {"lookback": 30},
                },
                "rsi_filter": {
                    "enabled": True,
                    "weight": 1,
                    "params": {"rsi_min": 35, "rsi_max": 70},
                },
            },
        }
    ),
}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_db() -> sqlite3.Connection:
    """Create SQLite database, required tables, and default settings."""
    DB_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)

    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS api_keys(
          exchange TEXT PRIMARY KEY,
          api_key TEXT,
          api_secret TEXT,
          created_at TEXT
        );

        CREATE TABLE IF NOT EXISTS pairs(
          symbol TEXT PRIMARY KEY,
          leverage INT,
          tp_pct REAL,
          sl_pct REAL,
          enabled INT,
          cooldown_sec INT
        );

        CREATE TABLE IF NOT EXISTS settings(
          key TEXT PRIMARY KEY,
          value TEXT
        );

        CREATE TABLE IF NOT EXISTS trades(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          ts TEXT,
          symbol TEXT,
          side TEXT,
          qty REAL,
          entry REAL,
          exit REAL,
          pnl REAL,
          mode TEXT,
          reason TEXT
        );

        CREATE TABLE IF NOT EXISTS orders(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          ts TEXT,
          symbol TEXT,
          kind TEXT,
          order_id TEXT,
          status TEXT,
          meta_json TEXT
        );

        CREATE TABLE IF NOT EXISTS positions(
          symbol TEXT PRIMARY KEY,
          side TEXT,
          amount REAL,
          entry_price REAL,
          unrealized_pnl REAL,
          status TEXT,
          meta_json TEXT,
          updated_at TEXT
        );

        CREATE TABLE IF NOT EXISTS zero_fee_symbols(
          symbol TEXT PRIMARY KEY,
          enabled INT,
          updated_at TEXT
        );
        """
    )

    conn.executemany(
        "INSERT OR IGNORE INTO settings(key, value) VALUES(?, ?)",
        list(DEFAULT_SETTINGS.items()),
    )

    conn.commit()
    return conn


class Storage:
    def __init__(self, conn: sqlite3.Connection | None = None) -> None:
        self.conn = conn if conn is not None else init_db()
        self.conn.row_factory = sqlite3.Row

    def get_setting(self, key: str, default: str | None = None) -> str | None:
        row = self.conn.execute(
            "SELECT value FROM settings WHERE key = ?", (key,)
        ).fetchone()
        return row["value"] if row else default

    def set_setting(self, key: str, value: Any) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO settings(key, value) VALUES(?, ?)",
            (key, str(value)),
        )
        self.conn.commit()

    def list_pairs(self) -> list[dict[str, Any]]:
        rows = self.conn.execute("SELECT * FROM pairs ORDER BY symbol").fetchall()
        return [dict(row) for row in rows]

    def upsert_pair(
        self,
        symbol: str,
        leverage: int,
        tp_pct: float,
        sl_pct: float,
        enabled: int,
        cooldown_sec: int,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO pairs(symbol, leverage, tp_pct, sl_pct, enabled, cooldown_sec)
            VALUES(?, ?, ?, ?, ?, ?)
            ON CONFLICT(symbol) DO UPDATE SET
              leverage=excluded.leverage,
              tp_pct=excluded.tp_pct,
              sl_pct=excluded.sl_pct,
              enabled=excluded.enabled,
              cooldown_sec=excluded.cooldown_sec
            """,
            (symbol, leverage, tp_pct, sl_pct, enabled, cooldown_sec),
        )
        self.conn.commit()

    def delete_pair(self, symbol: str) -> None:
        self.conn.execute("DELETE FROM pairs WHERE symbol = ?", (symbol,))
        self.conn.commit()

    def get_api_keys(self, exchange: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT * FROM api_keys WHERE exchange = ?", (exchange,)
        ).fetchone()
        return dict(row) if row else None

    def set_api_keys(self, exchange: str, api_key: str, api_secret: str) -> None:
        self.conn.execute(
            """
            INSERT INTO api_keys(exchange, api_key, api_secret, created_at)
            VALUES(?, ?, ?, ?)
            ON CONFLICT(exchange) DO UPDATE SET
              api_key=excluded.api_key,
              api_secret=excluded.api_secret,
              created_at=excluded.created_at
            """,
            (exchange, api_key, api_secret, _utc_now_iso()),
        )
        self.conn.commit()

    def insert_trade(
        self,
        ts: str,
        symbol: str,
        side: str,
        qty: float,
        entry: float,
        exit: float,
        pnl: float,
        mode: str,
        reason: str,
    ) -> int:
        cursor = self.conn.execute(
            """
            INSERT INTO trades(ts, symbol, side, qty, entry, exit, pnl, mode, reason)
            VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (ts, symbol, side, qty, entry, exit, pnl, mode, reason),
        )
        self.conn.commit()
        return int(cursor.lastrowid)

    def list_trades(self, limit: int = 200) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM trades ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(row) for row in rows]

    def insert_order(
        self,
        ts: str,
        symbol: str,
        kind: str,
        order_id: str,
        status: str,
        meta_json: str,
    ) -> int:
        cursor = self.conn.execute(
            """
            INSERT INTO orders(ts, symbol, kind, order_id, status, meta_json)
            VALUES(?, ?, ?, ?, ?, ?)
            """,
            (ts, symbol, kind, order_id, status, meta_json),
        )
        self.conn.commit()
        return int(cursor.lastrowid)

    def update_order_status(self, order_id: str, status: str) -> None:
        self.conn.execute(
            "UPDATE orders SET status = ? WHERE order_id = ?",
            (status, order_id),
        )
        self.conn.commit()

    def list_open_orders(self) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM orders WHERE status NOT IN ('closed', 'canceled') ORDER BY id DESC"
        ).fetchall()
        return [dict(row) for row in rows]


    def upsert_position(
        self,
        symbol: str,
        side: str,
        amount: float,
        entry_price: float,
        unrealized_pnl: float,
        status: str,
        meta_json: str,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO positions(symbol, side, amount, entry_price, unrealized_pnl, status, meta_json, updated_at)
            VALUES(?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(symbol) DO UPDATE SET
              side=excluded.side,
              amount=excluded.amount,
              entry_price=excluded.entry_price,
              unrealized_pnl=excluded.unrealized_pnl,
              status=excluded.status,
              meta_json=excluded.meta_json,
              updated_at=excluded.updated_at
            """,
            (symbol, side, amount, entry_price, unrealized_pnl, status, meta_json, _utc_now_iso()),
        )
        self.conn.commit()

    def list_positions(self) -> list[dict[str, Any]]:
        rows = self.conn.execute("SELECT * FROM positions ORDER BY symbol").fetchall()
        return [dict(row) for row in rows]

    def delete_positions_not_in(self, symbols: list[str]) -> None:
        if not symbols:
            self.conn.execute("DELETE FROM positions")
            self.conn.commit()
            return

        placeholders = ",".join("?" for _ in symbols)
        self.conn.execute(f"DELETE FROM positions WHERE symbol NOT IN ({placeholders})", tuple(symbols))
        self.conn.commit()

    def delete_open_orders_not_in(self, order_ids: list[str]) -> None:
        if not order_ids:
            self.conn.execute("DELETE FROM orders WHERE status NOT IN ('closed', 'canceled')")
            self.conn.commit()
            return

        placeholders = ",".join("?" for _ in order_ids)
        self.conn.execute(
            f"DELETE FROM orders WHERE status NOT IN ('closed', 'canceled') AND order_id NOT IN ({placeholders})",
            tuple(order_ids),
        )
        self.conn.commit()

    def list_zero_fee_symbols(self) -> list[str]:
        rows = self.conn.execute(
            "SELECT symbol FROM zero_fee_symbols WHERE enabled = 1 ORDER BY symbol"
        ).fetchall()
        return [str(row["symbol"]) for row in rows]

    def set_zero_fee_symbol(self, symbol: str, enabled: int) -> None:
        normalized = symbol.strip().upper()
        if not normalized:
            return
        self.conn.execute(
            """
            INSERT INTO zero_fee_symbols(symbol, enabled, updated_at)
            VALUES(?, ?, ?)
            ON CONFLICT(symbol) DO UPDATE SET
              enabled=excluded.enabled,
              updated_at=excluded.updated_at
            """,
            (normalized, int(enabled), _utc_now_iso()),
        )
        self.conn.commit()

    def import_zero_fee_symbols(self, symbols: list[str]) -> None:
        payload = [
            (symbol.strip().upper(), 1, _utc_now_iso())
            for symbol in symbols
            if symbol and symbol.strip()
        ]
        if not payload:
            return
        self.conn.executemany(
            """
            INSERT INTO zero_fee_symbols(symbol, enabled, updated_at)
            VALUES(?, ?, ?)
            ON CONFLICT(symbol) DO UPDATE SET
              enabled=excluded.enabled,
              updated_at=excluded.updated_at
            """,
            payload,
        )
        self.conn.commit()
