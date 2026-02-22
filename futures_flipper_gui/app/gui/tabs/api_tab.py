from PyQt5.QtWidgets import (
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.core.logger import logger
from app.exchange.mexc_swap import MexcSwapClient
from app.core.storage import Storage


class ApiTab(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.storage = Storage()

        root_layout = QVBoxLayout()
        form = QFormLayout()

        self.exchange_combo = QComboBox()
        self.exchange_combo.addItems(["MEXC"])
        self.exchange_combo.setEnabled(False)

        self.api_key_edit = QLineEdit()
        self.api_key_edit.setPlaceholderText("Enter API Key")

        self.api_secret_edit = QLineEdit()
        self.api_secret_edit.setPlaceholderText("Enter API Secret")
        self.api_secret_edit.setEchoMode(QLineEdit.Password)

        form.addRow("Exchange", self.exchange_combo)
        form.addRow("API Key", self.api_key_edit)
        form.addRow("API Secret", self.api_secret_edit)

        buttons_layout = QHBoxLayout()
        self.save_btn = QPushButton("Save")
        self.test_btn = QPushButton("Test Connection")
        buttons_layout.addWidget(self.save_btn)
        buttons_layout.addWidget(self.test_btn)

        root_layout.addWidget(QLabel("Exchange API credentials"))
        root_layout.addLayout(form)
        root_layout.addLayout(buttons_layout)
        root_layout.addStretch(1)
        self.setLayout(root_layout)

        self.save_btn.clicked.connect(self.on_save)
        self.test_btn.clicked.connect(self.on_test_connection)

        self._load_saved_keys()

    def _load_saved_keys(self) -> None:
        saved = self.storage.get_api_keys("MEXC")
        if not saved:
            return
        self.api_key_edit.setText(saved.get("api_key", ""))
        self.api_secret_edit.setText(saved.get("api_secret", ""))

    def on_save(self) -> None:
        api_key = self.api_key_edit.text().strip()
        api_secret = self.api_secret_edit.text().strip()

        if not api_key or not api_secret:
            QMessageBox.warning(self, "Validation", "API Key and API Secret are required.")
            return

        self.storage.set_api_keys("MEXC", api_key, api_secret)
        logger.info("API keys updated for exchange MEXC")
        QMessageBox.information(self, "Saved", "API credentials saved.")

    def on_test_connection(self) -> None:
        api_key = self.api_key_edit.text().strip()
        api_secret = self.api_secret_edit.text().strip()

        client = MexcSwapClient(api_key=api_key, api_secret=api_secret)

        try:
            ok = client.healthcheck()
        except Exception:
            logger.exception("MEXC healthcheck failed")
            QMessageBox.critical(self, "Connection Error", "MEXC connection test failed.")
            return

        if ok:
            logger.info("MEXC healthcheck succeeded")
            QMessageBox.information(self, "Connection OK", "MEXC connection test succeeded.")
        else:
            logger.warning("MEXC healthcheck failed")
            QMessageBox.warning(self, "Connection Error", "MEXC connection test failed.")
