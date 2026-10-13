# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests: the Create Dados dialog vs sketches attached to the cutout.

A dado sketch that stays attached to a face of the ShaperCutout itself
creates a dependency cycle (sketch -> cutout -> dados -> sketch), which
leaves the cutout permanently touched and unrecomputable. When such a
sketch enters the Create Dados dialog (dropped onto the cutout, or added
via the Add button), the user is offered to re-attach it to the dado's
face plane, preserving the sketch's global placement; declining cancels
the operation.
"""

import types

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtWidgets

import ShaperCutout  # noqa: F401  (registers the ShaperCutout type)
import ShaperDados  # noqa: F401  (registers the ShaperDados type)

from shaper_cutout_command.create_shaper_dados import (
    ShaperDadosTaskPanel, open_dados_task_panel)
from shaper_cutout_command.task_panel import ShaperTaskPanel
from shaper_cutout_util import attachment_target, reattach_to_plane

from util import assert_true, assert_volume, make_cutout, make_plane, \
    make_sketch, mm


def _qapp():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def _stub_selection(objects):
    Gui.Selection = types.SimpleNamespace(
        getSelection=lambda: list(objects),
        getSelectionEx=lambda: [],
    )


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


class _StubbedQuestion:
    """Capture QMessageBox.question calls, answering from a canned list."""

    def __init__(self, answers):
        self.answers = list(answers)
        self.calls = []
        self._real = QtWidgets.QMessageBox.question
        self._real_warning = QtWidgets.QMessageBox.warning

    def __enter__(self):
        def fake(parent, title, text, *a, **k):
            self.calls.append((title, str(text)))
            return self.answers.pop(0)

        QtWidgets.QMessageBox.question = staticmethod(fake)
        QtWidgets.QMessageBox.warning = staticmethod(fake)
        return self

    def __exit__(self, *exc):
        QtWidgets.QMessageBox.question = self._real
        QtWidgets.QMessageBox.warning = self._real_warning


class _StubbedGetItem:
    """Capture QInputDialog.getItem, picking via a callback over the items."""

    def __init__(self, pick):
        self.pick = pick
        self._real = QtWidgets.QInputDialog.getItem

    def __enter__(self):
        def fake(parent, title, label, items, current=0, selectable=True, *a, **k):
            idx = self.pick(list(items))
            return (items[idx], True)

        QtWidgets.QInputDialog.getItem = staticmethod(fake)
        return self

    def __exit__(self, *exc):
        QtWidgets.QInputDialog.getItem = self._real


def _face_sub(cutout, face_plane):
    """The 'FaceN' subelement name of the cutout's sheet face lying on
    face_plane's side of the sheet."""
    n = cutout.CenterPlane.getGlobalPlacement().Rotation.multVec(
        App.Vector(0, 0, 1))
    center = cutout.CenterPlane.getGlobalPlacement().Base
    half = cutout.Thickness.Value / 2.0
    want = (face_plane.getGlobalPlacement().Base - center).dot(n)
    for i, f in enumerate(cutout.Shape.Faces, 1):
        u, v = f.Surface.parameter(f.CenterOfGravity)
        fn = f.normalAt(u, v)
        d = (f.CenterOfGravity - center).dot(n)
        if abs(fn.dot(n)) > 0.999 and abs(d - want) < 1e-6 \
                and abs(abs(d) - half) < 1e-6:
            return f"Face{i}"
    raise AssertionError("no sheet face found for the given face plane")


def _rect_sketch(doc, name, w=mm(0.4), h=mm(0.8)):
    """A small closed rectangle sketch (no attachment), for dado pockets."""
    sketch = doc.addObject("Sketcher::SketchObject", name)
    sketch.Label = name
    p1 = App.Vector(-w / 2, -h / 2, 0)
    p2 = App.Vector(w / 2, -h / 2, 0)
    p3 = App.Vector(w / 2, h / 2, 0)
    p4 = App.Vector(-w / 2, h / 2, 0)
    for a, b in [(p1, p2), (p2, p3), (p3, p4), (p4, p1)]:
        sketch.addGeometry(Part_LineSegment(a, b), False)
    return sketch


def Part_LineSegment(a, b):
    import Part
    return Part.LineSegment(a, b)


def _cutout_with_face_sketch(doc, name):
    """A cutout plus a closed sketch attached to its front sheet face."""
    plane = make_plane(doc, "Plane1")
    outline = make_sketch(doc, plane, "Outline")
    cutout = make_cutout(doc, plane, name)
    cutout.OutlineSketch = outline
    doc.recompute()

    dsk = _rect_sketch(doc, "DadoSketch")
    dsk.AttachmentSupport = [(cutout, (_face_sub(cutout, cutout.FrontFace),))]
    dsk.MapMode = 'FlatFace'
    doc.recompute()
    return cutout, dsk


