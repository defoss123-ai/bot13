from pathlib import Path

from loguru import logger


LOG_DIR = Path(__file__).resolve().parents[2] / "logs"
LOG_FILE = LOG_DIR / "app.log"


def setup_logger() -> None:
    """Configure application logging to console and file."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    logger.remove()
    logger.add(lambda msg: print(msg, end=""), level="INFO")
    logger.add(LOG_FILE, level="INFO", rotation="5 MB", enqueue=False)


__all__ = ["logger", "setup_logger"]
