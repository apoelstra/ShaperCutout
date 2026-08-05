# SPDX-License-Identifier: GPL-3.0-or-later

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore, QtGui, QtWidgets

from .model import ReportTableModel, ReportTableWidget
from shaper_cutout_util import make_expr_template, parent_cutout


class DadosModel(ReportTableModel):
    def __init__(self, dados=None):
        def parent_label(dados):
            parent = parent_cutout(dados, 'Dados')
            return parent.Label if parent else '<no parent>'

        super().__init__([
            ("Name", lambda dado: dado.Label),
            ("Cutout", parent_label),
            ("Width", lambda dado: dado.Width),
            ("Depth", lambda dado: dado.Depth),
            ("Tolerance", lambda dado: dado.Tolerance),
        ])


class ReportViewDados(QtGui.QWidget):
    def __init__(self, report_section):
        self._doc = App.ActiveDocument
        self._report_section = report_section

        super().__init__()
        self.initUi()

    def initUi(self):
        self.setWindowTitle("Dados")
        layout = QtWidgets.QVBoxLayout(self)

        # Dados section
        self._table = ReportTableWidget(DadosModel())

        # Buttons
        button_layout = QtWidgets.QVBoxLayout()

        # Update data row
        self.width_widget = Gui.UiLoader().createWidget('Gui::QuantitySpinBox')
        self.width_widget.setProperty('minimum', 1e-7)
        self.width_widget.setEnabled(False)
        self.depth_widget = Gui.UiLoader().createWidget('Gui::QuantitySpinBox')
        self.depth_widget.setProperty('minimum', 0)
        self.depth_widget.setEnabled(False)
        self.tolerance_widget = Gui.UiLoader().createWidget('Gui::QuantitySpinBox')
        self.tolerance_widget.setProperty('minimum', 0)
        self.tolerance_widget.setEnabled(False)
        self._template = make_expr_template({
            'Width': 'App::PropertyLength',
            'Depth': 'App::PropertyLength',
            'Tolerance': 'App::PropertyLength',
        })
        self._template.bind(self.width_widget, 'Width', 25.4)  # arbitrory nonzero value
        self._template.bind(self.depth_widget, 'Depth', 0)
        self._template.bind(self.tolerance_widget, 'Tolerance', 0)

        # Width row
        self.width_apply_btn = QtWidgets.QPushButton("Update Width")
        self.width_apply_btn.clicked.connect(self._on_apply_width)
        self.width_apply_btn.setEnabled(False)
        width_input_layout = QtWidgets.QVBoxLayout()
        width_input_layout.addWidget(self.width_widget)
        width_input_layout.addWidget(self.width_apply_btn)

        # Depth row
        self.depth_apply_btn = QtWidgets.QPushButton("Update Depth")
        self.depth_apply_btn.clicked.connect(self._on_apply_depth)
        self.depth_apply_btn.setEnabled(False)
        depth_input_layout = QtWidgets.QVBoxLayout()
        depth_input_layout.addWidget(self.depth_widget)
        depth_input_layout.addWidget(self.depth_apply_btn)

        # Tolerance row
        self.tolerance_apply_btn = QtWidgets.QPushButton("Update Tolerance")
        self.tolerance_apply_btn.clicked.connect(self._on_apply_tolerance)
        self.tolerance_apply_btn.setEnabled(False)
        tolerance_input_layout = QtWidgets.QVBoxLayout()
        tolerance_input_layout.addWidget(self.tolerance_widget)
        tolerance_input_layout.addWidget(self.tolerance_apply_btn)

        update_data_layout = QtWidgets.QFormLayout()
        update_data_layout.setFormAlignment(QtCore.Qt.AlignCenter)
        update_data_layout.setLabelAlignment(
            QtCore.Qt.AlignRight | QtCore.Qt.AlignTrailing | QtCore.Qt.AlignVCenter)
        update_data_layout.addRow("Width:", width_input_layout)
        update_data_layout.addRow("Depth:", depth_input_layout)
        update_data_layout.addRow("Tolerance:", tolerance_input_layout)
        button_layout.addLayout(update_data_layout)

        # Populate table
        dados = [obj for obj in self._doc.Objects
                 if getattr(obj, 'Type', '') == 'ShaperDados']
        self._table.populate(dados)

        layout.addWidget(self._table)
        layout.addLayout(button_layout)

        # Connect signals
        self._table.checkedStateChanged.connect(self._on_table_checked_state_changed)

    def _on_table_checked_state_changed(self, checked: [App.DocumentObject]):
        has_selection = len(checked) > 0
        self.width_widget.setEnabled(has_selection)
        self.depth_widget.setEnabled(has_selection)
        self.tolerance_widget.setEnabled(has_selection)
        self.width_apply_btn.setEnabled(has_selection)
        self.depth_apply_btn.setEnabled(has_selection)
        self.tolerance_apply_btn.setEnabled(has_selection)

    def _on_apply_width(self):
        selected = self._table.get_checked_objects()
        n = len(selected)
        for dados in selected:
            self._template.update_object(dados, 'Width')
            dados.recompute()
            dados.Proxy.parent_cutout(dados).recompute()
        self._table.refresh_display()
        self._report_section.replace_text(f"Updated width on {n} selected dados."
                                          "\n(Clicking 'Cancel' will undo this.)")

    def _on_apply_depth(self):
        selected = self._table.get_checked_objects()
        n = len(selected)
        for dados in selected:
            self._template.update_object(dados, 'Depth')
            dados.recompute()
            dados.Proxy.parent_cutout(dados).recompute()
        self._table.refresh_display()
        self._report_section.replace_text(f"Updated depth on {n} selected dados."
                                          "\n(Clicking 'Cancel' will undo this.)")

    def _on_apply_tolerance(self):
        selected = self._table.get_checked_objects()
        n = len(selected)
        for dados in selected:
            self._template.update_object(dados, 'Tolerance')
            dados.recompute()
        self._table.refresh_display()
        self._report_section.replace_text(f"Updated tolerance on {n} selected dados."
                                          "\n(Clicking 'Cancel' will undo this.)")