def test_drop_sketch_on_face_reattaches_to_face_plane():
    """Dropping a face-attached sketch (Create Dados with initial_sketches):
    with consent the sketch is re-attached to the dado's face plane, the
    global placement is preserved, and the dado actually cuts."""
    _qapp()
    doc = App.newDocument("dados_face_reattach")
    control = _StubbedControl()
    old_control = getattr(Gui, 'Control', None)
    old_widget = ShaperTaskPanel._quantity_widget
    ShaperTaskPanel._quantity_widget = \
        lambda self, prop, minimum=None, maximum=None: QtWidgets.QWidget()
    Gui.Control = control
    try:
        cutout, dsk = _cutout_with_face_sketch(doc, "Cutout")
        base_volume = sum(s.Volume for s in cutout.Shape.Solids)
        g_before = App.Placement(dsk.getGlobalPlacement())

        with _StubbedQuestion([QtWidgets.QMessageBox.Yes]) as asks:
            open_dados_task_panel(cutout, initial_sketches=[dsk])

        assert_true(len(control.shown) == 1, "panel was shown")
        assert_true(len(asks.calls) == 1,
                    f"one question expected, got {asks.calls}")
        assert_true("dependency cycle" in asks.calls[0][1],
                    f"question should explain the cycle: {asks.calls[0]}")
        assert_true(dsk.Label in asks.calls[0][1], "question names the sketch")

        target = attachment_target(dsk)
        assert_true(target is not None and target[0] is cutout.FrontFace
                    and target[1] == '',
                    f"sketch re-attached to FrontFace, got {target}")
        entry = dsk.AttachmentSupport[0]
        assert_true(entry[0] is cutout.FrontFace and entry[1][0] == '',
                    f"support is (FrontFace, ''): {entry}")
        assert_true(dsk.MapMode == 'FlatFace', "map mode is FlatFace")

        g_after = App.Placement(dsk.getGlobalPlacement())
        assert_true((g_after.Base - g_before.Base).Length < 1e-9,
                    f"global placement preserved: {g_before.Base} -> {g_after.Base}")

        # The document must not be cyclic: a full recompute leaves the
        # cutout up to date.
        doc.recompute()
        assert_true('Touched' not in cutout.State,
                    f"cutout still touched after recompute: {cutout.State}")

        # And the dado cuts: give it a depth and check the exact volume.
        panel = control.shown[0]
        assert_true(not panel.is_rejected(), "panel not rejected")
        dados = panel._object
        assert_true(dados.Face is cutout.FrontFace, "dado on the front face")
        assert_true(list(dados.Sketches) == [dsk], "sketch linked into dados")
        dados.Depth = mm(0.25)
        dados.recompute()
        cutout.recompute()
        w, h, depth = mm(0.4), mm(0.8), mm(0.25)
        assert_volume(cutout, base_volume - w * h * depth,
                      tol=1e-3)

        doc.abortTransaction()  # the panel's open create-transaction
    finally:
        if old_control is not None:
            Gui.Control = old_control
        else:
            try:
                del Gui.Control
            except AttributeError:
                pass
        App.closeDocument(doc.Name)


def test_drop_sketch_on_face_declined_cancels():
    """Declining the re-attachment cancels the whole operation: no dialog,
    no dados, and the sketch is left exactly as it was."""
    _qapp()
    doc = App.newDocument("dados_face_decline")
    control = _StubbedControl()
    old_control = getattr(Gui, 'Control', None)
    Gui.Control = control
    try:
        cutout, dsk = _cutout_with_face_sketch(doc, "Cutout")
        n_objects = len(doc.Objects)

        with _StubbedQuestion([QtWidgets.QMessageBox.No]) as asks:
            open_dados_task_panel(cutout, initial_sketches=[dsk])

        assert_true(len(asks.calls) == 1, "the re-attachment was offered")
        assert_true(control.shown == [], "no dialog was opened")

        dados_objs = [o for o in doc.Objects
                      if getattr(o, 'Type', '') == 'ShaperDados']
        assert_true(dados_objs == [], f"no dados created: {dados_objs}")
        assert_true(len(doc.Objects) == n_objects,
                    f"no objects created (got {len(doc.Objects) - n_objects})")

        entry = dsk.AttachmentSupport[0]
        assert_true(entry[0] is cutout and entry[1][0] == _face_sub(cutout, cutout.FrontFace),
                    f"sketch attachment untouched: {entry}")
    finally:
        if old_control is not None:
            Gui.Control = old_control
        else:
            try:
                del Gui.Control
            except AttributeError:
                pass
        App.closeDocument(doc.Name)


