# SPDX-License-Identifier: GPL-3.0-or-later

import os

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtWidgets

import ShaperCutout as CutoutModule
from util import make_expr_template, move_to_root, insert_if_missing


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
        self._doc = App.ActiveDocument
        self._edit_mode = cutout is not None

        # Collect available planes and sketches
        internal = _internal_objects(self._doc)
        self._all_planes = [o for o in self._doc.Objects
                            if o.TypeId == 'Part::DatumPlane' and o not in internal]
        self._all_sketches = [o for o in self._doc.Objects
                              if _is_sketch(o) and o not in internal]

        # Build UI
        self.form = QtWidgets.QWidget()
        self.form.setWindowTitle("Edit Cutout" if self._edit_mode else "Create Shaper Cutout")
        layout = QtWidgets.QFormLayout(self.form)

        # Label
        self.label_edit = QtWidgets.QLineEdit()
        self.label_edit.setEnabled(not self._edit_mode)
        layout.addRow("Label:", self.label_edit)

        # Plane combo
        self.plane_combo = QtWidgets.QComboBox()
        for p in self._all_planes:
            self.plane_combo.addItem(p.Label, p)
        layout.addRow("Center Plane:", self.plane_combo)

        # Sketch combo
        self.sketch_combo = QtWidgets.QComboBox()
        for s in self._all_sketches:
            self.sketch_combo.addItem(s.Label, s)
        layout.addRow("Outline Sketch:", self.sketch_combo)

        # Move into group checkboxes
        self.move_sketch_check = QtWidgets.QCheckBox()
        self.move_sketch_check.setChecked(True)
        layout.addRow("Move sketch into group:", self.move_sketch_check)

        self.move_plane_check = QtWidgets.QCheckBox()
        self.move_plane_check.setChecked(False)
        layout.addRow("Move plane into group:", self.move_plane_check)

        # Thickness
        thickness_widget = Gui.UiLoader().createWidget('Gui::QuantitySpinBox')
        thickness_widget.setProperty('unit', 'mm')
        layout.addRow("Thickness:", thickness_widget)
        self._thickness_widget = thickness_widget

        # Open transaction and create/reference cutout
        self._doc.openTransaction(
            "Edit Shaper Cutout" if self._edit_mode else "Create Shaper Cutout")
        self._template = make_expr_template({'Thickness': 'App::PropertyLength'})
        self._template.set_from_object(cutout, 'Thickness')
        self._template.bind(thickness_widget, 'Thickness')

        if self._edit_mode:
            self._cutout = cutout
            # Populate fields from existing cutout
            self.label_edit.setText(cutout.Label)
            cp = cutout.CenterPlane
            if cp:
                idx = self.plane_combo.findData(cp)
                if idx < 0:
                    self.plane_combo.insertItem(0, cp.Label, cp)
                    idx = 0
                self.plane_combo.setCurrentIndex(idx)
            sk = cutout.OutlineSketch
            if sk:
                idx = self.sketch_combo.findData(sk)
                if idx < 0:
                    self.sketch_combo.insertItem(0, sk.Label, sk)
                    idx = 0
                self.sketch_combo.setCurrentIndex(idx)
            # Reflect current group membership
            self.move_plane_check.setChecked(cp in cutout.Group if cp else False)
            self.move_sketch_check.setChecked(sk in cutout.Group if sk else False)
        else:
            self._cutout = CutoutModule.create(
                obj_name='',
                center_plane=self.plane_combo.currentData(),
                outline_sketch=self.sketch_combo.currentData(),
                thickness=0,
                own_sketch=False,
                own_plane=False,
            )
            self.label_edit.setText(self._cutout.Label)

        # Record initial plane/sketch so we can detect changes on accept
        self._initial_plane = self._cutout.CenterPlane
        self._initial_sketch = self._cutout.OutlineSketch

        # Connect signals AFTER populating
        self.label_edit.textChanged.connect(self._on_changed)
        self.plane_combo.currentIndexChanged.connect(self._on_changed)
        self.sketch_combo.currentIndexChanged.connect(self._on_changed)
        self._thickness_widget.valueChanged.connect(self._on_changed)

    def _on_changed(self):
        if not self._edit_mode:
            label = self.label_edit.text().strip()
            if label:
                self._cutout.Label = label

        self._cutout.CenterPlane = self.plane_combo.currentData()
        self._cutout.OutlineSketch = self.sketch_combo.currentData()
        self._template.update_object(self._cutout, 'Thickness')

        self._cutout.recompute()

    def accept(self):
        if self._cutout.Thickness.Value == 0:
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
        if self.move_plane_check.isChecked() and new_plane:
            insert_if_missing(self._cutout, new_plane)
        if self.move_sketch_check.isChecked() and new_sketch:
            insert_if_missing(self._cutout, new_sketch)

        self._template.destroyTemplate()
        self._doc.commitTransaction()
        Gui.Control.closeDialog()

    def reject(self):
        self._doc.abortTransaction()
        Gui.Control.closeDialog()


class createShaperCutoutCmd:
    def GetResources(self):
        icon_path = os.path.join(os.path.dirname(__file__),
                                 "../resources/icons/cutout.svg")
        return {
            "MenuText": "Create Shaper Cutout",
            "ToolTip": "Create cutout with a given thickness outlined by a given Sketch",
            "Pixmap": icon_path,
        }

    def IsActive(self):
        if not App.ActiveDocument:
            return False
        doc = App.ActiveDocument
        excluded = _internal_objects(doc)
        has_plane = any(o for o in doc.Objects
                        if o.TypeId == 'Part::DatumPlane' and o not in excluded)
        has_sketch = any(o for o in doc.Objects
                         if _is_sketch(o) and o not in excluded)
        return has_plane and has_sketch

    def Activated(self):
        open_cutout_task_panel()
