# SPDX-License-Identifier: GPL-3.0-or-later

import os
from typing import List, Optional, Tuple

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore, QtWidgets

from .task_panel import ShaperTaskPanel
from shaper_cutout_util import _ICON_ROOT, all_objects, objects_are_parallel, parent_cutout, \
        selection, ShaperCutoutType


def _available_sketches(doc, already_linked):
    """Return sketches in doc not already in the linked set."""
    return all_objects(doc, exclude=set(already_linked)).dict[ShaperCutoutType.SKETCH]


def _cutouts_for_sketch(sketch):
    """Cutouts a sketch-only "Create Dados" could target.

    A cutout qualifies when it is parallel to the sketch (a dado must cut
    into one of its sheet faces) and the sketch is not already linked into
    one of its dados (that would silently double-cut). Empty when the
    sketch is not parallel to any cutout.
    """
    def _dados_parents(sketch):
        """The ShaperDados objects that link this sketch, oldest first.

        Each is a candidate to be "dado'd into": the sketch already cuts a
        pocket for it.
        """
        return [o for o in getattr(sketch, 'InList', [])
                if ShaperCutoutType.DADOS.is_type_of(o)]

    def _pick_dado_for_sketch(sketch, cutouts):
        """A ShaperDados the selected sketch already belongs to, if any.

        `cutouts` is the list of candidate ShaperCutouts; only dados of those
        cutouts count (a dado sketch may be shared with other cutouts whose
        dados would not be affected). Returns None when there is no match.
        """
        for dados in _dados_parents(sketch):
            if parent_cutout(dados, 'Dados') in cutouts:
                return dados
        return None

    doc = sketch.Document
    return [o for o in doc.Objects
            if ShaperCutoutType.CUTOUT.is_type_of(o)
            and objects_are_parallel(o.CenterPlane, sketch)
            and _pick_dado_for_sketch(sketch, [o]) is None]


def _selected_objects() -> Tuple[Optional[App.DocumentObject], List[App.DocumentObject]]:
    """Parse the selection for the Create Dados command.

    Returns (cutout, initial_sketches). If there is more than one cutout, or anything other
    than a cutout and sketches are selected, returns (None, []).
    """
    sel = selection()
    if sel.total_count == 0:
        return None, []

    cutouts = sel.dict[ShaperCutoutType.CUTOUT]
    sketches = sel.dict[ShaperCutoutType.SKETCH]

    if len(cutouts) > 1 or sel.total_count != len(cutouts) + len(sketches):
        return None, []

    return cutouts[0] if cutouts else None, sketches


def _choose_cutout_for_sketch(sketch, cutouts):
    """Ask the user which cutout a sketch-only "Create Dados" should target.

    Returns the chosen ShaperCutout, or None if the user cancelled.
    """
    items = [c.Label for c in cutouts]
    chosen, ok = QtWidgets.QInputDialog.getItem(
        None, "Create Dados",
        f"Which cutout should '{sketch.Label}' dado into?",
        items, 0, False)
    if not ok:
        return None
    return cutouts[items.index(chosen)]


def _check_parallel(cutout: Optional[App.DocumentObject], sketches: List[App.DocumentObject]):
    if cutout:
        for sketch in sketches:
            if not objects_are_parallel(cutout.CenterPlane, sketch):
                QtWidgets.QMessageBox.critical(
                    None, "Create Dados",
                    f"The sketch {sketch.Label} is not parallel to the cutout {cutout.Label}. "
                    "Cannot create a dado set."
                )
                return False

    if len(sketches) > 1:
        for sketch in sketches[1:]:
            if not objects_are_parallel(sketches[0], sketch):
                QtWidgets.QMessageBox.critical(
                    None, "Create Dados",
                    f"The sketch {sketch.Label} is not parallel to the sketch {sketches[0].Label}. "
                    "Cannot create a dado set."
                )

    return True


def open_dados_task_panel(cutout, dados=None, initial_sketches=[], clone_from=None):
    """Open the task panel. If dados is None, a new one will be created.

    If clone_from is given (with dados=None), the new dado set is
    pre-populated with copies of clone_from's settings (drag-and-drop clone;
    see ShaperDados.apply_clone). The clone is created immediately so the
    panel can live-edit it, and is removed again if the user cancels.
    """
    if Gui.Control.activeDialog():
        Gui.Control.closeDialog()
    panel = ShaperDadosTaskPanel(cutout, dados, initial_sketches, clone_from)
    Gui.Control.showDialog(panel)


class ShaperDadosTaskPanel(ShaperTaskPanel):
    def __init__(self, cutout, dados=None, initial_sketches=[], clone_from=None):
        self._initialized = False
        self._cutout = cutout
        super().__init__("Dado Set", dados)
        if self.is_rejected():
            # create_uninitialized_object declined (the user was told why);
            # the transaction is already aborted and the dialog won't be shown.
            return

        # A dropped dado set clones its settings into the freshly created
        # object; do this before building any widgets so they all pick up the
        # copied values.
        self._clone_mode = False
        if dados is None and clone_from is not None:
            from ShaperDados import apply_clone
            self._clone_mode = apply_clone(clone_from, self._object, cutout)
            if self._clone_mode:
                label = f"{clone_from.Label} (copy)"
                self._object.Label = label
                self.label_edit.setText(label)

        # Plywood plane (face selector)
        self.face_combo = QtWidgets.QComboBox()
        front = cutout.FrontFace
        back = cutout.BackFace
        if front:
            self.face_combo.addItem(front.Label + " (Front)", (front, True))
        if back:
            self.face_combo.addItem(back.Label + " (Back)", (back, False))
        self._main_layout.addRow("Face:", self.face_combo)

        # Set face combo from existing dados (or from the clone we just applied)
        if self._edit_mode or self._clone_mode:
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
        self._on_changed()

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
            "ToolTip": "Create a dado pocket collection on the selected ShaperCutout "
                       "(or on a cutout chosen from those parallel to the selected "
                       "sketch)",
            "Pixmap": icon_path,
            "CmdType": "AlterDoc",
        }

    def IsActive(self):
        cutout, sketches = _selected_objects()
        return cutout is not None or len(sketches) > 0

    def Activated(self):
        cutout, sketches = _selected_objects()
        if not _check_parallel(cutout, sketches):
            return

        if cutout is None:
            if not sketches:
                # Selection changed between the button lighting up and the click
                return

            cutouts = _cutouts_for_sketch(sketches[0])
            if not cutouts:
                QtWidgets.QMessageBox.critical(
                    None, "Create Dados",
                    f"The sketch '{sketches[0].Label}' is not parallel to any cutout it "
                    "could dado into. Create a cutout whose center plane is parallel "
                    "to the sketch first.")
                return
            else:
                # Pop up the dialog even if there's just one option, so the user understands
                # that he's connecting the sketch to a cutout, and that he has a choice
                cutout = _choose_cutout_for_sketch(sketches[0], cutouts)

            if cutout is None:
                return

        open_dados_task_panel(cutout, initial_sketches=sketches)
