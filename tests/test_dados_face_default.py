# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests: the Create Dados dialog's default face follows the sketch.

When the (first) initial sketch does not sit on the cutout's center
plane, the face combo must default to the face on the sketch's side of
the sheet: the user drew the dado where the mating sheet sits, which is
the side it must be cut from. Sketches on the center plane keep the old
front-face default.
"""

import FreeCAD as App
from PySide import QtWidgets

import ShaperCutout  # noqa: F401  (registers the ShaperCutout type)
import ShaperDados  # noqa: F401  (registers the ShaperDados type)

from shaper_cutout_command.create_shaper_dados import (
    ShaperDadosTaskPanel, _face_for_sketch)
from shaper_cutout_command.task_panel import ShaperTaskPanel

from util import assert_true, make_cutout, make_plane, make_sketch, mm


def _qapp():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def _rect_sketch(doc, name, plane, offset_z=0.0):
    """A small closed rectangle sketch attached to `plane` (optionally
    offset along the plane's normal)."""
    sketch = make_sketch(doc, plane, name)
    if offset_z:
        sketch.AttachmentOffset = App.Placement(
            App.Vector(0, 0, offset_z), App.Rotation())
    return sketch


def test_face_for_sketch_sides():
    """The math: front-side sketch -> (front, invert), back-side ->
    (back, not invert), center-plane -> front default."""
    doc = App.newDocument("fd_math")
    try:
        plane = make_plane(doc, "Plane", origin=(0, 0, 0))
        outline = make_sketch(doc, plane, "Outline")
        cutout = make_cutout(doc, plane, "Cutout", thickness=mm(0.5))
        cutout.OutlineSketch = outline
        doc.recompute()
        front, back = cutout.FrontFace, cutout.BackFace
        half = mm(0.5) / 2.0

        # Exactly on the center plane: front default.
        center_sk = _rect_sketch(doc, "CenterSk", plane)
        doc.recompute()
        assert_true(_face_for_sketch(cutout, center_sk, front, back)
                    == (front, True), "center-plane sketch -> front default")

        # Front sheet face (offset +thickness/2) and beyond.
        front_sk = _rect_sketch(doc, "FrontSk", plane, offset_z=half)
        doc.recompute()
        assert_true(_face_for_sketch(cutout, front_sk, front, back)
                    == (front, True), "front-face sketch -> (front, invert)")

        beyond_sk = _rect_sketch(doc, "BeyondSk", plane, offset_z=mm(1))
        doc.recompute()
        assert_true(_face_for_sketch(cutout, beyond_sk, front, back)
                    == (front, True), "sketch beyond front -> (front, invert)")

        # Back sheet face and beyond.
        back_sk = _rect_sketch(doc, "BackSk", plane, offset_z=-half)
        doc.recompute()
        assert_true(_face_for_sketch(cutout, back_sk, front, back)
                    == (back, False), "back-face sketch -> (back, normal)")

        beyond_back = _rect_sketch(doc, "BeyondBackSk", plane, offset_z=-mm(1))
        doc.recompute()
        assert_true(_face_for_sketch(cutout, beyond_back, front, back)
                    == (back, False), "sketch beyond back -> (back, normal)")

        # Missing face planes: no opinion.
        assert_true(_face_for_sketch(cutout, front_sk, None, back) is None,
                    "missing front -> None")
        assert_true(_face_for_sketch(cutout, front_sk, front, None) is None,
                    "missing back -> None")
    finally:
        App.closeDocument(doc.Name)


def test_face_for_sketch_global_normal():
    """The side decision uses the sheet's *global* normal, not the sketch's
    or the world Z axis: rotate the sheet 90 degrees about X (normal
    becomes -Y) and put the sketch on what is now the front side."""
    doc = App.newDocument("fd_global")
    try:
        plane = make_plane(doc, "Plane", origin=(0, 0, 0),
                           rot=(0.70710678, 0, 0, 0.70710678))  # normal -Y
        outline = make_sketch(doc, plane, "Outline")
        cutout = make_cutout(doc, plane, "Cutout", thickness=mm(0.5))
        cutout.OutlineSketch = outline
        doc.recompute()
        front, back = cutout.FrontFace, cutout.BackFace

        # With this rotation the sheet normal is -Y and the FrontFace
        # plane sits at y = -thickness/2, i.e. the front side is -Y. A
        # sketch at +Y must map to the back face, and vice versa, even
        # though a naive world-Z comparison would call both "flat".
        world_plane = make_plane(doc, "WorldPlane", origin=(0, mm(1), 0))
        front_sk = make_sketch(doc, world_plane, "BackSideSk")
        doc.recompute()
        assert_true(_face_for_sketch(cutout, front_sk, front, back)
                    == (back, False),
                    "sketch at +Y (back side of a -Y-normal sheet) -> (back, normal)")

        world_plane2 = make_plane(doc, "WorldPlane2", origin=(0, -mm(1), 0))
        back_sk = make_sketch(doc, world_plane2, "FrontSideSk")
        doc.recompute()
        assert_true(_face_for_sketch(cutout, back_sk, front, back)
                    == (front, True),
                    "sketch at -Y (front side of a -Y-normal sheet) -> (front, invert)")
    finally:
        App.closeDocument(doc.Name)


class _PanelFixture:
    """Build a create-mode ShaperDadosTaskPanel headlessly; abort the
    panel's transaction on exit."""

    def __init__(self, cutout, initial_sketches):
        self.cutout = cutout
        self.initial_sketches = initial_sketches
        self._undo_widget = ShaperTaskPanel._quantity_widget

    def __enter__(self):
        _qapp()
        ShaperTaskPanel._quantity_widget = \
            lambda self, prop, minimum=None, maximum=None: QtWidgets.QWidget()
        self.panel = ShaperDadosTaskPanel(self.cutout,
                                          initial_sketches=self.initial_sketches)
        return self.panel

    def __exit__(self, *exc):
        ShaperTaskPanel._quantity_widget = self._undo_widget
        if self.panel is not None and not self.panel.is_rejected():
            self.panel._doc.abortTransaction()
        return False


def test_panel_defaults_face_from_sketch():
    """The dialog's face combo (and the created object) default to the
    side of the sheet the initial sketch sits on."""
    doc = App.newDocument("fd_panel")
    try:
        plane = make_plane(doc, "Plane", origin=(0, 0, 0))
        outline = make_sketch(doc, plane, "Outline")
        cutout = make_cutout(doc, plane, "Cutout", thickness=mm(0.5))
        cutout.OutlineSketch = outline
        doc.recompute()

        # Back-side sketch: dialog defaults to back.
        back_sk = _rect_sketch(doc, "BackSk", plane, offset_z=-mm(0.25))
        doc.recompute()
        with _PanelFixture(cutout, [back_sk]) as panel:
            (face, invert) = panel.face_combo.currentData()
            assert_true(face is cutout.BackFace and invert is False,
                        "combo defaults to back for a back-side sketch")
            assert_true(panel._object.Face is cutout.BackFace,
                        "object face is back")
            assert_true(panel._object.Invert is False, "object not inverted")

        # Front-side sketch: dialog defaults to front.
        front_sk = _rect_sketch(doc, "FrontSk", plane, offset_z=mm(0.25))
        doc.recompute()
        with _PanelFixture(cutout, [front_sk]) as panel:
            (face, invert) = panel.face_combo.currentData()
            assert_true(face is cutout.FrontFace and invert is True,
                        "combo defaults to front for a front-side sketch")
            assert_true(panel._object.Face is cutout.FrontFace,
                        "object face is front")
            assert_true(panel._object.Invert is True, "object inverted")

        # Center-plane sketch: old front default.
        center_sk = _rect_sketch(doc, "CenterSk", plane)
        doc.recompute()
        with _PanelFixture(cutout, [center_sk]) as panel:
            (face, invert) = panel.face_combo.currentData()
            assert_true(face is cutout.FrontFace and invert is True,
                        "center-plane sketch keeps the front default")

        # No sketches at all: old front default.
        with _PanelFixture(cutout, []) as panel:
            (face, invert) = panel.face_combo.currentData()
            assert_true(face is cutout.FrontFace and invert is True,
                        "no sketch keeps the front default")
    finally:
        App.closeDocument(doc.Name)


def test_panel_face_default_first_sketch_wins():
    """With several initial sketches the first one with an opinion picks
    the face; a detached sketch has no opinion."""
    doc = App.newDocument("fd_panel_multi")
    try:
        plane = make_plane(doc, "Plane", origin=(0, 0, 0))
        outline = make_sketch(doc, plane, "Outline")
        cutout = make_cutout(doc, plane, "Cutout", thickness=mm(0.5))
        cutout.OutlineSketch = outline
        doc.recompute()

        center_sk = _rect_sketch(doc, "CenterSk", plane)
        back_sk = _rect_sketch(doc, "BackSk", plane, offset_z=-mm(0.25))
        doc.recompute()

        # Center-plane sketch first: its "opinion" is the front default,
        # so the back-side sketch behind it cannot override.
        with _PanelFixture(cutout, [center_sk, back_sk]) as panel:
            (face, _inv) = panel.face_combo.currentData()
            assert_true(face is cutout.FrontFace,
                        "first sketch's side wins")

        # Detached sketch first: no opinion; the back-side sketch decides.
        detached = _rect_sketch(doc, "DetachedSk", plane)
        detached.AttachmentSupport = []
        detached.MapMode = 'Deactivated'
        doc.recompute()
        with _PanelFixture(cutout, [detached, back_sk]) as panel:
            (face, invert) = panel.face_combo.currentData()
            assert_true(face is cutout.BackFace and invert is False,
                        "detached sketch skipped, back-side sketch decides")
    finally:
        App.closeDocument(doc.Name)


def register_tests(all_tests):
    all_tests.extend([
        test_face_for_sketch_sides,
        test_face_for_sketch_global_normal,
        test_panel_defaults_face_from_sketch,
        test_panel_face_default_first_sketch_wins,
    ])
