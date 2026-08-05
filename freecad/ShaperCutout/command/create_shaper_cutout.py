# SPDX-License-Identifier: GPL-3.0-or-later

import os

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtWidgets

from .task_panel import ShaperTaskPanel
from shaper_cutout_util import _ICON_ROOT, copy_property, is_single_selected, is_sketch, \
        force_combo_to_value, objects_are_parallel


_SUPPORTED_PLANE_TYPES = ['App::Plane', 'Part::Plane', 'Part::DatumPlane', 'PartDesign::Plane']


def _lcs_parent(obj):
    if obj is None or len(getattr(obj, 'InList', [])) == 0:
        return None

    for parent in obj.InList:
        if getattr(parent, 'TypeId', '') in (
            "App::LocalCoordinateSystem",
            "Part::LocalCoordinateSystem",
            "PartDesign::CoordinateSystem"
        ):
            return parent
    return None


def _dado_parents(obj):
    """Find all ShaperDados for which this is some sketch."""
    if obj is None or len(getattr(obj, 'InList', [])) == 0:
        return []

    result = set()
    for parent in obj.InList:
        if getattr(parent, 'Type', '') == 'ShaperDado':
            result.extend(_cutout_parents(parent))

    return sorted(list(result), key=lambda x: x.Label)


def _cutout_parents(obj):
    """Find all ShaperCutouts for which this is some plane."""
    if obj is None or len(getattr(obj, 'InList', [])) == 0:
        return []

    result = set()
    for parent in obj.InList:
        if getattr(parent, 'Type', '') == 'ShaperCutout':
            result.add(parent)
        elif getattr(parent, 'Type', '') == 'ShaperDado':
            result.extend(_cutout_parents(parent))

    return sorted(list(result), key=lambda x: x.Label)


def open_cutout_task_panel(cutout=None):
    if Gui.Control.activeDialog():
        Gui.Control.closeDialog()
    panel = ShaperCutoutTaskPanel(cutout)
    Gui.Control.showDialog(panel)


