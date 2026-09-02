# SPDX-License-Identifier: GPL-3.0-or-later

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtWidgets

from .task_panel import ShaperTaskPanel
from ShaperSvgShape import OPEN_WIRE_TYPES, CLOSED_WIRE_TYPES


def open_shape_task_panel(shape_obj=None):
    if Gui.Control.activeDialog():
        Gui.Control.closeDialog()
    panel = ShaperSvgShapeTaskPanel(shape_obj)
    Gui.Control.showDialog(panel)


class ShaperSvgShapeTaskPanel(ShaperTaskPanel):
    """Edit dialog for a ShaperSvgShape object.

    Allows changing position/rotation, the cut depth (enable + value), and the
    cut types used for open and closed wires. The open-wire / closed-wire cut
    type controls are greyed out when the source object has no wires of that
    kind.
    """

    def __init__(self, shape_obj: App.DocumentObject):
        super().__init__("SVG Shape", shape_obj)

        # Source (display only; changing a shape's source is better done by
        # deleting and re-adding it).
        source_label = QtWidgets.QLabel(
            self._object.Source.Label if self._object.Source else '(none)')
        self._main_layout.addRow("Source:", source_label)

        # Position / rotation
        self._main_layout.addRow(
            "Offset X:",
            self._quantity_widget('OffsetX'),
        )
        self._main_layout.addRow(
            "Offset Y:",
            self._quantity_widget('OffsetY'),
        )
        self._main_layout.addRow(
            "Rotation:",
            self._quantity_widget('Rotation'),
        )

        # Cut depth enable + value
        self.cut_depth_checkbox = QtWidgets.QCheckBox("Enable cut depth")
        self.cut_depth_checkbox.setChecked(bool(self._object.CutDepthEnabled))
        self.cut_depth_checkbox.setToolTip(
            "Include shaper:cutDepth on the exported paths.")
        self.cut_depth_checkbox.stateChanged.connect(self._on_cut_depth_enabled_changed)
        self._main_layout.addRow(self.cut_depth_checkbox)

        self.cut_depth_widget = self._quantity_widget('CutDepth', minimum=0.0)
        self._main_layout.addRow("Cut Depth:", self.cut_depth_widget)

        # Cut types for open / closed wires
        self.open_wire_combo = self._enum_combo('OpenWireType', OPEN_WIRE_TYPES)
        self._main_layout.addRow("Open Wires:", self.open_wire_combo)

        self.closed_wire_combo = self._enum_combo('ClosedWireType', CLOSED_WIRE_TYPES)
        self._main_layout.addRow("Closed Wires:", self.closed_wire_combo)

        self._update_wire_combo_sensitivity()
        self.cut_depth_widget.setEnabled(bool(self._object.CutDepthEnabled))

    def create_uninitialized_object(self) -> App.DocumentObject:
        raise RuntimeError("ShaperSvgShapeTaskPanel is edit-only")

    def recompute_objects(self, updated_prop_name: str):
        self._object.recompute()

    def _enum_combo(self, prop_name, choices):
        combo = QtWidgets.QComboBox()
        for c in choices:
            combo.addItem(c, c)
        combo.setCurrentIndex(combo.findData(getattr(self._object, prop_name)))
        combo.currentIndexChanged.connect(
            lambda _idx, p=prop_name, cb=combo: self._on_enum_changed(p, cb.currentData()))
        return combo

    def _on_enum_changed(self, prop_name, value):
        if value is None:
            return
        setattr(self._object, prop_name, value)
        self.recompute_objects(prop_name)

    def _on_cut_depth_enabled_changed(self):
        self._object.CutDepthEnabled = self.cut_depth_checkbox.isChecked()
        self.cut_depth_widget.setEnabled(self.cut_depth_checkbox.isChecked())
        self.recompute_objects('CutDepthEnabled')

    def _update_wire_combo_sensitivity(self):
        """Grey out the open- / closed-wire cut type choice if the source has no
        wires of that kind."""
        has_open = False
        has_closed = False
        shape = getattr(self._object.Source, 'Shape', None) if self._object.Source else None
        if shape is not None and not shape.isNull():
            for w in shape.Wires:
                if w.isClosed():
                    has_closed = True
                else:
                    has_open = True

        self.open_wire_combo.setEnabled(has_open)
        self.closed_wire_combo.setEnabled(has_closed)
        tip = "The source has no %s wires; this setting has no effect."
        self.open_wire_combo.setToolTip('' if has_open else tip % 'open')
        self.closed_wire_combo.setToolTip('' if has_closed else tip % 'closed')
