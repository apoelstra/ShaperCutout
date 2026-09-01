# SPDX-License-Identifier: GPL-3.0-or-later

import os

import FreeCAD as App
import FreeCADGui as Gui
import Part
from PySide import QtWidgets

from .task_panel import ShaperTaskPanel
from shaper_cutout_util import _ICON_ROOT
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


class ShaperMiterTaskPanel(ShaperTaskPanel):
    def __init__(self, cutout, miter=None):
        self._initialized = False
        self._cutout = cutout
        super().__init__("Miter", miter)

        # Edge multi-select
        self.edge_list = QtWidgets.QListWidget()
        self.edge_list.setSelectionMode(QtWidgets.QAbstractItemView.MultiSelection)
        for name in _straight_edges(cutout.OutlineSketch):
            self.edge_list.addItem(name)
        self.edge_list.setMinimumHeight(100)
        self._main_layout.addRow("Edges:", self.edge_list)

        # Angle
        self._main_layout.addRow(
            "Angle:",
            self._quantity_widget(
                'Angle',
                minimum=-89.99,
                maximum=89.99,
            ),
        )

        # Miter axis
        self.axis_combo = QtWidgets.QComboBox()
        self.axis_combo.addItems(["Center", "Front", "Back"])
        self._main_layout.addRow("Miter Axis:", self.axis_combo)

        # Populate UI from miter state
        axis_idx = self.axis_combo.findText(self._object.MiterAxis)
        if axis_idx >= 0:
            self.axis_combo.setCurrentIndex(axis_idx)
        # Pre-select edges
        current_edges = set()
        for (_, subnames) in self._object.Edges:
            current_edges.update(subnames)
        for i in range(self.edge_list.count()):
            item = self.edge_list.item(i)
            item.setSelected(item.text() in current_edges)

        self.edge_list.itemSelectionChanged.connect(self._on_changed)
        self.axis_combo.currentIndexChanged.connect(self._on_changed)
        self._initialized = True

    def recompute_objects(self, updated_prop_name: str):
        if self._initialized:
            self._cutout.recompute()

    def create_uninitialized_object(self) -> App.DocumentObject:
        return ShaperMiter.create(
            cutout=self._cutout,
            edges=[(self._cutout.OutlineSketch, [])],
            angle=45.0,
            miter_axis="Center",
            name="Miter",
        )

    def _on_changed(self):
        selected = [item.text() for item in self.edge_list.selectedItems()]
        self._object.Edges = [(self._cutout.OutlineSketch, selected)]
        self._object.MiterAxis = self.axis_combo.currentText()
        self.recompute_objects(None)

    def accept(self):
        if not [item for item in self.edge_list.selectedItems()]:
            QtWidgets.QMessageBox.warning(
                self.form, "No Edges", "Please select at least one edge.")
            return
        super().accept()


class CreateShaperMiterCmd:
    def GetResources(self):
        icon_path = os.path.join(_ICON_ROOT, "miter.svg")
        return {
            "MenuText": "Create Miter",
            "ToolTip": "Create a miter cut on selected edges of a ShaperCutout outline sketch",
            "Pixmap": icon_path,
            "CmdType": "AlterDoc",
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