class ShaperCutoutTaskPanel(ShaperTaskPanel):
    def __init__(self, cutout=None):
        self._initialized = False
        super().__init__("Cutout", cutout)

        # Collect available planes and sketches
        self._all_sketches = [o for o in self._doc.Objects
                              if is_sketch(o) and not _dado_parents(o)]

        # Plane combo
        self.plane_combo = QtWidgets.QComboBox()
        for o in self._doc.Objects:
            if getattr(o, 'TypeId', '') not in _SUPPORTED_PLANE_TYPES:
                continue

            parents = _cutout_parents(o)
            is_current = False
            shared_with = []
            is_center = len(parents) == 0
            for par in parents:
                if par.CenterPlane != o:
                    continue
                is_center = True

                if par == cutout:
                    is_current = True
                else:
                    shared_with.append(par.Label)

            if not is_center:
                # Planes that are (only) back/front/dado planes we exclude from the list. There
                # are a lot of them, it is unlikely to make sense for them to be plywood center
                # planes, and if the user really wants to do this he can add another plane in
                # the same position. (Though if you are reading this comment and disagree,
                # please file a bug!)
                continue

            suffix = " (current" if is_current else ""
            if len(shared_with) > 0:
                suffix += ", " if is_current else " ("
                suffix += ', '.join(shared_with)
            suffix += ")" if is_current or len(shared_with) > 0 else ""

            lcs_owner = _lcs_parent(o)
            if lcs_owner:
                self.plane_combo.addItem(f"{lcs_owner.Label}.{o.Label}{suffix}", o)
            else:
                self.plane_combo.addItem(f"{o.Label}{suffix}", o)

        force_combo_to_value(self.plane_combo, self._object.CenterPlane)
        self._main_layout.addRow("Center Plane:", self.plane_combo)

        # Thickness
        self._main_layout.addRow(
            "Thickness:",
            self._quantity_widget('Thickness', minimum=1e-7),
        )

        # Sketch combo
        self.sketch_combo = QtWidgets.QComboBox()
        self.sketch_combo.addItem('(No outline sketch)', None)

        # Open transaction and create/reference cutout
        if self._edit_mode:
            if self._object.CenterPlane:
                force_combo_to_value(self.plane_combo, self._object.CenterPlane)
            if self._object.OutlineSketch:
                force_combo_to_value(self.sketch_combo, self._object.OutlineSketch)

        for s in self._all_sketches:
            if objects_are_parallel(self.plane_combo.currentData(), s):
                self.sketch_combo.addItem(s.Label, s)
        self._main_layout.addRow("Outline Sketch:", self.sketch_combo)

        # Connect signals AFTER populating
        self.plane_combo.currentIndexChanged.connect(self._on_plane_changed)
        self.sketch_combo.currentIndexChanged.connect(self._on_changed)

        self._own_front = None
        self._own_back = None
        self._on_plane_changed()
        self._on_changed()
        self._initialized = True

    def create_uninitialized_object(self) -> App.DocumentObject:
        from ShaperCutout import create_uninitialized
        current_sel = Gui.Selection.getSelection()[0]
        _cutout = create_uninitialized()
        if getattr(current_sel, 'Type', '') == 'ShaperCutout':
            _cutout.CenterPlane = current_sel.CenterPlane
        else:
            _cutout.CenterPlane = current_sel

        # Copy initial thickness from any cutouts that share this center plane.
        for parent in _cutout.CenterPlane.InList:
            if getattr(parent, 'Type', '') != 'ShaperCutout' or parent == _cutout:
                continue
            if parent.CenterPlane == _cutout.CenterPlane:
                copy_property(parent, _cutout, 'Thickness')
                break

        return _cutout

    def recompute_objects(self, updated_prop_name: str):
        if not self._initialized:
            return

        # Recompute every cutout that shares this center plane when the thickness changes.
        if updated_prop_name == 'Thickness':
            for parent in self._object.CenterPlane.InList:
                if getattr(parent, 'Type', '') != 'ShaperCutout':
                    continue
                if parent.CenterPlane != self._object.CenterPlane:
                    continue
                parent.recompute()
        else:
            self._object.recompute()

    def _on_plane_changed(self):
        # Doing `self._object.CenterPlane = <X>` will trigger `ShaperCutout::onChanged` which will
        # update an update the computed planes. We don't want this to happen until the end of this
        # function, so we need to be a bit careful.
        #
        # We do this because when editing from the dialog, we (a) want to implement the "if the
        # user chooses another cutout's center, we atomically link to the other cutout's planes
        # rather than computing our own" logic, and (b) we want that when the user starts from
        # uniquely-owned planes, switches to shared planes, then switches back, they recover the
        # original uniquely-owned planes rather than having now ones be created. This only really
        # makes sense within the dialog so we can't move this logic into ShaperCutout::onChanged.
        new_plane = self.plane_combo.currentData()
        # Record current planes if they're unique to us
        if len(_cutout_parents(self._object.FrontFace)) == 1:
            self._own_front = self._object.FrontFace
            self._own_front.ViewObject.ShowInTree = False
        if len(_cutout_parents(self._object.BackFace)) == 1:
            self._own_back = self._object.BackFace
            self._own_back.ViewObject.ShowInTree = False

        # Disable thickness dialog if we are sharing a plane
        sharing_center = False
        parents = _cutout_parents(new_plane)
        for par in parents:
            if par == self._object or par.CenterPlane != new_plane:
                continue
            self._object.FrontFace = par.FrontFace
            self._object.BackFace = par.BackFace
            sharing_center = True
            break

        if not sharing_center:
            self._object.FrontFace = None
            self._object.BackFace = None
            if self._own_front is not None:
                self._object.FrontFace = self._own_front
                self._own_front.ViewObject.ShowInTree = True
                self._own_front = None
            if self._own_back is not None:
                self._object.BackFace = self._own_back
                self._own_back.ViewObject.ShowInTree = True
                self._own_back = None
        self._object.CenterPlane = new_plane

        # Update sketch combo
        selected_sketch = self.sketch_combo.currentData()
        self.sketch_combo.clear()
        self.sketch_combo.addItem('(No outline sketch)', None)
        idx = 1
        for s in self._all_sketches:
            if objects_are_parallel(self.plane_combo.currentData(), s):
                self.sketch_combo.addItem(s.Label, s)
                if selected_sketch == s:
                    self.sketch_combo.setCurrentIndex(idx)
                idx += 1

    def _on_changed(self):
        self._object.OutlineSketch = self.sketch_combo.currentData()
        self.recompute_objects('OutlineSketch')

    def accept(self):
        if self._own_front:
            self._doc.removeObject(self._own_front)
        if self._own_back:
            self._doc.removeObject(self._own_back)

        super().accept()


class CreateShaperCutoutCmd:
    def GetResources(self):
        icon_path = os.path.join(_ICON_ROOT, "cutout.svg")
        return {
            "MenuText": "Create Shaper Cutout",
            "ToolTip": "Create an empty cutout from the selected plane (or the center plane of "
                        "the selected cutout).",
            "Pixmap": icon_path,
        }

    def IsActive(self):
        if not App.ActiveDocument:
            return False
        return is_single_selected(_SUPPORTED_PLANE_TYPES) or is_single_selected('ShaperCutout')

    def Activated(self):
        open_cutout_task_panel()
