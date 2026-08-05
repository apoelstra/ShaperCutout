# SPDX-License-Identifier: GPL-3.0-or-later

import os

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore, QtWidgets

from .task_panel import ShaperTaskPanel
from shaper_cutout_util import _ICON_ROOT, is_single_selected


def _is_sketch(obj):
    return obj.TypeId in (
        'Sketcher::SketchObject',
        'Part::Part2DObject',
        'Part::Part2DObjectPython',
    )


def _available_sketches(doc, already_linked):
    """Return sketches in doc not already in the linked set."""
    linked_set = set(already_linked)
    return [o for o in doc.Objects if _is_sketch(o) and o not in linked_set]


def open_dados_task_panel(cutout, dados=None, initial_sketches=[]):
    """Open the task panel. If dados is None, a new one will be created."""
    if Gui.Control.activeDialog():
        Gui.Control.closeDialog()
    panel = ShaperDadosTaskPanel(cutout, dados, initial_sketches)
    Gui.Control.showDialog(panel)


class ShaperDadosTaskPanel(ShaperTaskPanel):
    def __init__(self, cutout, dados=None, initial_sketches=[]):
        self._initialized = False
        self._cutout = cutout
        super().__init__("Dado Set", dados)

        # Plywood plane (face selector)
        self.face_combo = QtWidgets.QComboBox()
        front = cutout.FrontFace
        back = cutout.BackFace
        if front:
            self.face_combo.addItem(front.Label + " (Front)", (front, True))
        if back:
            self.face_combo.addItem(back.Label + " (Back)", (back, False))
        self._main_layout.addRow("Face:", self.face_combo)

        # Set face combo from existing dados
        if self._edit_mode:
            for i in range(self.face_combo.count()):
                (f, inv) = self.face_combo.itemData(i)
                if f is self._object.Face and inv == self._object.Invert:
                    self.face_combo.setCurrentIndex(i)
                    break
        else:
            face_data = self.face_combo.currentData()
            (face, invert) = face_data if face_data else (None, False)

        # Depth / Width / Tolerance
        self._main_layout.addRow(
            "Depth:",
            self._quantity_widget('Depth', minimum=0),
        )
        self._main_layout.addRow(
            "Width:",
            self._quantity_widget('Width', minimum=1e-7),
        )
        self._main_layout.addRow(
            "Tolerance:",
            self._quantity_widget('Tolerance', minimum=0),
        )

        # Autodrill section
        autodrill_group = QtWidgets.QGroupBox("Autodrill")
        autodrill_layout = QtWidgets.QFormLayout(autodrill_group)
        # Max Holes Per Line - integer spinbox
        self.max_holes_spin = QtWidgets.QSpinBox()
        self.max_holes_spin.setMinimum(0)
        self.max_holes_spin.setValue(self._object.MaxHolesPerLine)
        self.max_holes_spin.valueChanged.connect(self._on_max_holes_changed)
        autodrill_layout.addRow("Max Holes Per Line:", self.max_holes_spin)

        autodrill_layout.addRow(
            "Hole Diameter:",
            self._quantity_widget('HoleDiameter', minimum=1e-7),
        )
        autodrill_layout.addRow(
            "Min Hole Distance:",
            self._quantity_widget('MinHoleDistance', minimum=1e-7),
        )
        autodrill_layout.addRow(
            "End Distance:",
            self._quantity_widget('EndDistance', minimum=0),
        )
        self._main_layout.addRow(autodrill_group)

        # Sketch list with Add/Remove
        self.sketch_list = QtWidgets.QListWidget()
        self.sketch_list.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.sketch_list.setMinimumHeight(100)

        sketch_buttons = QtWidgets.QHBoxLayout()
        self.add_btn = QtWidgets.QPushButton("Add")
        self.remove_btn = QtWidgets.QPushButton("Remove")
        sketch_buttons.addWidget(self.add_btn)
        sketch_buttons.addWidget(self.remove_btn)

        self._main_layout.addRow("Sketches:", self.sketch_list)
        self._main_layout.addRow("", sketch_buttons)

        # Populate sketch list
        for sk in (self._object.Sketches or []):
            self.sketch_list.addItem(self._make_item(sk))
        for sk in initial_sketches:
            self.sketch_list.addItem(self._make_item(sk))

        # Connect signals AFTER populating
        self.label_edit.textChanged.connect(self._on_label_changed)
        self.face_combo.currentIndexChanged.connect(self._on_changed)
        self.add_btn.clicked.connect(self._on_add)
        self.remove_btn.clicked.connect(self._on_remove)

        self._initialized = True

    def create_uninitialized_object(self) -> App.DocumentObject:
        from ShaperDados import create_uninitialized
        return create_uninitialized(self._cutout, "Dados")

    def recompute_objects(self, updated_prop_name: str):
        if self._initialized:
            self._object.recompute()
            self._cutout.recompute()

    def _on_max_holes_changed(self):
        if self._object is None:
            return
        self._object.MaxHolesPerLine = self.max_holes_spin.value()
        self.recompute_objects('MaxHolesPerLine')

    def _make_item(self, sketch):
        item = QtWidgets.QListWidgetItem(sketch.Label)
        item.setData(QtCore.Qt.UserRole, sketch)
        return item

    def _current_sketches(self):
        return [self.sketch_list.item(i).data(QtCore.Qt.UserRole)
                for i in range(self.sketch_list.count())]

    def _on_add(self):
        available = _available_sketches(self._doc, self._current_sketches())
        if not available:
            QtWidgets.QMessageBox.information(
                self.form, "No Sketches", "No unlinked sketches available.")
            return
        items = [o.Label for o in available]
        chosen, ok = QtWidgets.QInputDialog.getItem(
            self.form, "Add Sketch", "Select sketch:", items, 0, False)
        if not ok:
            return
        sketch = available[items.index(chosen)]
        self.sketch_list.addItem(self._make_item(sketch))
        self._on_changed()

    def _on_remove(self):
        for item in self.sketch_list.selectedItems():
            self.sketch_list.takeItem(self.sketch_list.row(item))
        self._on_changed()

    def _on_changed(self):
        face_data = self.face_combo.currentData()
        if face_data:
            (face, invert) = face_data
            self._object.Face = face
            self._object.Invert = invert
        self._object.Sketches = self._current_sketches()
        self.recompute_objects(None)

    def accept(self):
        if not self._current_sketches():
            QtWidgets.QMessageBox.warning(
                self.form, "No Sketches", "Please add at least one sketch.")
            return

        super().accept()


class CreateShaperDadosCmd:
    def GetResources(self):
        icon_path = os.path.join(_ICON_ROOT, "dados.svg")
        return {
            "MenuText": "Create Dados",
            "ToolTip": "Create a dado pocket collection on the selected ShaperCutout",
            "Pixmap": icon_path,
        }

    def IsActive(self):
        if not App.ActiveDocument:
            return False
        return is_single_selected('ShaperCutout')

    def Activated(self):
        sel = Gui.Selection.getSelection()
        if len(sel) == 0 or getattr(sel[0], 'Type', '') != 'ShaperCutout':
            return
        open_dados_task_panel(sel[0])
