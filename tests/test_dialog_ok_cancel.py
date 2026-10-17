# SPDX-License-Identifier: GPL-3.0-or-later
"""Open every create/edit task panel headlessly and click Okay and Cancel.

GUI-fuzzing regression net: each panel must open without raising, Cancel
(reject) must roll its transaction back cleanly (create-mode objects
disappear, edit-mode objects survive), and Okay (accept) must commit
(create-mode objects persist). QuantitySpinBox widgets and modal popups are
stubbed out, matching the headless panel fixtures in
test_task_panel_rejection.
"""

import types

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtWidgets

import ShaperCutout  # noqa: F401
import ShaperDados  # noqa: F401
import ShaperMiter  # noqa: F401
import ShaperSlot  # noqa: F401
import ShaperSvgPage
import ShaperSvgShape

from shaper_cutout_command.create_shaper_cutout import open_cutout_task_panel
from shaper_cutout_command.create_shaper_dados import open_dados_task_panel
from shaper_cutout_command.create_shaper_miter import open_miter_task_panel
from shaper_cutout_command.create_shaper_slot import open_slot_task_panel
from shaper_cutout_command.edit_shaper_svg_page import open_page_task_panel
from shaper_cutout_command.edit_shaper_svg_shape import open_shape_task_panel
from shaper_cutout_command.task_panel import ShaperTaskPanel


from util import assert_true, make_cutout, make_plane, make_sketch, mm


def _qapp():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def _stub_selection(objects):
    Gui.Selection = types.SimpleNamespace(
        getSelection=lambda: list(objects),
        getSelectionEx=lambda: [],
    )


def _unstub_selection():
    try:
        del Gui.Selection
    except AttributeError:
        pass


class _StubbedControl:
    """Headless stand-in for Gui.Control (absent in FreeCADCmd)."""

    def __init__(self):
        self.shown = []

    def activeDialog(self):
        return False

    def closeDialog(self):
        pass

    def showDialog(self, panel):
        self.shown.append(panel)


class _RecordingDoc:
    """Forwards to the real document, recording transaction calls.

    FreeCAD 27 auto-closes transactions leaked open at exit and exposes no
    document-level committed-vs-aborted state, so the only way to check what
    Okay/Cancel actually did to the undo stack is to watch the calls the
    panel makes."""

    def __init__(self, doc):
        self._real_doc = doc
        self.calls = []

    def openTransaction(self, name):
        self.calls.append(('open', name))
        return self._real_doc.openTransaction(name)

    def commitTransaction(self):
        self.calls.append(('commit',))
        return self._real_doc.commitTransaction()

    def abortTransaction(self):
        self.calls.append(('abort',))
        return self._real_doc.abortTransaction()

    def __getattr__(self, name):
        return getattr(self._real_doc, name)


class _DialogCase:
    """Stub Gui.Control so the open_* helpers record panels instead of
    showing them. open() returns the one panel the helper showed."""

    def __enter__(self):
        self.control = _StubbedControl()
        self._real = getattr(Gui, 'Control', None)
        Gui.Control = self.control
        self._panels = []
        return self

    def __exit__(self, *exc):
        # Destroy every panel's widget tree while the QApplication is alive.
        # Panels are Python objects owning C++ QWidgets; if they survive until
        # interpreter shutdown, PySide's teardown walk over them segfaults
        # (FreeCADCmd exits 1 after all tests printed Success).
        import gc
        for panel in self._panels:
            form = getattr(panel, 'form', None)
            if form is not None:
                try:
                    if isinstance(form, list):
                        for w in form:
                            w.deleteLater()
                    else:
                        form.deleteLater()
                except RuntimeError:
                    pass  # already destroyed with a parent
        gc.collect()
        if self._real is not None:
            Gui.Control = self._real
        else:
            try:
                del Gui.Control
            except AttributeError:
                pass

    def open(self, open_fn, *args, **kwargs):
        self.control.shown.clear()
        open_fn(*args, **kwargs)
        assert_true(len(self.control.shown) == 1,
                    f"expected exactly one panel shown, "
                    f"got {len(self.control.shown)}")
        panel = self.control.shown[0]
        self._panels.append(panel)
        # Swap in a transaction-recording document so tests can assert on
        # what accept()/reject() did to the undo stack.
        panel._doc = _RecordingDoc(panel._doc)
        return panel

    def tx_calls(self, panel):
        """The (recorded) transaction calls the panel made since open()."""
        doc = panel._doc
        assert_true(isinstance(doc, _RecordingDoc),
                    "panel document is not the recording proxy")
        return list(doc.calls)


