# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for the "Create Shaper Cutout" command's selection handling.

Issue #15: selecting a datum plane together with a sketch used to disable the
Create Shaper Cutout button entirely. The button must be active whenever the
selection contains exactly one center-plane candidate (a plane, or a cutout
which contributes its center plane) plus any number of sketches; the dialog
then pre-selects a usable sketch as the outline and reports ones it declines
to use (nonparallel, dado sketches, extras beyond the first).

These run headless: the Gui.Selection module does not exist without a GUI, so
tests patch it with a stub exposing getSelection().
"""

import types

import FreeCAD as App
import FreeCADGui as Gui
import Part
from PySide import QtWidgets

import ShaperDados  # noqa: F401  (registers the ShaperDados type)
import ShaperCutout  # noqa: F401

from shaper_cutout_command.create_shaper_cutout import (
    CreateShaperCutoutCmd, ShaperCutoutTaskPanel, _selection_center_and_sketches)
from shaper_cutout_command.task_panel import ShaperTaskPanel

from util import assert_true, make_cutout, make_plane, make_sketch, mm


def _qapp():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def _stub_selection(objects):
    """Patch Gui.Selection (absent in headless mode) to return `objects`."""
    Gui.Selection = types.SimpleNamespace(
        getSelection=lambda: list(objects),
        getSelectionEx=lambda: [],
    )


def _make_dado_on(cutout, sketch):
    dados = ShaperDados.create_uninitialized(cutout, "Dados_for_sketch")
    dados.Face = cutout.FrontFace
    dados.Depth = mm(0.25)
    dados.Width = mm(0.25)
    dados.Tolerance = mm(0.01)
    dados.Sketches = [sketch]
    return dados


class _PanelFixture:
    """Builds the doc/selection/widgets a create-flow panel needs, headless.

    Usage: with _PanelFixture([plane, sketch]) as panel: ...
    The panel's transaction is aborted on exit (Gui.Control is absent
    headless, so panel.reject() itself cannot be used).
    """

    def __init__(self, selection):
        self.selection = selection
        self._undo_widget = ShaperTaskPanel._quantity_widget
        self._sel = getattr(Gui, 'Selection', None)
        self.panel = None

    def __enter__(self):
        _qapp()
        # The quantity spin boxes need Gui.UiLoader, which headless mode
        # lacks; stub it out -- we only test selection/outline behavior.
        ShaperTaskPanel._quantity_widget = \
            lambda self, prop, minimum=None, maximum=None: QtWidgets.QWidget()
        _stub_selection(self.selection)
        self.panel = ShaperCutoutTaskPanel()
        return self.panel

    def __exit__(self, *exc):
        ShaperTaskPanel._quantity_widget = self._undo_widget
        if self._sel is None:
            try:
                del Gui.Selection
            except AttributeError:
                pass
        else:
            Gui.Selection = self._sel
        if self.panel is not None:
            self.panel._doc.abortTransaction()
        return False


def test_selection_parse_plane_plus_sketch():
    doc = App.newDocument("sel_parse")
    plane = make_plane(doc, "Plane1")
    sketch = make_sketch(doc, plane, "Sketch1")
    cutout = make_cutout(doc, plane, "Cutout1")
    plane2 = make_plane(doc, "Plane2")
    cube = doc.addObject("Part::Box", "Box")

    center, sketches = _selection_center_and_sketches([plane])
    assert_true(center is plane and sketches == [], "plane alone -> plane center")

    center, sketches = _selection_center_and_sketches([plane, sketch])
    assert_true(center is plane and sketches == [sketch],
                "plane + sketch is a valid selection")

    center, sketches = _selection_center_and_sketches([cutout])
    assert_true(center is plane and sketches == [],
                "cutout alone -> its center plane")

    center, sketches = _selection_center_and_sketches([cutout, plane])
    assert_true(center is plane and sketches == [],
                "cutout + own center plane de-dupes to one candidate")

    center, sketches = _selection_center_and_sketches([cutout, plane, sketch])
    assert_true(center is plane and sketches == [sketch],
                "cutout + own center plane + sketch")

    center, _ = _selection_center_and_sketches([plane, plane2])
    assert_true(center is None, "two planes is not a valid center")

    center, _ = _selection_center_and_sketches([cutout, plane2])
    assert_true(center is None,
                "cutout + a different plane is ambiguous, not a valid center")

    center, _ = _selection_center_and_sketches([sketch])
    assert_true(center is None, "sketch alone has no center")

    center, _ = _selection_center_and_sketches([plane, cube])
    assert_true(center is None, "unrelated object disqualifies selection")

    center, _ = _selection_center_and_sketches([])
    assert_true(center is None, "empty selection")

    App.closeDocument(doc.Name)


def test_create_cmd_isactive():
    doc = App.newDocument("sel_isactive")
    plane = make_plane(doc, "Plane1")
    sketch = make_sketch(doc, plane, "Sketch1")
    plane2 = make_plane(doc, "Plane2")
    cube = doc.addObject("Part::Box", "Box")
    cmd = CreateShaperCutoutCmd()

    old_sel = getattr(Gui, 'Selection', None)
    try:
        _stub_selection([plane])
        assert_true(cmd.IsActive(), "plane alone: command active")
        _stub_selection([plane, sketch])
        assert_true(cmd.IsActive(), "plane + sketch: command active (issue #15)")
        _stub_selection([sketch])
        assert_true(not cmd.IsActive(), "sketch alone: not active")
        _stub_selection([plane, plane2])
        assert_true(not cmd.IsActive(), "two planes: not active")
        _stub_selection([plane, cube])
        assert_true(not cmd.IsActive(), "plane + unrelated object: not active")
        _stub_selection([])
        assert_true(not cmd.IsActive(), "empty selection: not active")
    finally:
        if old_sel is None:
            try:
                del Gui.Selection
            except AttributeError:
                pass
        else:
            Gui.Selection = old_sel

    App.closeDocument(doc.Name)


def test_create_panel_preselects_selected_sketch():
    doc = App.newDocument("sel_preselect")
    plane = make_plane(doc, "Plane1")
    sketch = make_sketch(doc, plane, "Sketch1")
    doc.recompute()

    with _PanelFixture([plane, sketch]) as panel:
        obj = panel._object
        assert_true(obj.Type == 'ShaperCutout', "created a cutout")
        assert_true(obj.CenterPlane is plane, "center plane from selection")
        assert_true(obj.OutlineSketch is sketch,
                    "selected sketch pre-set as outline sketch")
        assert_true(panel.sketch_combo.currentData() is sketch,
                    "sketch combo shows the selected sketch")
        assert_true(panel.preselect_warnings == [],
                    f"no warnings expected, got {panel.preselect_warnings}")
        # The quantity spin box is stubbed headless, so set the thickness a
        # real user would have dialed in, and confirm the outline flows into
        # the geometry.
        obj.Thickness = mm(0.5)
        doc.recompute()
        assert_true(len(obj.Shape.Solids) == 1, "cutout computed a solid")

    App.closeDocument(doc.Name)


def test_create_panel_nonparallel_sketch_warns():
    doc = App.newDocument("sel_nonparallel")
    plane = make_plane(doc, "Plane1")
    # A vertical plane with a sketch on it; selecting it with the horizontal
    # center plane must still create the cutout, but not use the sketch.
    vertical = make_plane(doc, "Vertical", rot=(0.70710678, 0, 0, 0.70710678))
    sketch = make_sketch(doc, vertical, "SketchV")
    doc.recompute()

    with _PanelFixture([plane, sketch]) as panel:
        obj = panel._object
        assert_true(obj.CenterPlane is plane, "center plane still created")
        assert_true(obj.OutlineSketch is None,
                    "nonparallel sketch not used as outline")
        assert_true(len(panel.preselect_warnings) == 1
                    and "not parallel" in panel.preselect_warnings[0],
                    f"nonparallel warning expected, got {panel.preselect_warnings}")

    App.closeDocument(doc.Name)


def test_create_panel_dado_sketch_warns():
    doc = App.newDocument("sel_dadosketch")
    plane = make_plane(doc, "Plane1")
    other = make_cutout(doc, make_plane(doc, "Plane2"), "Cutout2")
    # A parallel sketch that is already used as a dado sketch.
    sketch = make_sketch(doc, plane, "DadoLineSketch", closed=False)
    doc.recompute()
    _make_dado_on(other, sketch)
    doc.recompute()

    with _PanelFixture([plane, sketch]) as panel:
        obj = panel._object
        assert_true(obj.CenterPlane is plane, "center plane still created")
        assert_true(obj.OutlineSketch is None,
                    "dado sketch not used as outline")
        assert_true(len(panel.preselect_warnings) == 1
                    and "dado" in panel.preselect_warnings[0],
                    f"dado warning expected, got {panel.preselect_warnings}")
        # Dado sketches should also be absent from the combo entirely.
        entries = [panel.sketch_combo.itemData(i)
                   for i in range(panel.sketch_combo.count())]
        assert_true(sketch not in entries, "dado sketch not offered in combo")

    App.closeDocument(doc.Name)


def test_create_panel_multiple_sketches():
    doc = App.newDocument("sel_multi")
    plane = make_plane(doc, "Plane1")
    sketch_a = make_sketch(doc, plane, "SketchA")
    sketch_b = make_sketch(doc, plane, "SketchB")
    doc.recompute()

    with _PanelFixture([plane, sketch_b, sketch_a]) as panel:
        obj = panel._object
        # First selected sketch wins; the rest are reported.
        assert_true(obj.OutlineSketch is sketch_b,
                    "first selected sketch used as outline")
        assert_true(len(panel.preselect_warnings) == 1
                    and "SketchA" in panel.preselect_warnings[0],
                    f"ignored-sketch warning expected, got {panel.preselect_warnings}")

    App.closeDocument(doc.Name)


def test_create_panel_plane_only_unchanged():
    doc = App.newDocument("sel_planeonly")
    plane = make_plane(doc, "Plane1")
    doc.recompute()

    with _PanelFixture([plane]) as panel:
        obj = panel._object
        assert_true(obj.CenterPlane is plane, "center plane from selection")
        assert_true(obj.OutlineSketch is None, "no outline without a sketch")
        assert_true(panel.sketch_combo.currentData() is None,
                    "combo defaults to '(No outline sketch)'")
        assert_true(panel.preselect_warnings == [], "no warnings")

    App.closeDocument(doc.Name)


def register_tests(all_tests):
    all_tests.extend([
        test_selection_parse_plane_plus_sketch,
        test_create_cmd_isactive,
        test_create_panel_preselects_selected_sketch,
        test_create_panel_nonparallel_sketch_warns,
        test_create_panel_dado_sketch_warns,
        test_create_panel_multiple_sketches,
        test_create_panel_plane_only_unchanged,
    ])
