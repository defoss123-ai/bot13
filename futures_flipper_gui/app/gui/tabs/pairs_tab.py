from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QCheckBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.core.logger import logger
from app.core.storage import Storage


class PairsTab(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.storage = Storage()

        root = QVBoxLayout()
        root.addWidget(QLabel("Pairs configuration"))

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["symbol", "enabled", "leverage", "tp_pct", "sl_pct", "cooldown_sec"]
        )
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.itemSelectionChanged.connect(self._on_row_selected)

        form = QFormLayout()
        self.symbol_edit = QLineEdit()
        self.leverage_edit = QLineEdit()
        self.tp_pct_edit = QLineEdit()
        self.sl_pct_edit = QLineEdit()
        self.cooldown_edit = QLineEdit()
        self.enabled_check = QCheckBox("Enabled")
        self.enabled_check.setChecked(True)

        form.addRow("Symbol", self.symbol_edit)
        form.addRow("Enabled", self.enabled_check)
        form.addRow("Leverage", self.leverage_edit)
        form.addRow("TP %", self.tp_pct_edit)
        form.addRow("SL %", self.sl_pct_edit)
        form.addRow("Cooldown (sec)", self.cooldown_edit)

        buttons = QHBoxLayout()
        self.add_btn = QPushButton("Add")
        self.save_btn = QPushButton("Update/Save")
        self.delete_btn = QPushButton("Delete")
        buttons.addWidget(self.add_btn)
        buttons.addWidget(self.save_btn)
        buttons.addWidget(self.delete_btn)

        self.add_btn.clicked.connect(self.on_add)
        self.save_btn.clicked.connect(self.on_save)
        self.delete_btn.clicked.connect(self.on_delete)

        root.addWidget(self.table)
        root.addLayout(form)
        root.addLayout(buttons)
        self.setLayout(root)

        self.refresh_table()

    def _settings_default(self, key: str, fallback: str) -> str:
        return self.storage.get_setting(key, fallback) or fallback

    def _normalize_symbol(self, value: str) -> str:
        symbol = value.strip().upper()
        if not symbol:
            return ""
        if "/" not in symbol and symbol.endswith("USDT") and len(symbol) > 4:
            return f"{symbol[:-4]}/USDT"
        return symbol

    def _validate_inputs(self) -> tuple[str, int, int, float, float, int] | None:
        symbol = self._normalize_symbol(self.symbol_edit.text())
        if not symbol:
            QMessageBox.warning(self, "Validation", "Symbol must not be empty.")
            return None

        try:
            enabled = 1 if self.enabled_check.isChecked() else 0
            leverage = int(self.leverage_edit.text().strip())
            tp_pct = float(self.tp_pct_edit.text().strip())
            sl_pct = float(self.sl_pct_edit.text().strip())
            cooldown_sec = int(self.cooldown_edit.text().strip())
        except ValueError:
            QMessageBox.warning(self, "Validation", "Invalid numeric value in fields.")
            return None

        if leverage <= 0:
            QMessageBox.warning(self, "Validation", "Leverage must be > 0.")
            return None
        if tp_pct <= 0 or sl_pct <= 0:
            QMessageBox.warning(self, "Validation", "TP and SL must be > 0.")
            return None
        return symbol, enabled, leverage, tp_pct, sl_pct, cooldown_sec

    def refresh_table(self) -> None:
        pairs = self.storage.list_pairs()
        self.table.setRowCount(len(pairs))

        for row_idx, row in enumerate(pairs):
            symbol_item = QTableWidgetItem(str(row.get("symbol", "")))
            symbol_item.setFlags(symbol_item.flags() & ~Qt.ItemIsEditable)

            enabled_item = QTableWidgetItem("")
            enabled_item.setFlags(enabled_item.flags() & ~Qt.ItemIsEditable)
            enabled_item.setCheckState(Qt.Checked if int(row.get("enabled", 0)) else Qt.Unchecked)

            leverage_item = QTableWidgetItem(str(row.get("leverage", "")))
            leverage_item.setFlags(leverage_item.flags() & ~Qt.ItemIsEditable)

            tp_item = QTableWidgetItem(str(row.get("tp_pct", "")))
            tp_item.setFlags(tp_item.flags() & ~Qt.ItemIsEditable)

            sl_item = QTableWidgetItem(str(row.get("sl_pct", "")))
            sl_item.setFlags(sl_item.flags() & ~Qt.ItemIsEditable)

            cooldown_item = QTableWidgetItem(str(row.get("cooldown_sec", "")))
            cooldown_item.setFlags(cooldown_item.flags() & ~Qt.ItemIsEditable)

            self.table.setItem(row_idx, 0, symbol_item)
            self.table.setItem(row_idx, 1, enabled_item)
            self.table.setItem(row_idx, 2, leverage_item)
            self.table.setItem(row_idx, 3, tp_item)
            self.table.setItem(row_idx, 4, sl_item)
            self.table.setItem(row_idx, 5, cooldown_item)

        self.table.resizeColumnsToContents()

    def _on_row_selected(self) -> None:
        row = self.table.currentRow()
        if row < 0:
            return

        self.symbol_edit.setText(self.table.item(row, 0).text())
        self.enabled_check.setChecked(self.table.item(row, 1).checkState() == Qt.Checked)
        self.leverage_edit.setText(self.table.item(row, 2).text())
        self.tp_pct_edit.setText(self.table.item(row, 3).text())
        self.sl_pct_edit.setText(self.table.item(row, 4).text())
        self.cooldown_edit.setText(self.table.item(row, 5).text())

    def on_add(self) -> None:
        symbol = self._normalize_symbol(self.symbol_edit.text())
        if not symbol:
            QMessageBox.warning(self, "Validation", "Symbol must not be empty.")
            return

        default_leverage = int(self._settings_default("default_leverage", "5"))
        default_tp = float(self._settings_default("ultra_tp_pct", "0.12"))
        default_sl = float(self._settings_default("ultra_sl_pct", "0.25"))
        default_cooldown = int(self._settings_default("check_interval_sec", "5"))

        self.storage.upsert_pair(
            symbol=symbol,
            leverage=default_leverage,
            tp_pct=default_tp,
            sl_pct=default_sl,
            enabled=1,
            cooldown_sec=default_cooldown,
        )

        logger.info(f"Pair added {symbol}")
        self.refresh_table()

    def on_save(self) -> None:
        validated = self._validate_inputs()
        if not validated:
            return

        symbol, enabled, leverage, tp_pct, sl_pct, cooldown_sec = validated
        self.storage.upsert_pair(
            symbol=symbol,
            leverage=leverage,
            tp_pct=tp_pct,
            sl_pct=sl_pct,
            enabled=enabled,
            cooldown_sec=cooldown_sec,
        )

        logger.info(f"Pair updated {symbol}")
        self.refresh_table()

    def on_delete(self) -> None:
        symbol = self._normalize_symbol(self.symbol_edit.text())
        if not symbol:
            QMessageBox.warning(self, "Validation", "Select or enter a symbol to delete.")
            return

        self.storage.delete_pair(symbol)
        logger.info(f"Pair deleted {symbol}")
        self.refresh_table()
