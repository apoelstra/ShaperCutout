# SPDX-License-Identifier: GPL-3.0-or-later

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore, QtGui, QtWidgets

from command.report_view.model import ReportTableModel, ReportTableWidget
from shaper_cutout_util import make_expr_template, parent_cutout


class SlotModel(ReportTableModel):
    def __init__(self, slots=None):
        def parent_label(slot):
            parent = parent_cutout(slot, 'Slots')
            return parent.Label if parent else '<no parent>'

        super().__init__([
            ("Name", lambda slot: slot.Label),
            ("Cutout", parent_label),
            ("Length Tolerance", lambda slot: slot.LengthTolerance),
            ("Width Tolerance", lambda slot: slot.WidthTolerance),
        ])


class ReportViewSlots(QtGui.QWidget):
    def __init__(self, report_section):
        self._doc = App.ActiveDocument
        self._report_section = report_section

        super().__init__()
        self.initUi()

    def initUi(self):
        self.setWindowTitle("Slots")
        layout = QtWidgets.QVBoxLayout(self)

        # Slots section
        self._table = ReportTableWidget(SlotModel())

        # Buttons
        button_layout = QtWidgets.QVBoxLayout()

        # Update data row
        self.length_tolerance_widget = Gui.UiLoader().createWidget('Gui::QuantitySpinBox')
        self.length_tolerance_widget.setProperty('minimum', 0)
        self.length_tolerance_widget.setEnabled(False)
        self.width_tolerance_widget = Gui.UiLoader().createWidget('Gui::QuantitySpinBox')
        self.width_tolerance_widget.setProperty('minimum', 0)
        self.width_tolerance_widget.setEnabled(False)
        self._template = make_expr_template({
            'LengthTolerance': 'App::PropertyLength',
            'WidthTolerance': 'App::PropertyLength',
        })
        self._template.bind(self.length_tolerance_widget, 'LengthTolerance', 0)
        self._template.bind(self.width_tolerance_widget, 'WidthTolerance', 0)

        # Length Tolerance row
        self.length_tolerance_apply_btn = QtWidgets.QPushButton("Update Length Tolerance")
        self.length_tolerance_apply_btn.clicked.connect(self._on_apply_length_tolerance)
        self.length_tolerance_apply_btn.setEnabled(False)
        length_tolerance_input_layout = QtWidgets.QVBoxLayout()
        length_tolerance_input_layout.addWidget(self.length_tolerance_widget)
        length_tolerance_input_layout.addWidget(self.length_tolerance_apply_btn)

        # Width Tolerance row
        self.width_tolerance_apply_btn = QtWidgets.QPushButton("Update Width Tolerance")
        self.width_tolerance_apply_btn.clicked.connect(self._on_apply_width_tolerance)
        self.width_tolerance_apply_btn.setEnabled(False)
        width_tolerance_input_layout = QtWidgets.QVBoxLayout()
        width_tolerance_input_layout.addWidget(self.width_tolerance_widget)
        width_tolerance_input_layout.addWidget(self.width_tolerance_apply_btn)

        update_data_layout = QtWidgets.QFormLayout()
        update_data_layout.setFormAlignment(QtCore.Qt.AlignCenter)
        update_data_layout.setLabelAlignment(
            QtCore.Qt.AlignRight | QtCore.Qt.AlignTrailing | QtCore.Qt.AlignVCenter)
        update_data_layout.addRow("Length Tolerance:", length_tolerance_input_layout)
        update_data_layout.addRow("Width Tolerance:", width_tolerance_input_layout)
        button_layout.addLayout(update_data_layout)

        layout.addWidget(self._table)
        layout.addLayout(button_layout)

        # Populate table
        slots = [obj for obj in self._doc.Objects
                 if getattr(obj, 'Type', '') == 'ShaperSlot']
        self._table.populate(slots)

        # Connect signals
        self._table.checkedStateChanged.connect(self._on_table_checked_state_changed)

    def _on_table_checked_state_changed(self, checked: [App.DocumentObject]):
        has_selection = len(checked) > 0
        self.length_tolerance_widget.setEnabled(has_selection)
        self.width_tolerance_widget.setEnabled(has_selection)
        self.length_tolerance_apply_btn.setEnabled(has_selection)
        self.width_tolerance_apply_btn.setEnabled(has_selection)

    def _on_apply_length_tolerance(self):
        selected = self._table.get_checked_objects()
        n = len(selected)
        for slot in selected:
            self._template.update_object(slot, 'LengthTolerance')
            slot.recompute()
            slot.Proxy.find_cutout1(slot).recompute()
            slot.Proxy.find_cutout2(slot).recompute()
        self._report_section.replace_text(f"Updated length tolerance on {n} selected slots."
                                          "\n(Clicking 'Cancel' will undo this.)")

    def _on_apply_width_tolerance(self):
        selected = self._table.get_checked_objects()
        n = len(selected)
        for slot in selected:
            self._template.update_object(slot, 'WidthTolerance')
            slot.recompute()
            slot.Proxy.find_cutout1(slot).recompute()
            slot.Proxy.find_cutout2(slot).recompute()
        self._report_section.replace_text(f"Updated width tolerance on {n} selected slots."
                                          "\n(Clicking 'Cancel' will undo this.)")