class _StubbedQuantityWidgets:
    """Replace QuantitySpinBox creation (needs a real Gui) with plain
    widgets."""

    def __enter__(self):
        self._real = ShaperTaskPanel._quantity_widget
        ShaperTaskPanel._quantity_widget = \
            lambda self, prop, minimum=None, maximum=None: QtWidgets.QWidget()
        return self

    def __exit__(self, *exc):
        ShaperTaskPanel._quantity_widget = self._real


class _StubbedDialogs:
    """Capture QMessageBox popups so panel flows never block on a modal."""

    def __init__(self):
        self.messages = []
        self._real = (QtWidgets.QMessageBox.warning,
                      QtWidgets.QMessageBox.critical,
                      QtWidgets.QMessageBox.information)

    def __enter__(self):
        def make(kind):
            def handler(parent, title, text, *a, **k):
                self.messages.append((kind, title, str(text)))
                return QtWidgets.QMessageBox.StandardButton.Ok
            return staticmethod(handler)

        QtWidgets.QMessageBox.warning = make('warning')
        QtWidgets.QMessageBox.critical = make('critical')
        QtWidgets.QMessageBox.information = make('information')
        return self

    def __exit__(self, *exc):
        (QtWidgets.QMessageBox.warning,
         QtWidgets.QMessageBox.critical,
         QtWidgets.QMessageBox.information) = self._real


def _of_type(doc, ty_name):
    # Count by the object's Type attribute. ShaperCutoutType.type_of has no
    # branches for miters/slots (they classify as OTHER), so the enum can't
    # be used here.
    return [o for o in doc.Objects if getattr(o, 'Type', '') == ty_name]


def _cutout_fixture(doc):
    """A cutout with an outline sketch and materialized front/back faces."""
    plane = make_plane(doc, "Plane")
    sketch = make_sketch(doc, plane, "Outline")
    cutout = make_cutout(doc, plane, "Cutout")
    cutout.OutlineSketch = sketch
    doc.recompute()
    return plane, sketch, cutout


def _slot_fixture(doc):
    """Two orthogonal cutouts + an interface plane (valid slot geometry)."""
    p1 = make_plane(doc, "P1", origin=(0, 0, 0), rot=(0, 0, 0))
    p2 = make_plane(doc, "P2", origin=(0, 0, 0), rot=(0, 0, 90))
    s1 = make_sketch(doc, p1, "P1_outline", closed=True)
    s2 = make_sketch(doc, p2, "P2_outline", closed=True)
    c1 = make_cutout(doc, p1, "C1")
    c1.OutlineSketch = s1
    c2 = make_cutout(doc, p2, "C2")
    c2.OutlineSketch = s2
    ifp = make_plane(doc, "IFP", origin=(0, 0, mm(2)), rot=(0, 90, 0))
    doc.recompute()
    return c1, c2, ifp


# ============================================================================
# Cutout panel
# ============================================================================

def test_cutout_create_okay_and_cancel():
    _qapp()
    doc = App.newDocument("dlg_cutout_create")
    try:
        plane = make_plane(doc, "Plane")
        doc.recompute()
        with _DialogCase() as dlg, _StubbedQuantityWidgets(), _StubbedDialogs():
            _stub_selection([plane])
            try:
                panel = dlg.open(open_cutout_task_panel)
                assert_true(len(_of_type(doc, "ShaperCutout")) == 1,
                            "create panel made the cutout")
                panel.reject()
                _tx = dlg.tx_calls(panel)
                assert_true(_tx == [("abort",)],
                            f"cancel should abort the panel transaction, got {_tx}")
                assert_true(_of_type(doc, "ShaperCutout") == [],
                            "cancel removed the created cutout")

                panel = dlg.open(open_cutout_task_panel)
                panel.accept()
                _tx = dlg.tx_calls(panel)
                assert_true(_tx == [("commit",)],
                            f"okay should commit the panel transaction, got {_tx}")
                assert_true(len(_of_type(doc, "ShaperCutout")) == 1,
                            "okay kept the created cutout")
            finally:
                _unstub_selection()
    finally:
        App.closeDocument(doc.Name)


