from PyQt5.QtWidgets import QLabel, QVBoxLayout, QWidget


class LogsTab(QWidget):
    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout()
        layout.addWidget(QLabel("Logs tab (placeholder)"))
        self.setLayout(layout)
