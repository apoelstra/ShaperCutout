# SPDX-License-Identifier: GPL-3.0-or-later

import os

import FreeCAD as App
import FreeCADGui as Gui
import Part
from PySide import QtWidgets

from shaper_cutout_util import make_expr_template
import ShaperMiter


def _selected_cutout():
    for sel_obj in Gui.Selection.getSelectionEx():
        obj = sel_obj.Object
        if getattr(obj, 'Type', None) == 'ShaperCutout':
            return obj
        for parent in obj.InList:
            if getattr(parent, 'Type', None) == 'ShaperCutout':
                return parent
    return None


def _straight_edges(sketch):
    result = []
    for i, edge in enumerate(sketch.Shape.Edges):
        if isinstance(edge.Curve, Part.Line):
            result.append(f'Edge{i + 1}')
    return result


def open_miter_task_panel(cutout, miter=None):
    """Open the task panel. If miter is None, a new one will be created."""
    if Gui.Control.activeDialog():
        Gui.Control.closeDialog()
    panel = ShaperMiterTaskPanel(cutout, miter)
    Gui.Control.showDialog(panel)


class ShaperMiterTaskPanel:
    def __init__(self, cutout, miter=None):
        self._cutout = cutout
        self._doc = cutout.Document

        # Build the UI widget
        self.form = QtWidgets.QWidget()
        self.form.setWindowTitle("Create Miter" if miter is None else "Edit Miter")
        layout = QtWidgets.QFormLayout(self.form)

        # Label
        self.label_edit = QtWidgets.QLineEdit()
        layout.addRow("Label:", self.label_edit)

        # Edge multi-select
        self.edge_list = QtWidgets.QListWidget()
        self.edge_list.setSelectionMode(QtWidgets.QAbstractItemView.MultiSelection)
        for name in _straight_edges(cutout.OutlineSketch):
            self.edge_list.addItem(name)
        self.edge_list.setMinimumHeight(100)
        layout.addRow("Edges:", self.edge_list)

        # Angle
        self.angle_spin = Gui.UiLoader().createWidget('Gui::QuantitySpinBox')
        self.angle_spin.setProperty('unit', 'deg')
        layout.addRow("Angle:", self.angle_spin)

        # Miter axis
        self.axis_combo = QtWidgets.QComboBox()
        self.axis_combo.addItems(["Center", "Front", "Back"])
        layout.addRow("Miter Axis:", self.axis_combo)

        # Create or snapshot existing miter
        self._doc.openTransaction("Create Miter" if miter is None else "Edit Miter")
        self._template = make_expr_template({'Angle': 'App::PropertyAngle'})
        self._template.set_from_object(miter, 'Angle', default=45.0)
        self._template.bind(self.angle_spin, 'Angle')

        self._miter = miter
        if self._miter is None:
            self._miter = ShaperMiter.create(
                cutout=cutout,
                edges=[(cutout.OutlineSketch, [])],
                angle=self._template.widget_value('Angle'),
                miter_axis="Center",
                name="Miter",
            )

        # Populate UI from miter state
        self.label_edit.setText(self._miter.Label)
        axis_idx = self.axis_combo.findText(self._miter.MiterAxis)
        if axis_idx >= 0:
            self.axis_combo.setCurrentIndex(axis_idx)
        # Pre-select edges
        current_edges = set()
        for (_, subnames) in self._miter.Edges:
            current_edges.update(subnames)
        for i in range(self.edge_list.count()):
            item = self.edge_list.item(i)
            item.setSelected(item.text() in current_edges)

        # Connect signals AFTER populating to avoid spurious recomputes
        self.label_edit.textChanged.connect(self._on_changed)
        self.edge_list.itemSelectionChanged.connect(self._on_changed)
        self.angle_spin.valueChanged.connect(self._on_changed)
        self.axis_combo.currentIndexChanged.connect(self._on_changed)

    def _on_changed(self):
        selected = [item.text() for item in self.edge_list.selectedItems()]
        self._miter.Label = self.label_edit.text().strip() or "Miter"
        self._miter.Edges = [(self._cutout.OutlineSketch, selected)]
        self._miter.MiterAxis = self.axis_combo.currentText()
        self._template.update_object(self._miter, 'Angle')

        cutout = next(
            (p for p in self._miter.InList if getattr(p, 'Type', None) == 'ShaperCutout'),
            None
        )
        cutout.recompute()

    def accept(self):
        if not [item for item in self.edge_list.selectedItems()]:
            QtWidgets.QMessageBox.warning(
                self.form, "No Edges", "Please select at least one edge.")
            return
        self._miter.Label = self.label_edit.text().strip() or "Miter"
        # An expression may have changed to an explicit value or vice-versa, which wouldn't
        # have triggered the widget's "on changed" signal. So explicitly call it here to make
        # sure the change is saved.
        self._on_changed()
        self._template.destroyTemplate()
        self._doc.commitTransaction()
        Gui.Control.closeDialog()

    def reject(self):
        self._doc.abortTransaction()
        Gui.Control.closeDialog()


class CreateShaperMiterCmd:
    def GetResources(self):
        icon_path = os.path.join(os.path.dirname(__file__),
                                 "../resources/icons/miter.svg")
        return {
            "MenuText": "Create Miter",
            "ToolTip": "Create a miter cut on selected edges of a ShaperCutout outline sketch",
            "Pixmap": icon_path,
        }

    def IsActive(self):
        if App.ActiveDocument is None:
            return False
        return _selected_cutout() is not None

    def Activated(self):
        cutout = _selected_cutout()
        if cutout is None:
            QtWidgets.QMessageBox.warning(
                None, "No Selection", "Please select a ShaperCutout first.")
            return
        open_miter_task_panel(cutout)