def test_cutout_edit_okay_and_cancel():
    _qapp()
    doc = App.newDocument("dlg_cutout_edit")
    try:
        _, _, cutout = _cutout_fixture(doc)
        with _DialogCase() as dlg, _StubbedQuantityWidgets(), _StubbedDialogs():
            panel = dlg.open(open_cutout_task_panel, cutout)
            assert_true(panel._object is cutout,
                        "edit panel edits the existing cutout")
            panel.reject()
            _tx = dlg.tx_calls(panel)
            assert_true(_tx == [("abort",)],
                        f"cancel should abort the panel transaction, got {_tx}")
            assert_true(cutout in doc.Objects, "cancel keeps the cutout")

            panel = dlg.open(open_cutout_task_panel, cutout)
            panel.accept()
            _tx = dlg.tx_calls(panel)
            assert_true(_tx == [("commit",)],
                        f"okay should commit the panel transaction, got {_tx}")
            assert_true(cutout in doc.Objects, "okay keeps the cutout")
    finally:
        App.closeDocument(doc.Name)


# ============================================================================
# Dados panel
# ============================================================================

def test_dados_create_okay_and_cancel():
    _qapp()
    doc = App.newDocument("dlg_dados_create")
    try:
        plane, _sketch, cutout = _cutout_fixture(doc)
        dsk = make_sketch(doc, plane, "DadoSketch")
        doc.recompute()
        with _DialogCase() as dlg, _StubbedQuantityWidgets(), _StubbedDialogs():
            panel = dlg.open(open_dados_task_panel, cutout,
                             initial_sketches=[dsk])
            assert_true(len(_of_type(doc, "ShaperDados")) == 1,
                        "create panel made the dados")
            panel.reject()
            _tx = dlg.tx_calls(panel)
            assert_true(_tx == [("abort",)],
                        f"cancel should abort the panel transaction, got {_tx}")
            assert_true(_of_type(doc, "ShaperDados") == [],
                        "cancel removed the created dados")

            panel = dlg.open(open_dados_task_panel, cutout,
                             initial_sketches=[dsk])
            panel.accept()
            _tx = dlg.tx_calls(panel)
            assert_true(_tx == [("commit",)],
                        f"okay should commit the panel transaction, got {_tx}")
            assert_true(len(_of_type(doc, "ShaperDados")) == 1,
                        "okay kept the created dados")
    finally:
        App.closeDocument(doc.Name)


def test_dados_edit_okay_and_cancel():
    _qapp()
    doc = App.newDocument("dlg_dados_edit")
    try:
        plane, _sketch, cutout = _cutout_fixture(doc)
        dsk = make_sketch(doc, plane, "DadoSketch")
        dados = ShaperDados.create_uninitialized(cutout, "Dados")
        dados.Face = cutout.FrontFace
        dados.Invert = True
        dados.Sketches = [dsk]
        doc.recompute()
        with _DialogCase() as dlg, _StubbedQuantityWidgets(), _StubbedDialogs():
            panel = dlg.open(open_dados_task_panel, cutout, dados=dados)
            assert_true(panel._object is dados,
                        "edit panel edits the existing dados")
            panel.reject()
            _tx = dlg.tx_calls(panel)
            assert_true(_tx == [("abort",)],
                        f"cancel should abort the panel transaction, got {_tx}")
            assert_true(dados in doc.Objects, "cancel keeps the dados")

            panel = dlg.open(open_dados_task_panel, cutout, dados=dados)
            panel.accept()
            _tx = dlg.tx_calls(panel)
            assert_true(_tx == [("commit",)],
                        f"okay should commit the panel transaction, got {_tx}")
            assert_true(dados in doc.Objects, "okay keeps the dados")
    finally:
        App.closeDocument(doc.Name)


