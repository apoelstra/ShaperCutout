# SPDX-License-Identifier: GPL-3.0-or-later

import os

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtWidgets

from shaper_cutout_util import is_single_selected, is_sketch, make_expr_template, \
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


class ShaperCutoutTaskPanel:
    def __init__(self, cutout=None):
        from ShaperCutout import create_uninitialized

        self._doc = App.ActiveDocument
        self._edit_mode = cutout is not None

        # Collect available planes and sketches
        self._all_sketches = [o for o in self._doc.Objects
                              if is_sketch(o) and not _dado_parents(o)]

        # Build UI
        action = "Edit" if self._edit_mode else "Create"
        self.form = QtWidgets.QWidget()
        self.form.setWindowTitle(f"{action} Shaper Cutout")
        layout = QtWidgets.QFormLayout(self.form)

        # Label
        self.label_edit = QtWidgets.QLineEdit()
        self.label_edit.setEnabled(not self._edit_mode)
        layout.addRow("Label:", self.label_edit)

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

        layout.addRow("Center Plane:", self.plane_combo)

        # Thickness
        thickness_widget = Gui.UiLoader().createWidget('Gui::QuantitySpinBox')
        thickness_widget.setProperty('unit', 'mm')
        layout.addRow("Thickness:", thickness_widget)
        self.thickness_widget = thickness_widget

        # Sketch combo
        self.sketch_combo = QtWidgets.QComboBox()
        self.sketch_combo.addItem('(No outline sketch)', None)

        # Set initial widget values
        current_sel = Gui.Selection.getSelection()[0]
        if self._edit_mode:
            self._cutout = cutout
            if cutout.CenterPlane:
                force_combo_to_value(self.plane_combo, cutout.CenterPlane)
            if cutout.OutlineSketch:
                force_combo_to_value(self.sketch_combo, cutout.OutlineSketch)
        else:
            self._cutout = create_uninitialized('')
            self._cutout.ViewObject.ShowInTree = False
            if getattr(current_sel, 'Type', '') == 'ShaperCutout':
                force_combo_to_value(self.plane_combo, current_sel.CenterPlane)

        for s in self._all_sketches:
            if objects_are_parallel(self.plane_combo.currentData(), s):
                self.sketch_combo.addItem(s.Label, s)

        # Label
        layout.addRow("Outline Sketch:", self.sketch_combo)
        self.label_edit.setText(self._cutout.Label)

        # Open transaction and create/reference cutout
        self._doc.openTransaction(f"{action} Shaper Cutout")
        self._template = make_expr_template({'Thickness': 'App::PropertyLength'})
        self._template.set_from_object(self._cutout, 'Thickness')
        self._template.bind(self.thickness_widget, 'Thickness')

        # Copy thickness from current selection, if we are making a new cutout from an
        # existing one. To deal with expression/value complexity it's fastest to just
        # do the copy in two steps via the template object.
        print(self._edit_mode)
        print(getattr(current_sel, 'Type', ''))
        if not self._edit_mode and getattr(current_sel, 'Type', '') == 'ShaperCutout':
            print("Setting thickness...")
            self._template.set_from_object(current_sel, 'Thickness')
            self._template.update_object(self._cutout, 'Thickness')

        # Connect signals AFTER populating
        self.label_edit.textChanged.connect(self._on_changed)
        self.plane_combo.currentIndexChanged.connect(self._on_plane_changed)
        self.sketch_combo.currentIndexChanged.connect(self._on_changed)
        self.thickness_widget.valueChanged.connect(self._on_thickness_changed)

        self._on_changed()

    def _on_plane_changed(self):
        self._cutout.CenterPlane = self.plane_combo.currentData()
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

    def _on_thickness_changed(self):
        if self._cutout is None:
            return

        center_plane = getattr(self._cutout, 'CenterPlane')
        for parent in center_plane.InList:
            if getattr(parent, 'Type', '') != 'ShaperCutout':
                continue
            if parent.CenterPlane != center_plane:
                continue

            # Expressions may fail to set due to circular references.
            try:
                self._template.update_object(parent, 'Thickness')
                parent.recompute()
            except Exception as e:
                App.Console.PrintWarning(f"Failed to set thickness of {self._cutout.Name} "
                                         f"to expression: {e}\n")

    def _on_changed(self):
        if self._cutout is None:
            return

        if not self._edit_mode:
            label = self.label_edit.text().strip()
            self._cutout.Label = label

        self._cutout.OutlineSketch = self.sketch_combo.currentData()
        self._cutout.recompute()

    def accept(self):
        if self._cutout.Thickness.Value == 0:
            QtWidgets.QMessageBox.warning(
                self.form, "Invalid Thickness", "Thickness must not be zero.")
            return

        self._on_changed()

        self._cutout.ViewObject.ShowInTree = True
        self._template.destroyTemplate()
        self._doc.commitTransaction()
        # Note: if you swap the recompute and the closeDialog, you can get segfaults. I don't have
        # a FreeCAD build with debug symbols but I'd like to investigate this at some point. I
        # think that some pointer related to self._doc gets invalidated while the dialog closing
        # logic takes effoct, and this races with the recompute. Just a guess.
        Gui.Control.closeDialog()

    def reject(self):
        self._doc.abortTransaction()
        Gui.Control.closeDialog()


class CreateShaperCutoutCmd:
    def GetResources(self):
        icon_path = os.path.join(os.path.dirname(__file__),
                                 "../resources/icons/cutout.svg")
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
