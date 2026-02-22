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
from app.core.storage import Storage
from app.gui.tabs.api_tab import ApiTab
from app.gui.tabs.logs_tab import LogsTab
from app.gui.tabs.pairs_tab import PairsTab
from app.gui.tabs.risk_orders_tab import RiskOrdersTab
from app.gui.tabs.stats_tab import StatsTab
from app.gui.tabs.strategy_tab import StrategyTab


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Futures Flipper GUI")
        self.resize(1000, 700)

        self.storage = Storage()
        self.engine = TradingEngine(self.storage)

        self.tabs = QTabWidget()
        self.tabs.addTab(ApiTab(), "API")
        self.tabs.addTab(PairsTab(), "Pairs")
        self.tabs.addTab(StrategyTab(), "Strategy")
        self.tabs.addTab(RiskOrdersTab(), "Risk & Orders")
        self.tabs.addTab(StatsTab(), "Stats")
        self.tabs.addTab(LogsTab(), "Logs")

        self.cancel_orders_btn = QPushButton("Cancel All Open Orders")
        self.cancel_orders_btn.clicked.connect(self.on_cancel_all_orders)

        self.panic_stop_btn = QPushButton("Panic Stop")
        self.panic_stop_btn.clicked.connect(self.on_panic_stop)

        controls_layout = QHBoxLayout()
        controls_layout.addWidget(self.cancel_orders_btn)
        controls_layout.addWidget(self.panic_stop_btn)
        controls_layout.addStretch(1)

        central = QWidget()
        root = QVBoxLayout()
        root.addLayout(controls_layout)
        root.addWidget(self.tabs)
        central.setLayout(root)
        self.setCentralWidget(central)

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
        QMessageBox.warning(self, "Panic Stop", "Panic stop executed.")

    def _confirm_action(self, title: str, text: str) -> bool:
        reply = QMessageBox.question(
            self,
            title,
            text,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        return reply == QMessageBox.Yes