# ============================================================================
# Miter panel
# ============================================================================

def test_miter_create_okay_and_cancel():
    _qapp()
    doc = App.newDocument("dlg_miter_create")
    try:
        _plane, _sketch, cutout = _cutout_fixture(doc)
        with _DialogCase() as dlg, _StubbedQuantityWidgets(), _StubbedDialogs():
            panel = dlg.open(open_miter_task_panel, cutout)
            assert_true(len(_of_type(doc, "ShaperMiter")) == 1,
                        "create panel made the miter")
            panel.reject()
            _tx = dlg.tx_calls(panel)
            assert_true(_tx == [("abort",)],
                        f"cancel should abort the panel transaction, got {_tx}")
            assert_true(_of_type(doc, "ShaperMiter") == [],
                        "cancel removed the created miter")

            panel = dlg.open(open_miter_task_panel, cutout)
            assert_true(panel.edge_list.count() > 0,
                        "edge list populated from the outline sketch")
            panel.edge_list.item(0).setSelected(True)
            panel._on_changed()
            panel.accept()
            _tx = dlg.tx_calls(panel)
            assert_true(_tx == [("commit",)],
                        f"okay should commit the panel transaction, got {_tx}")
            assert_true(len(_of_type(doc, "ShaperMiter")) == 1,
                        "okay kept the created miter")
    finally:
        App.closeDocument(doc.Name)


def test_miter_edit_okay_and_cancel():
    _qapp()
    doc = App.newDocument("dlg_miter_edit")
    try:
        _plane, sketch, cutout = _cutout_fixture(doc)
        miter = ShaperMiter.create(
            cutout=cutout, edges=[(sketch, ['Edge1'])], angle=45.0,
            miter_axis="Center", name="Miter")
        doc.recompute()
        with _DialogCase() as dlg, _StubbedQuantityWidgets(), _StubbedDialogs():
            panel = dlg.open(open_miter_task_panel, cutout, miter)
            assert_true(panel._object is miter,
                        "edit panel edits the existing miter")
            panel.reject()
            _tx = dlg.tx_calls(panel)
            assert_true(_tx == [("abort",)],
                        f"cancel should abort the panel transaction, got {_tx}")
            assert_true(miter in doc.Objects, "cancel keeps the miter")

            panel = dlg.open(open_miter_task_panel, cutout, miter)
            panel.accept()
            _tx = dlg.tx_calls(panel)
            assert_true(_tx == [("commit",)],
                        f"okay should commit the panel transaction, got {_tx}")
            assert_true(miter in doc.Objects, "okay keeps the miter")
    finally:
        App.closeDocument(doc.Name)


# ============================================================================
# Slot panel
# ============================================================================

def test_slot_create_okay_and_cancel():
    _qapp()
    doc = App.newDocument("dlg_slot_create")
    try:
        c1, c2, ifp = _slot_fixture(doc)
        with _DialogCase() as dlg, _StubbedQuantityWidgets(), _StubbedDialogs():
            _stub_selection([c1, c2, ifp])
            try:
                panel = dlg.open(open_slot_task_panel)
                assert_true(len(_of_type(doc, "ShaperSlot")) == 1,
                            "create panel made the slot")
                panel.reject()
                _tx = dlg.tx_calls(panel)
                assert_true(_tx == [("abort",)],
                            f"cancel should abort the panel transaction, got {_tx}")
                assert_true(_of_type(doc, "ShaperSlot") == [],
                            "cancel removed the created slot")

                panel = dlg.open(open_slot_task_panel)
                panel.accept()
                _tx = dlg.tx_calls(panel)
                assert_true(_tx == [("commit",)],
                            f"okay should commit the panel transaction, got {_tx}")
                assert_true(len(_of_type(doc, "ShaperSlot")) == 1,
                            "okay kept the created slot")
            finally:
                _unstub_selection()
    finally:
        App.closeDocument(doc.Name)


