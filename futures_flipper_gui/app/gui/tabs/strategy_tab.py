from __future__ import annotations

from typing import Any

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app.core.logger import logger
from app.core.storage import Storage
from app.strategies.builder import BlockConfig, StrategyConfig, default_config, load_config, save_config


class BlockEditor(QWidget):
    def __init__(self, block_name: str, block_config: BlockConfig) -> None:
        super().__init__()
        self.block_name = block_name
        self.param_widgets: dict[str, QWidget] = {}
        self.param_types: dict[str, type[Any]] = {}

        root = QVBoxLayout()
        root.setContentsMargins(8, 8, 8, 8)

        title_row = QHBoxLayout()
        title = QLabel(block_name)
        title.setStyleSheet("font-weight: 600;")

        self.enabled_check = QCheckBox("Enabled")
        self.enabled_check.setChecked(bool(block_config.enabled))

        self.weight_label = QLabel("Weight:")
        self.weight_spin = QSpinBox()
        self.weight_spin.setRange(0, 999)
        self.weight_spin.setValue(int(block_config.weight))
        self.weight_spin.setFixedWidth(80)

        title_row.addWidget(title)
        title_row.addStretch(1)
        title_row.addWidget(self.enabled_check)
        title_row.addWidget(self.weight_label)
        title_row.addWidget(self.weight_spin)

        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(4)

        for key, value in block_config.params.items():
            widget: QWidget
            self.param_types[key] = type(value)

            if isinstance(value, bool):
                cb = QCheckBox()
                cb.setChecked(value)
                widget = cb
            else:
                edit = QLineEdit(str(value))
                edit.setMaximumWidth(120)
                widget = edit

            self.param_widgets[key] = widget
            form.addRow(key, widget)

        frame = QFrame()
        frame.setFrameShape(QFrame.StyledPanel)
        frame.setLayout(form)

        root.addLayout(title_row)
        root.addWidget(frame)
        self.setLayout(root)

    def set_score_mode(self, is_score_mode: bool) -> None:
        self.weight_label.setVisible(is_score_mode)
        self.weight_spin.setVisible(is_score_mode)

    def to_block_config(self) -> BlockConfig:
        params: dict[str, Any] = {}

        for key, widget in self.param_widgets.items():
            raw_type = self.param_types.get(key, str)
            if isinstance(widget, QCheckBox):
                params[key] = widget.isChecked()
                continue

            if not isinstance(widget, QLineEdit):
                continue

            text = widget.text().strip()
            if raw_type is int:
                try:
                    params[key] = int(text)
                except ValueError as exc:
                    raise ValueError(f"{self.block_name}.{key} must be an integer") from exc
            elif raw_type is float:
                try:
                    params[key] = float(text)
                except ValueError as exc:
                    raise ValueError(f"{self.block_name}.{key} must be a number") from exc
            elif raw_type is bool:
                params[key] = text.lower() in ("1", "true", "yes", "on")
            else:
                params[key] = text

        return BlockConfig(
            enabled=self.enabled_check.isChecked(),
            weight=self.weight_spin.value(),
            params=params,
        )


class StrategyTab(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.storage = Storage()
        self.block_editors: dict[str, BlockEditor] = {}

        root = QVBoxLayout()
        root.setContentsMargins(8, 8, 8, 8)

        top_row = QHBoxLayout()
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["AND", "SCORE"])
        self.mode_combo.currentTextChanged.connect(self._on_mode_changed)

        self.min_score_spin = QSpinBox()
        self.min_score_spin.setRange(1, 999)
        self.min_score_spin.setValue(1)
        self.min_score_label = QLabel("Min score")

        top_row.addWidget(QLabel("Mode"))
        top_row.addWidget(self.mode_combo)
        top_row.addSpacing(12)
        top_row.addWidget(self.min_score_label)
        top_row.addWidget(self.min_score_spin)
        top_row.addStretch(1)

        self.blocks_container = QWidget()
        self.blocks_layout = QVBoxLayout()
        self.blocks_layout.setContentsMargins(0, 0, 0, 0)
        self.blocks_layout.setSpacing(6)
        self.blocks_container.setLayout(self.blocks_layout)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.blocks_container)

        buttons = QHBoxLayout()
        self.save_btn = QPushButton("Save")
        self.reset_btn = QPushButton("Reset to default")
        self.save_btn.clicked.connect(self.on_save)
        self.reset_btn.clicked.connect(self.on_reset)
        buttons.addWidget(self.save_btn)
        buttons.addWidget(self.reset_btn)
        buttons.addStretch(1)

        root.addLayout(top_row)
        root.addWidget(scroll)
        root.addLayout(buttons)
        self.setLayout(root)

        self._load_from_storage()

    def _clear_blocks(self) -> None:
        while self.blocks_layout.count():
            item = self.blocks_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self.block_editors.clear()

    def _render_blocks(self, config: StrategyConfig) -> None:
        self._clear_blocks()

        for block_name, block_cfg in config.enabled_blocks.items():
            editor = BlockEditor(block_name, block_cfg)
            self.block_editors[block_name] = editor
            self.blocks_layout.addWidget(editor)

        self.blocks_layout.addStretch(1)
        self._sync_mode_ui()

    def _sync_mode_ui(self) -> None:
        is_score_mode = self.mode_combo.currentText() == "SCORE"
        self.min_score_spin.setVisible(is_score_mode)
        self.min_score_label.setVisible(is_score_mode)

        for editor in self.block_editors.values():
            editor.set_score_mode(is_score_mode)

    def _on_mode_changed(self) -> None:
        self._sync_mode_ui()

    def _load_from_storage(self) -> None:
        config = load_config(self.storage)
        self.mode_combo.setCurrentText(config.mode.upper())
        self.min_score_spin.setValue(max(1, int(config.min_score)))
        self._render_blocks(config)

    def _build_config_from_ui(self) -> StrategyConfig:
        mode = self.mode_combo.currentText().lower()
        min_score = self.min_score_spin.value()

        blocks: dict[str, BlockConfig] = {}
        for name, editor in self.block_editors.items():
            blocks[name] = editor.to_block_config()

        return StrategyConfig(mode=mode, min_score=min_score, enabled_blocks=blocks)

    def on_save(self) -> None:
        try:
            config = self._build_config_from_ui()
        except ValueError as exc:
            QMessageBox.warning(self, "Validation", str(exc))
            return

        save_config(self.storage, config)
        logger.info("Strategy config saved")
        QMessageBox.information(self, "Saved", "Strategy configuration saved.")

    def on_reset(self) -> None:
        config = default_config()
        save_config(self.storage, config)
        self.mode_combo.setCurrentText(config.mode.upper())
        self.min_score_spin.setValue(config.min_score)
        self._render_blocks(config)
        logger.info("Strategy config reset to default")
        QMessageBox.information(self, "Reset", "Strategy configuration reset to default.")
