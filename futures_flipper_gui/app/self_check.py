"""Small runtime self-check for core services without launching GUI."""

from __future__ import annotations

import time
import sys
from pathlib import Path

if __package__ is None or __package__ == "":
    sys.path.append(str(Path(__file__).resolve().parents[1]))


from app.core.engine import TradingEngine
from app.core.logger import setup_logger
from app.core.storage import Storage


def run_self_check() -> int:
    setup_logger()

    storage = Storage()
    storage.set_setting("self_check", "ok")
    assert storage.get_setting("self_check") == "ok"

    storage.set_setting("paper_mode", "1")
    engine = TradingEngine(storage)
    engine.start()
    time.sleep(1.5)
    engine.stop()

    storage.close_thread_connection()
    print("Self-check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(run_self_check())