def test_slot_edit_okay_and_cancel():
    _qapp()
    doc = App.newDocument("dlg_slot_edit")
    try:
        c1, c2, ifp = _slot_fixture(doc)
        slot = ShaperSlot.create_uninitialized(c1, c2, ifp, "Slot")
        doc.recompute()
        with _DialogCase() as dlg, _StubbedQuantityWidgets(), _StubbedDialogs():
            panel = dlg.open(open_slot_task_panel, slot)
            assert_true(panel._object is slot,
                        "edit panel edits the existing slot")
            panel.reject()
            _tx = dlg.tx_calls(panel)
            assert_true(_tx == [("abort",)],
                        f"cancel should abort the panel transaction, got {_tx}")
            assert_true(slot in doc.Objects, "cancel keeps the slot")

            panel = dlg.open(open_slot_task_panel, slot)
            panel.accept()
            _tx = dlg.tx_calls(panel)
            assert_true(_tx == [("commit",)],
                        f"okay should commit the panel transaction, got {_tx}")
            assert_true(slot in doc.Objects, "okay keeps the slot")
    finally:
        App.closeDocument(doc.Name)


# ============================================================================
# SVG page / shape panels (edit-only)
# ============================================================================

def test_svg_page_edit_okay_and_cancel():
    _qapp()
    doc = App.newDocument("dlg_svg_page_edit")
    try:
        page = ShaperSvgPage.create("Page")
        doc.recompute()
        with _DialogCase() as dlg, _StubbedQuantityWidgets(), _StubbedDialogs():
            panel = dlg.open(open_page_task_panel, page)
            assert_true(panel._object is page,
                        "edit panel edits the existing page")
            panel.reject()
            _tx = dlg.tx_calls(panel)
            assert_true(_tx == [("abort",)],
                        f"cancel should abort the panel transaction, got {_tx}")
            assert_true(page in doc.Objects, "cancel keeps the page")

            panel = dlg.open(open_page_task_panel, page)
            panel.accept()
            _tx = dlg.tx_calls(panel)
            assert_true(_tx == [("commit",)],
                        f"okay should commit the panel transaction, got {_tx}")
            assert_true(page in doc.Objects, "okay keeps the page")
    finally:
        App.closeDocument(doc.Name)


def test_svg_shape_edit_okay_and_cancel():
    _qapp()
    doc = App.newDocument("dlg_svg_shape_edit")
    try:
        page = ShaperSvgPage.create("Page")
        plane = make_plane(doc, "Plane")
        sketch = make_sketch(doc, plane, "Rect")
        shape = ShaperSvgShape.create(page, sketch, "RectShape")
        doc.recompute()
        with _DialogCase() as dlg, _StubbedQuantityWidgets(), _StubbedDialogs():
            panel = dlg.open(open_shape_task_panel, shape)
            assert_true(panel._object is shape,
                        "edit panel edits the existing shape")
            panel.reject()
            _tx = dlg.tx_calls(panel)
            assert_true(_tx == [("abort",)],
                        f"cancel should abort the panel transaction, got {_tx}")
            assert_true(shape in doc.Objects, "cancel keeps the shape")

            panel = dlg.open(open_shape_task_panel, shape)
            panel.accept()
            _tx = dlg.tx_calls(panel)
            assert_true(_tx == [("commit",)],
                        f"okay should commit the panel transaction, got {_tx}")
            assert_true(shape in doc.Objects, "okay keeps the shape")
    finally:
        App.closeDocument(doc.Name)


def register_tests(all_tests):
    all_tests.append(test_cutout_create_okay_and_cancel)
    all_tests.append(test_cutout_edit_okay_and_cancel)
    all_tests.append(test_dados_create_okay_and_cancel)
    all_tests.append(test_dados_edit_okay_and_cancel)
    all_tests.append(test_miter_create_okay_and_cancel)
    all_tests.append(test_miter_edit_okay_and_cancel)
    all_tests.append(test_slot_create_okay_and_cancel)
    all_tests.append(test_slot_edit_okay_and_cancel)
    all_tests.append(test_svg_page_edit_okay_and_cancel)
    all_tests.append(test_svg_shape_edit_okay_and_cancel)
