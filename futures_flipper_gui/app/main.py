import sys
from pathlib import Path

if __package__ is None or __package__ == "":
    sys.path.append(str(Path(__file__).resolve().parents[1]))

from PyQt5.QtWidgets import QApplication

from app.core.logger import logger, setup_logger
from app.core.storage import init_db
from app.gui.main_window import MainWindow


def main() -> int:
    setup_logger()
    db_conn = init_db()
    logger.info("Database initialized")
    db_conn.close()

    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec_()


if __name__ == "__main__":
    raise SystemExit(main())
