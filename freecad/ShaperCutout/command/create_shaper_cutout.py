# SPDX-License-Identifier: GPL-3.0-or-later

import os

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtWidgets

from shaper_cutout_util import is_single_selected, make_expr_template, move_to_root, \
    insert_if_missing, force_combo_to_value


_SUPPORTED_PLANE_TYPES = ['App::Plane', 'Part::Plane', 'Part::DatumPlane', 'PartDesign::Plane']


def _lcs_plane_of(obj):
    if obj is None or len(getattr(obj, 'InList', [])) == 0:
        return None

    if getattr(obj.InList[0], 'TypeId', '') in (
        "App::LocalCoordinateSystem",
        "Part::LocalCoordinateSystem",
        "PartDesign::CoordinateSystem"
    ):
        return obj.InList[0]
    return None


def _data_plane_of(obj):
    """Find a ShaperCutout for which this is some plane."""
    if obj is None or len(getattr(obj, 'InList', [])) == 0:
        return None

    if getattr(obj.InList[0], 'Type', '') == 'ShaperCutout':
        return obj.InList[0]
    elif getattr(obj.InList[0], 'Type', '') == 'ShaperDado':
        if getattr(obj.InList[0].InList[0], 'Type', '') == 'ShaperCutout':
            return obj.InList[0]
    return None


def _is_sketch(obj):
    return obj.TypeId in (
        'Sketcher::SketchObject',
        'Part::Part2DObject',
        'Part::Part2DObjectPython',
    )