def test_add_button_reattaches_face_sketch():
    """The dialog's Add button offers the same re-attachment; declining
    cancels adding that sketch (the dialog itself stays open)."""
    _qapp()
    doc = App.newDocument("dados_face_add")
    old_widget = ShaperTaskPanel._quantity_widget
    ShaperTaskPanel._quantity_widget = \
        lambda self, prop, minimum=None, maximum=None: QtWidgets.QWidget()
    try:
        cutout, dsk = _cutout_with_face_sketch(doc, "Cutout")
        panel = ShaperDadosTaskPanel(cutout)
        try:
            assert_true(dsk.Label in [o.Label for o in
                                      _available(panel)],
                        "face-attached sketch is offered by Add")

            with _StubbedGetItem(
                    lambda items: items.index(dsk.Label)) as pick:
                with _StubbedQuestion([QtWidgets.QMessageBox.Yes]) as asks:
                    panel._on_add()

            assert_true(len(asks.calls) == 1, "re-attachment offered")
            assert_true(dsk in panel._current_sketches(), "sketch added")
            target = attachment_target(dsk)
            assert_true(target is not None and target[0] is cutout.FrontFace
                        and target[1] == '',
                        f"sketch re-attached to the face plane, got {target}")

            # Now the decline path: put the sketch back on the cutout face
            # (the accept path legitimately re-attached it to the plane),
            # then remove and re-add, declining. Clear the list first so the
            # document is not momentarily cyclic while re-attaching.
            panel.sketch_list.clear()
            panel._on_changed()
            assert_true(panel._current_sketches() == [], "list cleared")
            dsk.AttachmentSupport = [(cutout, (_face_sub(cutout, cutout.FrontFace),))]
            dsk.MapMode = 'FlatFace'
            doc.recompute()

            with _StubbedGetItem(
                    lambda items: items.index(dsk.Label)):
                with _StubbedQuestion([QtWidgets.QMessageBox.No]) as asks:
                    panel._on_add()

            assert_true(len(asks.calls) == 1, "re-attachment offered again")
            assert_true(dsk not in panel._current_sketches(),
                        "declining cancels the add")
            entry = dsk.AttachmentSupport[0]
            assert_true(entry[0] is cutout, "sketch attachment untouched")
        finally:
            doc.abortTransaction()
    finally:
        ShaperTaskPanel._quantity_widget = old_widget
        App.closeDocument(doc.Name)


def _available(panel):
    from shaper_cutout_command.create_shaper_dados import _available_sketches
    return _available_sketches(panel._doc, panel._current_sketches())


def test_sketch_on_plane_not_asked():
    """A sketch attached to an ordinary plane enters the dialog without any
    question and is left untouched."""
    _qapp()
    doc = App.newDocument("dados_face_plane_ok")
    control = _StubbedControl()
    old_control = getattr(Gui, 'Control', None)
    Gui.Control = control
    try:
        plane = make_plane(doc, "Plane1")
        outline = make_sketch(doc, plane, "Outline")
        cutout = make_cutout(doc, plane, "Cutout")
        cutout.OutlineSketch = outline
        dsk = make_sketch(doc, plane, "DadoSketch", closed=False)
        doc.recompute()

        with _StubbedQuestion([]) as asks:
            open_dados_task_panel(cutout, initial_sketches=[dsk])

        assert_true(len(asks.calls) == 0,
                    f"no question expected, got {asks.calls}")
        assert_true(len(control.shown) == 1, "panel shown")
        entry = dsk.AttachmentSupport[0]
        assert_true(entry[0] is plane, "sketch attachment untouched")
        doc.abortTransaction()
    finally:
        if old_control is not None:
            Gui.Control = old_control
        else:
            try:
                del Gui.Control
            except AttributeError:
                pass
        App.closeDocument(doc.Name)


def test_reattach_preserves_global_placement():
    """reattach_to_plane re-expresses the sketch's global placement as an
    AttachmentOffset on the new plane, for rotated/offset cases too."""
    doc = App.newDocument("dados_reattach_math")
    try:
        plane1 = make_plane(doc, "Plane1")
        plane2 = make_plane(doc, "Plane2", origin=(mm(1), 0, mm(2)),
                            rot=(90, 0, 0))
        sketch = make_sketch(doc, plane1, "Sketch1")
        sketch.AttachmentOffset = App.Placement(
            App.Vector(mm(0.5), mm(-0.25), 0), App.Rotation())
        doc.recompute()
        g_before = App.Placement(sketch.getGlobalPlacement())

        reattach_to_plane(sketch, plane2)
        doc.recompute()

        g_after = App.Placement(sketch.getGlobalPlacement())
        assert_true((g_after.Base - g_before.Base).Length < 1e-9,
                    f"base preserved: {g_before.Base} -> {g_after.Base}")
        dq = g_before.Rotation.multiply(g_after.Rotation).Angle
        assert_true(abs(dq) < 1e-9, f"rotation preserved (delta {dq} rad)")
        entry = sketch.AttachmentSupport[0]
        assert_true(entry[0] is plane2, "sketch now attached to plane2")
    finally:
        App.closeDocument(doc.Name)


def register_tests(all_tests):
    all_tests.extend([
        test_drop_sketch_on_face_reattaches_to_face_plane,
        test_drop_sketch_on_face_declined_cancels,
        test_add_button_reattaches_face_sketch,
        test_sketch_on_plane_not_asked,
        test_reattach_preserves_global_placement,
    ])
