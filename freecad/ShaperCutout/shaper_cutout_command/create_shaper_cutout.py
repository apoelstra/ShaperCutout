# SPDX-License-Identifier: GPL-3.0-or-later

import os
from typing import Optional, Tuple

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtWidgets

from .task_panel import ShaperTaskPanel
import shaper_cutout_util
from shaper_cutout_util import _ICON_ROOT, all_objects, copy_property, \
    get_or_create_attachment_plane, objects_are_parallel, Objects, ShaperCutoutType


def _selection_center_and_sketch(
    selected: Optional[Objects] = None
) -> Tuple[Optional[App.DocumentObject], Optional[App.DocumentObject]]:
    """Parse a selection for the Create Shaper Cutout command.

    Accepts exactly one center-plane candidate (either a ShaperCutout (interpreted as its
    center plane) or an actual plane) and one sketch candidate.
    """
    if selected is None:
        selected = shaper_cutout_util.selection()

    n_objects = len(selected.dict[ShaperCutoutType.CUTOUT]) \
        + len(selected.dict[ShaperCutoutType.PLANE]) \
        + len(selected.dict[ShaperCutoutType.SKETCH])
    if selected.total_count != n_objects:
        # Extra stuff selected.
        return None, None

    centers = set(o.CenterPlane for o in selected.dict[ShaperCutoutType.CUTOUT]).union(
        set(selected.dict[ShaperCutoutType.PLANE]))
    sketches = selected.dict[ShaperCutoutType.SKETCH]

    # More than one plane selected.
    if len(centers) > 1 or len(sketches) > 1:
        return None, None

    return centers.pop() if len(centers) == 1 else None, \
        sketches.pop() if len(sketches) == 1 else None


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


def _has_dado_parent(obj):
    for parent in getattr(obj, 'InList', []):
        if ShaperCutoutType.DADOS.is_type_of(parent):
            return True
    return False


def _cutout_parents(obj):
    """Find all ShaperCutouts for which this is some plane."""
    if obj is None or len(getattr(obj, 'InList', [])) == 0:
        return []

    result = set()
    for parent in obj.InList:
        if getattr(parent, 'Type', '') == 'ShaperCutout':
            result.add(parent)
        elif getattr(parent, 'Type', '') == 'ShaperDados':
            result.update(_cutout_parents(parent))

    return sorted(list(result), key=lambda x: x.Label)


def open_cutout_task_panel(cutout=None):
    if Gui.Control.activeDialog():
        Gui.Control.closeDialog()
    panel = ShaperCutoutTaskPanel(cutout)
    Gui.Control.showDialog(panel)

    if panel.preselect_warnings:
        QtWidgets.QMessageBox.warning(
            None, "Sketch Not Usable",
            "Creating the cutout without an outline sketch; "
            + "; ".join(panel.preselect_warnings) + ".")


