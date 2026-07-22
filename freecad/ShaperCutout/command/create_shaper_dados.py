# SPDX-License-Identifier: GPL-3.0-or-later

import os

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore, QtWidgets

from shaper_cutout_util import make_expr_template, is_single_selected


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


class ShaperDadosTaskPanel:
    def __init__(self, cutout, dados=None, initial_sketches=[]):
        from ShaperDados import create_uninitialized

        self._cutout = cutout
        self._doc = cutout.Document

        self.form = QtWidgets.QWidget()
        self.form.setWindowTitle("Edit Dados" if dados is not None else "Create Dados")
        layout = QtWidgets.QFormLayout(self.form)

        # Label
        self.label_edit = QtWidgets.QLineEdit()
        layout.addRow("Label:", self.label_edit)

        # Plywood plane (face selector)
        pp = cutout
        self.face_combo = QtWidgets.QComboBox()
        front = pp.FrontFace
        back = pp.BackFace
        if front:
            self.face_combo.addItem(front.Label + " (Front)", (front, True))
        if back:
            self.face_combo.addItem(back.Label + " (Back)", (back, False))
        layout.addRow("Face:", self.face_combo)

        # Depth / Width / Tolerance
        depth_widget = Gui.UiLoader().createWidget('Gui::QuantitySpinBox')
        depth_widget.setProperty('unit', 'mm')
        layout.addRow("Depth:", depth_widget)
        self._depth_widget = depth_widget

        width_widget = Gui.UiLoader().createWidget('Gui::QuantitySpinBox')
        width_widget.setProperty('unit', 'mm')
        layout.addRow("Width:", width_widget)
        self._width_widget = width_widget

        tolerance_widget = Gui.UiLoader().createWidget('Gui::QuantitySpinBox')
        tolerance_widget.setProperty('unit', 'mm')
        layout.addRow("Tolerance:", tolerance_widget)
        self._tolerance_widget = tolerance_widget

        # Sketch list with Add/Remove
        self.sketch_list = QtWidgets.QListWidget()
        self.sketch_list.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.sketch_list.setMinimumHeight(100)

        sketch_buttons = QtWidgets.QHBoxLayout()
        self.add_btn = QtWidgets.QPushButton("Add")
        self.remove_btn = QtWidgets.QPushButton("Remove")
        sketch_buttons.addWidget(self.add_btn)
        sketch_buttons.addWidget(self.remove_btn)

        layout.addRow("Sketches:", self.sketch_list)
        layout.addRow("", sketch_buttons)

        # Open transaction, setup expression template and populate dialog
        self._doc.openTransaction("Edit Dados" if dados is not None else "Create Dados")
        self._dados = dados
        if self._dados is None:
            face_data = self.face_combo.currentData()
            (face, invert) = face_data if face_data else (None, False)
            self._dados = create_uninitialized(cutout, "Dados")

        self._template = make_expr_template({
            'Depth': 'App::PropertyLength',
            'Width': 'App::PropertyLength',
            'Tolerance': 'App::PropertyLength',
        })
        self._template.set_from_object(self._dados, 'Depth', 1.0)
        self._template.set_from_object(self._dados, 'Width', 8.0)
        self._template.set_from_object(self._dados, 'Tolerance', 0.0)
        self._template.bind(depth_widget, 'Depth')
        self._template.bind(width_widget, 'Width')
        self._template.bind(tolerance_widget, 'Tolerance')
        self.label_edit.setText(self._dados.Label)

        # Set face combo from existing dados
        if dados is not None:
            for i in range(self.face_combo.count()):
                (f, inv) = self.face_combo.itemData(i)
                if f is self._dados.Face and inv == self._dados.Invert:
                    self.face_combo.setCurrentIndex(i)
                    break

        # Populate sketch list
        for sk in (self._dados.Sketches or []):
            self.sketch_list.addItem(self._make_item(sk))
        for sk in initial_sketches:
            self.sketch_list.addItem(self._make_item(sk))

        # Connect signals AFTER populating
        self.label_edit.textChanged.connect(self._on_changed)
        self.face_combo.currentIndexChanged.connect(self._on_changed)
        self._depth_widget.valueChanged.connect(self._on_changed)
        self._width_widget.valueChanged.connect(self._on_changed)
        self._tolerance_widget.valueChanged.connect(self._on_changed)
        self.add_btn.clicked.connect(self._on_add)
        self.remove_btn.clicked.connect(self._on_remove)

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
        self._dados.Label = self.label_edit.text().strip() or "Dados"
        face_data = self.face_combo.currentData()
        if face_data:
            (face, invert) = face_data
            self._dados.Face = face
            self._dados.Invert = invert
        self._dados.Sketches = self._current_sketches()
        self._template.update_object(self._dados, 'Depth')
        self._template.update_object(self._dados, 'Width')
        self._template.update_object(self._dados, 'Tolerance')

        self._dados.recompute()
        self._cutout.recompute()

    def accept(self):
        if self._template.widget_value('Depth') == 0:
            QtWidgets.QMessageBox.warning(
                self.form, "Invalid Depth", "Depth must not be zero.")
            return
        if not self._current_sketches():
            QtWidgets.QMessageBox.warning(
                self.form, "No Sketches", "Please add at least one sketch.")
            return
        self._on_changed()

        self._dados.Sketches = self._current_sketches()
        self._template.destroyTemplate()
        self._doc.commitTransaction()
        Gui.Control.closeDialog()

    def reject(self):
        self._doc.abortTransaction()
        Gui.Control.closeDialog()


class CreateShaperDadosCmd:
    def GetResources(self):
        icon_path = os.path.join(os.path.dirname(__file__),
                                 "../resources/icons/dados.svg")
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
