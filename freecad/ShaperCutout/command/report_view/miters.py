# SPDX-License-Identifier: GPL-3.0-or-later

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore, QtGui, QtWidgets

from command.report_view.model import ReportTableModel, ReportTableWidget
from shaper_cutout_util import make_expr_template, parent_cutout


class MiterModel(ReportTableModel):
    def __init__(self, miters=None):
        def parent_label(miter):
            parent = parent_cutout(miter, 'Miters')
            return parent.Label if parent else '<no parent>'

        super().__init__([
            ("Name", lambda miter: miter.Label),
            ("Cutout", parent_label),
            ("Number of Edges", lambda miter: len(miter.Edges)),
            ("Angle", lambda miter: miter.Angle),
        ])


class ReportViewMiter(QtGui.QWidget):
    def __init__(self, report_section):
        self._doc = App.ActiveDocument
        self._report_section = report_section

        super().__init__()
        self.initUi()

    def initUi(self):
        self.setWindowTitle("Miters")
        layout = QtWidgets.QVBoxLayout(self)

        # Miter section
        self._table = ReportTableWidget(MiterModel())

        # Buttons
        button_layout = QtWidgets.QVBoxLayout()

        # Update data row
        self.angle_widget = Gui.UiLoader().createWidget('Gui::QuantitySpinBox')
        self.angle_widget.setProperty('minimum', -89.9)
        self.angle_widget.setProperty('maximum', 89.9)
        self.angle_widget.setEnabled(False)
        self._template = make_expr_template({
            'Angle': 'App::PropertyAngle',
        })
        self._template.bind(self.angle_widget, 'Angle', 0.0)

        # Angle row
        self.angle_apply_btn = QtWidgets.QPushButton("Update Angle")
        self.angle_apply_btn.clicked.connect(self._on_apply_angle)
        self.angle_apply_btn.setEnabled(False)
        angle_input_layout = QtWidgets.QVBoxLayout()
        angle_input_layout.addWidget(self.angle_widget)
        angle_input_layout.addWidget(self.angle_apply_btn)

        update_data_layout = QtWidgets.QFormLayout()
        update_data_layout.setFormAlignment(QtCore.Qt.AlignCenter)
        update_data_layout.setLabelAlignment(
            QtCore.Qt.AlignRight | QtCore.Qt.AlignTrailing | QtCore.Qt.AlignVCenter)
        update_data_layout.addRow("Angle:", angle_input_layout)
        button_layout.addLayout(update_data_layout)

        layout.addWidget(self._table)
        layout.addLayout(button_layout)

        # Populate table
        miters = [obj for obj in self._doc.Objects
                  if getattr(obj, 'Type', '') == 'ShaperMiter']
        self._table.populate(miters)

        # Connect signals
        self._table.checkedStateChanged.connect(self._on_table_checked_state_changed)

    def run_cleanup(self):
        self._template.destroyTemplate()

    def _on_table_checked_state_changed(self, checked: [App.DocumentObject]):
        has_selection = len(checked) > 0
        self.angle_widget.setEnabled(has_selection)
        self.angle_apply_btn.setEnabled(has_selection)

    def _on_apply_angle(self):
        selected = self._table.get_checked_objects()
        n = len(selected)
        for miter in selected:
            self._template.update_object(miter, 'Angle')
            miter.recompute()
            miter.Proxy.parent_cutout(miter).recompute()
        self._table.refresh_display()
        self._report_section.replace_text(f"Updated angle on {n} selected miters."
                                          "\n(Clicking 'Cancel' will undo this.)")