class ShaperCutoutTaskPanel(ShaperTaskPanel):
    def __init__(self, cutout=None):
        self._initialized = False
        self.preselect_warnings = []
        selection = shaper_cutout_util.selection()
        if cutout is None:
            self._sel_center, self._sel_sketch = _selection_center_and_sketch(selection)
        else:
            self._sel_center, self._sel_sketch = cutout.CenterPlane, None
        super().__init__("Cutout", cutout)

        # Collect available planes and sketches
        all_doc_objects = all_objects(self._doc)

        # Plane combo
        def plane_label(o: App.DocumentObject) -> Optional[str]:
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
                return None

            suffix = " (current" if is_current else ""
            if len(shared_with) > 0:
                suffix += ", " if is_current else " ("
                suffix += ', '.join(shared_with)
            suffix += ")" if is_current or len(shared_with) > 0 else ""

            lcs_owner = _lcs_parent(o)
            if lcs_owner:
                return f"{lcs_owner.Label}.{o.Label}{suffix}"
            else:
                return f"{o.Label}{suffix}"

        self.plane_combo = self._link_widget(
            "CenterPlane",
            ShaperCutoutType.PLANE,
            None,
            all_doc_objects,
            selected_value=self._sel_center,
            labelfn=plane_label,
        )

        self._main_layout.addRow("Center Plane:", self.plane_combo._widget)

        # Thickness
        self._main_layout.addRow(
            "Thickness:",
            self._quantity_widget('Thickness', minimum=1e-7),
        )

        # Sketch combo
        if self._sel_sketch:
            center = self.plane_combo._widget.currentData()
            parent_dados = Objects(self._sel_sketch.InList).dict[ShaperCutoutType.DADOS]
            if any(self._sel_sketch in getattr(d, 'Sketches', []) for d in parent_dados):
                self.preselect_warnings.append(
                    f"sketch '{self._sel_sketch.Label}' belongs to a dado set and is not usable"
                    " as an outline sketch")
            elif not objects_are_parallel(center, self._sel_sketch):
                self.preselect_warnings.append(
                    f"sketch '{self._sel_sketch.Label}' is not parallel to the center plane")

        def sketch_label(s: App.DocumentObject) -> Optional[str]:
            if objects_are_parallel(self.plane_combo._widget.currentData(), s) \
                    and not _has_dado_parent(s):
                return s.Label
            return None

        self.sketch_combo = self._link_widget(
            "OutlineSketch",
            ShaperCutoutType.SKETCH,
            "(No outline sketch)",
            all_doc_objects,
            selected_value=self._sel_sketch,
            labelfn=sketch_label,
        )

        self._main_layout.addRow("Outline Sketch:", self.sketch_combo._widget)

        # Connect signals AFTER populating
        self.plane_combo._widget.currentIndexChanged.connect(self._on_plane_changed)

        self._front = None
        self._back = None
        self._initialized = True
        self._on_plane_changed()

    def create_uninitialized_object(self) -> Optional[App.DocumentObject]:
        from ShaperCutout import create_uninitialized
        center = self._sel_center
        if center is None:
            if self._sel_sketch is None:
                return None

            center = get_or_create_attachment_plane(self._sel_sketch)
            if center is None:
                return None

        _cutout = create_uninitialized()
        _cutout.CenterPlane = center

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
        # This should've been run after the LinkWidget signal handler.
        assert self._object.CenterPlane == self.plane_combo._widget.currentData()
        # If any other cutouts share this CenterPlane, also share their front and back planes.
        sharing_center = False
        parents = _cutout_parents(self._object.CenterPlane)
        for par in parents:
            if par == self._object or par.CenterPlane != self._object.CenterPlane:
                continue
            self._object.FrontFace = par.FrontFace
            self._object.BackFace = par.BackFace

            if self._front is not None:
                self._doc.removeObject(self._front)
                self._front = None
            if self._back is not None:
                self._doc.removeObject(self._back)
                self._back = None
            break

        # If not, create new planes if they don't already exist.
        if not sharing_center:
            if self._front is None:
                self._front = self._doc.addObject('Part::DatumPlane', f'{self._object.Name}_Front')
                self._front.setPropertyStatus('AttachmentSupport', 2)
                self._front.setPropertyStatus('AttachmentOffset', 2)
                self._front.setPropertyStatus('MapMode', 2)
            if self._back is None:
                self._back = self._doc.addObject('Part::DatumPlane', f'{self._object.Name}_Back')
                self._back.setPropertyStatus('AttachmentSupport', 2)
                self._back.setPropertyStatus('AttachmentOffset', 2)
                self._back.setPropertyStatus('MapMode', 2)
            self._object.FrontFace = self._front
            self._object.BackFace = self._back

        # Then move the plane(s).
        self._object.Proxy._propagate_thickness(self._object)

        # And update the sketch combo since our set of parallel sketches may have changed.
        self.sketch_combo._refresh(all_objects(self._doc))


class CreateShaperCutoutCmd:
    def GetResources(self):
        icon_path = os.path.join(_ICON_ROOT, "cutout.svg")
        return {
            "MenuText": "Create Shaper Cutout",
            "ToolTip": "Create an empty cutout from the selected plane (or the center plane of "
                        "the selected cutout). Any selected sketches are offered as the outline "
                        "sketch.",
            "Pixmap": icon_path,
            "CmdType": "AlterDoc",
        }

    def IsActive(self):
        center, sketch = _selection_center_and_sketch()
        return center is not None or sketch is not None

    def Activated(self):
        open_cutout_task_panel()
