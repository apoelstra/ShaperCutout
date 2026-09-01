# SPDX-License-Identifier: GPL-3.0-or-later

from typing import Optional
from PySide import QtCore, QtWidgets

import FreeCAD as App
import FreeCADGui as Gui

from .task_panel import ShaperTaskPanel


class ShaperSvgPageTaskPanel(ShaperTaskPanel):
    """Edit dialog for a ShaperSvgPage object.

    Allows changing page width, height, grid spacing, and the overlap /
    minimum-distance display flags.
    """

    def __init__(self, page_obj: App.DocumentObject):
        super().__init__("SVG Page", page_obj)

        # Width
        self._main_layout.addRow(
            "Width:",
            self._quantity_widget('Width', minimum=1e-7),
        )

        # Height
        self._main_layout.addRow(
            "Height:",
            self._quantity_widget('Height', minimum=1e-7),
        )

        # Grid spacing
        self._main_layout.addRow(
            "Grid Spacing:",
            self._quantity_widget('GridSpacing', minimum=1e-7),
        )

        # Show overlaps (may be slow)
        self.overlaps_checkbox = QtWidgets.QCheckBox()
        self.overlaps_checkbox.setChecked(getattr(self._object, 'ShowOverlaps', True))
        self.overlaps_checkbox.setToolTip(
            "Show overlap highlights between images. May be slow on complex pages."
        )
        self.overlaps_checkbox.stateChanged.connect(self._on_overlaps_changed)
        self._main_layout.addRow("Show Overlaps:", self.overlaps_checkbox)

        # Show minimum distances (may be slow)
        self.mindist_checkbox = QtWidgets.QCheckBox()
        self.mindist_checkbox.setChecked(getattr(self._object, 'ShowMinDistances', True))
        self.mindist_checkbox.setToolTip(
            "Show minimum distance lines between images. May be slow on complex pages."
        )
        self.mindist_checkbox.stateChanged.connect(self._on_mindist_changed)
        self._main_layout.addRow("Show Minimum Distances:", self.mindist_checkbox)

        self._initialized = True

    def create_uninitialized_object(self) -> App.DocumentObject:
        raise RuntimeError("ShaperSvgPageTaskPanel is edit-only")

    def recompute_objects(self, updated_prop_name: str):
        if not self._initialized:
            return
        self._object.recompute()

    def _on_overlaps_changed(self):
        self._object.ShowOverlaps = self.overlaps_checkbox.isChecked()
        self.recompute_objects('ShowOverlaps')

    def _on_mindist_changed(self):
        self._object.ShowMinDistances = self.mindist_checkbox.isChecked()
        self.recompute_objects('ShowMinDistances')


def open_page_task_panel(page_obj=None):
    if Gui.Control.activeDialog():
        Gui.Control.closeDialog()
    panel = ShaperSvgPageTaskPanel(page_obj)
    Gui.Control.showDialog(panel)
