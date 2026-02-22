from __future__ import annotations

from PyQt5.QtCore import QThread, pyqtSignal
from PyQt5.QtWidgets import (
    QHBoxLayout,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app.core.engine import TradingEngine
from app.core.logger import logger
from app.core.storage import Storage
from app.gui.tabs.api_tab import ApiTab
from app.gui.tabs.logs_tab import LogsTab
from app.gui.tabs.pairs_tab import PairsTab
from app.gui.tabs.risk_orders_tab import RiskOrdersTab
from app.gui.tabs.stats_tab import StatsTab
from app.gui.tabs.strategy_tab import StrategyTab


class EngineActionThread(QThread):
    done = pyqtSignal(bool, str)

    def __init__(self, action: str, engine: TradingEngine) -> None:
        super().__init__()
        self.action = action
        self.engine = engine

    def run(self) -> None:
        try:
            if self.action == "start":
                self.engine.start()
            elif self.action == "stop":
                self.engine.stop()
            self.done.emit(True, "")
        except Exception as exc:
            logger.exception(f"Engine action failed: {self.action}")
            self.done.emit(False, str(exc))
        finally:
            self.engine.storage.close_thread_connection()


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Futures Flipper GUI")
        self.resize(1000, 700)

        self.storage = Storage()
        self.engine = TradingEngine(self.storage)
        self._engine_action_thread: EngineActionThread | None = None

        self.tabs = QTabWidget()
        self.tabs.addTab(ApiTab(), "API")
        self.tabs.addTab(PairsTab(), "Pairs")
        self.tabs.addTab(StrategyTab(), "Strategy")
        self.tabs.addTab(RiskOrdersTab(), "Risk & Orders")
        self.tabs.addTab(StatsTab(), "Stats")
        self.tabs.addTab(LogsTab(), "Logs")

        self.start_btn = QPushButton("Start Trading")
        self.start_btn.clicked.connect(self.on_start_trading)

        self.stop_btn = QPushButton("Stop Trading")
        self.stop_btn.clicked.connect(self.on_stop_trading)
        self.stop_btn.setEnabled(False)

        self.cancel_orders_btn = QPushButton("Cancel All Open Orders")
        self.cancel_orders_btn.clicked.connect(self.on_cancel_all_orders)

        self.panic_stop_btn = QPushButton("Panic Stop")
        self.panic_stop_btn.clicked.connect(self.on_panic_stop)

        controls_layout = QHBoxLayout()
        controls_layout.addWidget(self.start_btn)
        controls_layout.addWidget(self.stop_btn)
        controls_layout.addWidget(self.cancel_orders_btn)
        controls_layout.addWidget(self.panic_stop_btn)
        controls_layout.addStretch(1)

        central = QWidget()
        root = QVBoxLayout()
        root.addLayout(controls_layout)
        root.addWidget(self.tabs)
        central.setLayout(root)
        self.setCentralWidget(central)

    def on_start_trading(self) -> None:
        self._run_engine_action("start")

    def on_stop_trading(self) -> None:
        self._run_engine_action("stop")

    def _run_engine_action(self, action: str) -> None:
        if self._engine_action_thread and self._engine_action_thread.isRunning():
            return

        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(False)

        self._engine_action_thread = EngineActionThread(action=action, engine=self.engine)
        self._engine_action_thread.done.connect(lambda ok, msg: self._on_engine_action_done(action, ok, msg))
        self._engine_action_thread.finished.connect(self._engine_action_thread.deleteLater)
        self._engine_action_thread.start()

    def _on_engine_action_done(self, action: str, ok: bool, error: str) -> None:
        if not ok:
            QMessageBox.critical(self, "Engine Error", f"Failed to {action} engine: {error}")

        running = self.engine.is_running()
        self.start_btn.setEnabled(not running)
        self.stop_btn.setEnabled(running)

    def on_cancel_all_orders(self) -> None:
        if not self._confirm_action(
            "Cancel All Open Orders",
            "Cancel all open exchange orders?",
        ):
            return

        canceled = self.engine.cancel_all_open_orders()
        QMessageBox.information(
            self,
            "Done",
            f"Canceled open orders: {canceled}",
        )

    def on_panic_stop(self) -> None:
        if not self._confirm_action(
            "Panic Stop",
            "Panic stop will stop engine and cancel all open orders. Continue?",
        ):
            return

        self.engine.panic_stop()
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        QMessageBox.warning(self, "Panic Stop", "Panic stop executed.")

    def closeEvent(self, event) -> None:  # type: ignore[override]
        if self._engine_action_thread and self._engine_action_thread.isRunning():
            self._engine_action_thread.wait(3000)

        self.engine.stop()
        self.storage.close_thread_connection()
        event.accept()

    def _confirm_action(self, title: str, text: str) -> bool:
        reply = QMessageBox.question(
            self,
            title,
            text,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        return reply == QMessageBox.Yes