def _internal_objects(doc):
    internal = set()
    for o in doc.Objects:
        if getattr(o, 'Type', None) == 'ShaperCutout':
            if o.FrontFace:
                internal.add(o.FrontFace)
            if o.BackFace:
                internal.add(o.BackFace)
        if getattr(o, 'Type', None) == 'ShaperDados':
            if o.DadoPlane:
                internal.add(o.DadoPlane)
            for member in o.Group:
                if member is not None and _is_sketch(member):
                    internal.add(member)
    return internal


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
        internal = _internal_objects(self._doc)
        self._all_sketches = [o for o in self._doc.Objects
                              if _is_sketch(o) and o not in internal]

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
            owner = _data_plane_of(o)
            lcs_owner = _lcs_plane_of(o)
            if owner:
                if getattr(owner, 'CenterPlane', None) == o:
                    self.plane_combo.addItem(f"{owner.Label}.{o.Label}", o)
                else:
                    continue
            elif lcs_owner:
                self.plane_combo.addItem(f"{lcs_owner.Label}.{o.Label}", o)
            else:
                self.plane_combo.addItem(o.Label, o)
        layout.addRow("Center Plane:", self.plane_combo)
        if not self._edit_mode:
            self.move_plane_check = QtWidgets.QCheckBox()
            self.move_plane_check.setChecked(False)
            layout.addRow("Move and rename plane:", self.move_plane_check)

        self.link_planes_check = QtWidgets.QCheckBox()
        layout.addRow("Link computed planes as well:", self.link_planes_check)

        # Thickness
        thickness_widget = Gui.UiLoader().createWidget('Gui::QuantitySpinBox')
        thickness_widget.setProperty('unit', 'mm')
        layout.addRow("Thickness:", thickness_widget)
        self.thickness_widget = thickness_widget

        # Sketch combo
        self.sketch_combo = QtWidgets.QComboBox()
        self.sketch_combo.addItem('(No outline sketch)', None)
        for s in self._all_sketches:
            self.sketch_combo.addItem(s.Label, s)
        layout.addRow("Outline Sketch:", self.sketch_combo)

        # Move into group checkboxes
        if not self._edit_mode:
            self.move_sketch_check = QtWidgets.QCheckBox()
            self.move_sketch_check.setChecked(False)
            layout.addRow("Move and rename sketch:", self.move_sketch_check)

        if self._edit_mode:
            self._cutout = cutout
            if cutout.CenterPlane:
                force_combo_to_value(self.plane_combo, cutout.CenterPlane)
                other1 = _data_plane_of(cutout.CenterPlane)
                other2 = _data_plane_of(cutout.BackFace)
                other3 = _data_plane_of(cutout.FrontFace)
                if other1 not in (None, self._cutout):
                    if other1 == other2 and other1 == other3:
                        self.link_planes_check.setChecked(True)

            if cutout.OutlineSketch:
                force_combo_to_value(self.sketch_combo, cutout.OutlineSketch)
        else:
            self._cutout = create_uninitialized('')
            self._cutout.ViewObject.ShowInTree = False
            current_sel = Gui.Selection.getSelection()[0]
            if getattr(current_sel, 'Type', '') == 'ShaperCutout':
                current_sel = current_sel.CenterPlane
            force_combo_to_value(self.plane_combo, current_sel)

        self.label_edit.setText(self._cutout.Label)

        # Open transaction and create/reference cutout
        self._doc.openTransaction(f"{action} Shaper Cutout")
        self._template = make_expr_template({'Thickness': 'App::PropertyLength'})
        self._template.set_from_object(cutout, 'Thickness')
        self._template.bind(self.thickness_widget, 'Thickness')

        # Record initial plane/sketch so we can detect changes on accept
        self._initial_plane = self._cutout.CenterPlane
        self._initial_sketch = self._cutout.OutlineSketch

        # Connect signals AFTER populating
        self.label_edit.textChanged.connect(self._on_changed)
        self.plane_combo.currentIndexChanged.connect(self._on_changed)
        self.sketch_combo.currentIndexChanged.connect(self._on_changed)
        self.thickness_widget.valueChanged.connect(self._on_changed)
        self.link_planes_check.checkStateChanged.connect(self._on_changed)

        self._on_changed()

    def _on_changed(self):
        if not self._edit_mode:
            label = self.label_edit.text().strip()
            self._cutout.Label = label

        if self._cutout is not None:
            self._cutout.CenterPlane = self.plane_combo.currentData()
        if self._cutout is not None:
            self._cutout.OutlineSketch = self.sketch_combo.currentData()

        # This can fail if the entered expression would cause a circular reference. This
        # isn't really our fault, though it could be caused by us setting the expression
        # to other.Thickness below. Try to warn the user here that they've made a mess.
        try:
            self._template.update_object(self._cutout, 'Thickness')
        except Exception as e:
            App.Console.PrintWarning(f"Failed to set thickness of {self._cutout.Name} "
                                     f"to expression: {e}\n")

        # Disable "link planes" iff plane does not belong to other cutout
        can_link = _data_plane_of(self.plane_combo.currentData()) not in (None, self._cutout)
        self.link_planes_check.setDisabled(not can_link)
        link_planes = self.link_planes_check.isEnabled() and self.link_planes_check.isChecked()

        if not self._edit_mode:
            # Disable "move sketch to group" iff sketch is "No outline sketch"
            self.move_sketch_check.setDisabled(self.sketch_combo.currentIndex() == 0)
            # Disable "move plane to group" iff "link planes" is checked or plane belongs to a LCS
            if link_planes:
                self.move_plane_check.setDisabled(True)
            else:
                lcs_plane = _lcs_plane_of(self.plane_combo.currentData())
                self.move_plane_check.setDisabled(lcs_plane is not None)
                self.thickness_widget.setDisabled(False)

        if link_planes:
            self.thickness_widget.setDisabled(True)

            # If the "link" checkbox is checked, delete old planes if they existed and link the new.
            other = _data_plane_of(self._cutout.CenterPlane)
            if _data_plane_of(self._cutout.BackFace) == self._cutout:
                self._doc.removeObject(self._cutout.BackFace)
            if _data_plane_of(self._cutout.FrontFace) == self._cutout:
                self._doc.removeObject(self._cutout.FrontFace)

            self._cutout.FrontFace = other.FrontFace
            self._cutout.BackFace = other.BackFace
            self._template.setExpression('Thickness', f"{other.Name}.Thickness")
        else:
            self.thickness_widget.setDisabled(False)
            # If not checked, and we had link(s) to another face, delete the links so the faces
            # will be recreated anew.
            if _data_plane_of(self._cutout.BackFace) not in (None, self._cutout):
                self._cutout.BackFace = None
                # Just clear the Thickness expression when clearing the link checkbox.
                # Arguably we should be more careful here, and clear the expression
                # only if it was the "other.Thickness" expression that we set, and we
                # should set the expression back to its previous value if there was one,
                # but manipulating expressions like this is extremely annoying and the
                # user should expect a bit of state loss if they're toggling the "Link"
                # checkbox. They can always hit Cancel to revert.
                self._template.clearExpression('Thickness')
            if _data_plane_of(self._cutout.FrontFace) not in (None, self._cutout):
                self._cutout.FrontFace = None

        self._cutout.recompute()

    def accept(self):
        link_planes = self.link_planes_check.isEnabled() and self.link_planes_check.isChecked()
        if not link_planes and self._cutout.Thickness.Value == 0:
            QtWidgets.QMessageBox.warning(
                self.form, "Invalid Thickness", "Thickness must not be zero.")
            return

        new_plane = self._cutout.CenterPlane
        new_sketch = self._cutout.OutlineSketch

        self._on_changed()

        # Move old plane/sketch out of group if they changed
        if self._initial_plane and self._initial_plane is not new_plane:
            move_to_root(self._initial_plane)
        if self._initial_sketch and self._initial_sketch is not new_sketch:
            move_to_root(self._initial_sketch)

        # Move new plane/sketch into group if checked
        if not self._edit_mode:
            mpc = self.move_plane_check
            msc = self.move_sketch_check
            if mpc.isEnabled() and mpc.isChecked() and new_plane:
                new_plane.Label = f'{self._cutout.Label}_Center'
                insert_if_missing(self._cutout, new_plane)
            if msc.isEnabled() and msc.isChecked() and new_sketch:
                new_sketch.Label = 'Outline'
                insert_if_missing(self._cutout, new_sketch)

        self._cutout.ViewObject.ShowInTree = True
        self._template.destroyTemplate()
        self._doc.commitTransaction()
        # For some reason we need to recompute the whole document here. Just recomputing the
        # cutout doesn't clear the checkmark (even though right-clicking and "Recompute" in
        # the GUI does).
        self._doc.recompute()
        # Note: if you swap the recompute and the closeDialog, you can get segfaults. I don't have
        # a FreeCAD build with debug symbols but I'd like to investigate this at some point. I
        # think that some pointer related to self._doc gets invalidated while the dialog closing
        # logic takes effoct, and this races with the recompute. Just a guess.
        Gui.Control.closeDialog()

    def reject(self):
        self._doc.abortTransaction()
        self._doc.recompute()
        Gui.Control.closeDialog()


class CreateShaperCutoutCmd:
    def GetResources(self):
        icon_path = os.path.join(os.path.dirname(__file__),
                                 "../resources/icons/cutout.svg")
        return {
            "MenuText": "Create Shaper Cutout",
            "ToolTip": "Create an empty cutout from the selected plane",
            "Pixmap": icon_path,
        }

    def IsActive(self):
        if not App.ActiveDocument:
            return False
        return is_single_selected(_SUPPORTED_PLANE_TYPES) or is_single_selected('ShaperCutout')

    def Activated(self):
        open_cutout_task_panel()
