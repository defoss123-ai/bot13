from __future__ import annotations

from collections import deque
from pathlib import Path

from PyQt5.QtCore import QTimer
from PyQt5.QtGui import QTextCursor
from PyQt5.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QPushButton, QTextEdit, QVBoxLayout, QWidget


class LogsTab(QWidget):
    def __init__(self) -> None:
        super().__init__()

        self.log_file = Path(__file__).resolve().parents[3] / "logs" / "app.log"
        self.max_lines = 800

        root = QVBoxLayout()

        controls = QHBoxLayout()
        controls.addWidget(QLabel("Filter:"))
        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("type text to filter logs...")
        controls.addWidget(self.filter_edit)

        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.clicked.connect(self.refresh_logs)
        controls.addWidget(self.refresh_btn)

        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)

        root.addLayout(controls)
        root.addWidget(self.log_view)
        self.setLayout(root)

        self.filter_edit.textChanged.connect(self.refresh_logs)

        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self.refresh_logs)
        self.timer.start()

        self.refresh_logs()

    def refresh_logs(self) -> None:
        if not self.log_file.exists():
            self.log_view.setPlainText("No logs yet. File logs/app.log not found.")
            return

        try:
            with self.log_file.open("r", encoding="utf-8", errors="ignore") as f:
                last_lines = deque(f, maxlen=self.max_lines)
        except Exception as exc:
            self.log_view.setPlainText(f"Failed to read log file: {exc}")
            return

        text_filter = self.filter_edit.text().strip().lower()
        if text_filter:
            lines = [line for line in last_lines if text_filter in line.lower()]
        else:
            lines = list(last_lines)

        self.log_view.setPlainText("".join(lines))
        cursor = self.log_view.textCursor()
        cursor.movePosition(QTextCursor.End)
        self.log_view.setTextCursor(cursor)
