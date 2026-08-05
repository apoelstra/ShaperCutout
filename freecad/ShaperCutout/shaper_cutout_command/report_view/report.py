# SPDX-License-Identifier: GPL-3.0-or-later

from PySide import QtGui, QtWidgets


class ReportViewReport(QtGui.QWidget):
    def __init__(self):
        super().__init__()
        self.initUi()

    def initUi(self):
        self.setWindowTitle("ShaperCutout Report")
        layout = QtWidgets.QVBoxLayout(self)
        self.report_text = QtWidgets.QTextEdit()
        self.report_text.setReadOnly(True)
        self.report_text.setText("Nothing to report.")
        layout.addWidget(self.report_text)

    def replace_text(self, text: str):
        self.report_text.setText(text)
