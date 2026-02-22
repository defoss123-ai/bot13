from PyQt5.QtWidgets import QLabel, QVBoxLayout, QWidget


class StatsTab(QWidget):
    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout()
        layout.addWidget(QLabel("Stats tab (placeholder)"))
        self.setLayout(layout)
