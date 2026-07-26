# SPDX-License-Identifier: GPL-3.0-or-later

import os
import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtWidgets

from shaper_cutout_util import _ICON_ROOT, global_normal, objects_are_parallel
import ShaperSlot


_SUPPORTED_PLANE_TYPES = ['App::Plane', 'Part::Plane', 'Part::DatumPlane', 'PartDesign::Plane']


def _selected_cutouts_and_plane():
    """Return (cutout1, cutout2, interface_plane) or None."""
    sel = Gui.Selection.getSelection()
    cutouts = [o for o in sel if getattr(o, 'Type', None) == 'ShaperCutout']
    planes = [o for o in sel if getattr(o, 'TypeId', '') in _SUPPORTED_PLANE_TYPES]

    if len(cutouts) != 2 or len(planes) != 1:
        return None

    return cutouts[0], cutouts[1], planes[0]


def _validate_cutout(cutout):
    """Check that cutout has required properties."""
    if not cutout.OutlineSketch:
        return False
    if not cutout.FrontFace or not cutout.BackFace:
        return False
    return True


def _determine_first_cutout(cutout1, cutout2, interface_plane):
    """Determine which cutout is 'first' based on geometric properties."""
    # Get intersection axis of the two cutout center planes
    normal1 = global_normal(cutout1.CenterPlane)
    normal2 = global_normal(cutout2.CenterPlane)
    intersection_axis = normal1.cross(normal2)

    if intersection_axis.Length < 1e-6:
        # Should never happen, but if so, fall back to alphabetical
        return cutout1 if cutout1.Name < cutout2.Name else cutout2

    # Attempt to order the cutouts so that the default cut minimizes
    # removed material, i.e. by cutting the "upward" slot into the
    # more "downward" of the two.
    proj1 = cutout1.Shape.BoundBox.Center.dot(intersection_axis)
    proj2 = cutout2.Shape.BoundBox.Center.dot(intersection_axis)
    if abs(proj1 - proj2) < 1e-6:
        # If neither is more "downward", just go alphabetically by name.
        return cutout1 if cutout1.Name < cutout2.Name else cutout2

    return cutout1 if proj1 < proj2 else cutout2


def open_slot_task_panel(slot=None):
    if Gui.Control.activeDialog():
        Gui.Control.closeDialog()
    panel = ShaperSlotTaskPanel(slot)
    Gui.Control.showDialog(panel)


class ShaperSlotTaskPanel:
    def __init__(self, slot=None):
        self._doc = App.ActiveDocument
        self._edit_mode = slot is not None

        # Build UI
        action = "Edit" if self._edit_mode else "Create"
        self.form = QtWidgets.QWidget()
        self.form.setWindowTitle(f"{action} Slot")
        layout = QtWidgets.QFormLayout(self.form)

        # Label
        self.label_edit = QtWidgets.QLineEdit()
        self.label_edit.setEnabled(not self._edit_mode)
        layout.addRow("Label:", self.label_edit)

        # Invert checkbox
        self.invert_checkbox = QtWidgets.QCheckBox()
        layout.addRow("Invert:", self.invert_checkbox)

        # Get selection or existing slot data
        if self._edit_mode:
            self._slot = slot
            self._cutout1 = slot.Proxy.find_cutout1(slot)
            self._cutout2 = slot.Proxy.find_cutout2(slot)
            self._interface_plane = slot.InterfacePlane
            self.label_edit.setText(slot.Label)
            self.invert_checkbox.setChecked(slot.Invert)
        else:
            selection = _selected_cutouts_and_plane()
            if selection is None:
                QtWidgets.QMessageBox.warning(
                    None, "Invalid Selection",
                    "Please select exactly two ShaperCutouts and one interface plane.")
                Gui.Control.closeDialog()
                return

            cutout_a, cutout_b, interface_plane = selection

            # Validate cutouts
            if not _validate_cutout(cutout_a) or not _validate_cutout(cutout_b):
                QtWidgets.QMessageBox.warning(
                    None, "Invalid Cutout",
                    "Both cutouts must have an outline sketch and front/back faces.")
                Gui.Control.closeDialog()
                return

            # Planes must be orthogonal. (Otherwise the slot sides would need to be miters, which
            # (a) will require some complicated tooling to manufacture, and (b) would require some
            # complicated geometry for us to represent in 3D and SVG. If there is demand for this
            # we should add it later and gate it behind an "allow mitered slots" checkbox.
            #
            # Note that users can create a slot and then rotate their planes later, so this is
            # just a sanity check -- will need to check again during execution.
            norm_a = cutout_a.CenterPlane.Shape.Surface.normal(0, 0)
            norm_b = cutout_b.CenterPlane.Shape.Surface.normal(0, 0)
            if 1.0 - norm_a.cross(norm_b).Length > 1e-4:
                QtWidgets.QMessageBox.warning(
                    None, "Non-Orthogonal Cutouts",
                    "Cutout planes are not orthogonal; cannot create slot.")
                Gui.Control.closeDialog()
                return

            # If the interface plane is parallel to a cutout, the slot is ill-defined and there's
            # nothing we can do about it even in principle. (Again, will need to check again during
            # execution.)
            if objects_are_parallel(cutout_a.CenterPlane, interface_plane) or \
               objects_are_parallel(cutout_b.CenterPlane, interface_plane):
                QtWidgets.QMessageBox.warning(
                    None, "Parallel Plane",
                    "Interface plane is parallel to a cutout center plane; cannot create slot.")
                Gui.Control.closeDialog()
                return

            # Determine "first" cutout
            self._cutout1 = _determine_first_cutout(cutout_a, cutout_b, interface_plane)
            self._cutout2 = cutout_b if self._cutout1 == cutout_a else cutout_a
            self._interface_plane = interface_plane

            self._doc.openTransaction("Create Slot")
            self._slot = ShaperSlot.create_uninitialized(
                self._cutout1, self._cutout2, self._interface_plane, "Slot"
            )
            self.label_edit.setText(self._slot.Label)

        # Connect signals
        self.label_edit.textChanged.connect(self._on_changed)
        self.invert_checkbox.toggled.connect(self._on_changed)

        self._on_changed()

    def _on_changed(self):
        if self._slot is None:
            return

        if not self._edit_mode:
            label = self.label_edit.text().strip()
            self._slot.Label = label

        self._slot.Invert = self.invert_checkbox.isChecked()
        self._slot.recompute()
        self._cutout1.recompute()
        self._cutout2.recompute()

    def accept(self):
        self._on_changed()
        self._doc.commitTransaction()
        Gui.Control.closeDialog()

    def reject(self):
        self._doc.abortTransaction()
        Gui.Control.closeDialog()


class CreateShaperSlotCmd:
    def GetResources(self):
        icon_path = os.path.join(_ICON_ROOT, "slot.svg")
        return {
            "MenuText": "Create Slot",
            "ToolTip": "Cut a slot into the two selected cutouts at the selected interface plane",
            "Pixmap": icon_path,
        }

    def IsActive(self):
        if not App.ActiveDocument:
            return False
        return _selected_cutouts_and_plane() is not None

    def Activated(self):
        open_slot_task_panel()
