from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app.core.logger import logger
from app.core.storage import Storage


class RiskOrdersTab(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.storage = Storage()

        root = QVBoxLayout()
        root.addWidget(QLabel("Risk and Orders settings"))

        risk_box = QGroupBox("Risk")
        risk_form = QFormLayout()

        self.max_positions_spin = QSpinBox()
        self.max_positions_spin.setMinimum(1)
        self.max_positions_spin.setMaximum(999)
        self.allow_all_positions_check = QCheckBox("allow_all_positions")
        self.allow_all_positions_check.stateChanged.connect(self._toggle_max_positions)

        max_pos_row = QHBoxLayout()
        max_pos_row.addWidget(self.max_positions_spin)
        max_pos_row.addWidget(self.allow_all_positions_check)

        self.sizing_mode_combo = QComboBox()
        self.sizing_mode_combo.addItems(["percent", "fixed", "full"])

        self.sizing_percent_spin = QDoubleSpinBox()
        self.sizing_percent_spin.setRange(0.01, 1000.0)
        self.sizing_percent_spin.setDecimals(2)

        self.sizing_fixed_usdt_spin = QDoubleSpinBox()
        self.sizing_fixed_usdt_spin.setRange(0.01, 1_000_000.0)
        self.sizing_fixed_usdt_spin.setDecimals(2)

        self.sizing_reserve_usdt_spin = QDoubleSpinBox()
        self.sizing_reserve_usdt_spin.setRange(0.0, 1_000_000.0)
        self.sizing_reserve_usdt_spin.setDecimals(2)

        self.max_margin_per_trade_usdt_spin = QDoubleSpinBox()
        self.max_margin_per_trade_usdt_spin.setRange(0.01, 1_000_000.0)
        self.max_margin_per_trade_usdt_spin.setDecimals(2)

        self.daily_loss_limit_pct_spin = QDoubleSpinBox()
        self.daily_loss_limit_pct_spin.setRange(0.01, 100.0)
        self.daily_loss_limit_pct_spin.setDecimals(2)

        risk_form.addRow("max_concurrent_positions", max_pos_row)
        risk_form.addRow("sizing_mode", self.sizing_mode_combo)
        risk_form.addRow("sizing_percent", self.sizing_percent_spin)
        risk_form.addRow("sizing_fixed_usdt", self.sizing_fixed_usdt_spin)
        risk_form.addRow("sizing_reserve_usdt", self.sizing_reserve_usdt_spin)
        risk_form.addRow("max_margin_per_trade_usdt", self.max_margin_per_trade_usdt_spin)
        risk_form.addRow("daily_loss_limit_pct", self.daily_loss_limit_pct_spin)
        risk_box.setLayout(risk_form)

        orders_box = QGroupBox("Orders")
        orders_form = QFormLayout()

        self.entry_order_type_combo = QComboBox()
        self.entry_order_type_combo.addItems(["market", "limit"])

        self.exit_order_type_combo = QComboBox()
        self.exit_order_type_combo.addItems(["market", "limit"])

        self.limit_offset_bps_spin = QSpinBox()
        self.limit_offset_bps_spin.setRange(0, 100_000)

        self.entry_timeout_sec_spin = QSpinBox()
        self.entry_timeout_sec_spin.setRange(1, 86_400)

        self.entry_retry_count_spin = QSpinBox()
        self.entry_retry_count_spin.setRange(0, 1_000)

        self.allow_market_fallback_check = QCheckBox()

        self.min_fill_pct_spin = QDoubleSpinBox()
        self.min_fill_pct_spin.setRange(0.01, 100.0)
        self.min_fill_pct_spin.setDecimals(2)

        orders_form.addRow("entry_order_type", self.entry_order_type_combo)
        orders_form.addRow("exit_order_type", self.exit_order_type_combo)
        orders_form.addRow("limit_offset_bps", self.limit_offset_bps_spin)
        orders_form.addRow("entry_timeout_sec", self.entry_timeout_sec_spin)
        orders_form.addRow("entry_retry_count", self.entry_retry_count_spin)
        orders_form.addRow("allow_market_fallback", self.allow_market_fallback_check)
        orders_form.addRow("min_fill_pct", self.min_fill_pct_spin)
        orders_box.setLayout(orders_form)

        self.save_btn = QPushButton("Save")
        self.save_btn.clicked.connect(self.on_save)

        root.addWidget(risk_box)
        root.addWidget(orders_box)
        root.addWidget(self.save_btn, alignment=Qt.AlignLeft)
        root.addStretch(1)
        self.setLayout(root)

        self.load_settings()

    def _toggle_max_positions(self) -> None:
        self.max_positions_spin.setEnabled(not self.allow_all_positions_check.isChecked())

    def _get_setting(self, key: str, default: str) -> str:
        return self.storage.get_setting(key, default) or default

    def load_settings(self) -> None:
        max_positions_value = self._get_setting("max_concurrent_positions", "1")
        if max_positions_value.upper() == "ALL":
            self.allow_all_positions_check.setChecked(True)
            self.max_positions_spin.setValue(1)
        else:
            self.allow_all_positions_check.setChecked(False)
            self.max_positions_spin.setValue(max(1, int(max_positions_value)))
        self._toggle_max_positions()

        self.sizing_mode_combo.setCurrentText(self._get_setting("sizing_mode", "percent"))
        self.sizing_percent_spin.setValue(float(self._get_setting("sizing_percent", "10")))
        self.sizing_fixed_usdt_spin.setValue(float(self._get_setting("sizing_fixed_usdt", "20")))
        self.sizing_reserve_usdt_spin.setValue(float(self._get_setting("sizing_reserve_usdt", "10")))
        self.max_margin_per_trade_usdt_spin.setValue(
            float(self._get_setting("max_margin_per_trade_usdt", "200"))
        )
        self.daily_loss_limit_pct_spin.setValue(float(self._get_setting("daily_loss_limit_pct", "3.0")))

        self.entry_order_type_combo.setCurrentText(self._get_setting("entry_order_type", "market"))
        self.exit_order_type_combo.setCurrentText(self._get_setting("exit_order_type", "market"))
        self.limit_offset_bps_spin.setValue(int(self._get_setting("limit_offset_bps", "2")))
        self.entry_timeout_sec_spin.setValue(int(self._get_setting("entry_timeout_sec", "30")))
        self.entry_retry_count_spin.setValue(int(self._get_setting("entry_retry_count", "0")))
        self.allow_market_fallback_check.setChecked(
            self._get_setting("allow_market_fallback", "0") == "1"
        )
        self.min_fill_pct_spin.setValue(float(self._get_setting("min_fill_pct", "80")))

    def on_save(self) -> None:
        max_positions = "ALL" if self.allow_all_positions_check.isChecked() else str(self.max_positions_spin.value())

        self.storage.set_setting("max_concurrent_positions", max_positions)
        self.storage.set_setting("sizing_mode", self.sizing_mode_combo.currentText())
        self.storage.set_setting("sizing_percent", self.sizing_percent_spin.value())
        self.storage.set_setting("sizing_fixed_usdt", self.sizing_fixed_usdt_spin.value())
        self.storage.set_setting("sizing_reserve_usdt", self.sizing_reserve_usdt_spin.value())
        self.storage.set_setting(
            "max_margin_per_trade_usdt", self.max_margin_per_trade_usdt_spin.value()
        )
        self.storage.set_setting("daily_loss_limit_pct", self.daily_loss_limit_pct_spin.value())

        self.storage.set_setting("entry_order_type", self.entry_order_type_combo.currentText())
        self.storage.set_setting("exit_order_type", self.exit_order_type_combo.currentText())
        self.storage.set_setting("limit_offset_bps", self.limit_offset_bps_spin.value())
        self.storage.set_setting("entry_timeout_sec", self.entry_timeout_sec_spin.value())
        self.storage.set_setting("entry_retry_count", self.entry_retry_count_spin.value())
        self.storage.set_setting(
            "allow_market_fallback", 1 if self.allow_market_fallback_check.isChecked() else 0
        )
        self.storage.set_setting("min_fill_pct", self.min_fill_pct_spin.value())

        logger.info("Risk/Orders settings saved")
        QMessageBox.information(self, "Saved", "Risk/Orders settings saved.")
