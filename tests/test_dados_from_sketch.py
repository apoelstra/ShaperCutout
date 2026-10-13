# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests: the "Create Dados" command from a sketch-only selection.

Selecting just a dado sketch (no cutout) must keep the command active:
clicking it asks which parallel cutout to dado into (when several
qualify), pre-selects the sketch in the dialog, and errors out when no
cutout is parallel to the sketch. Sketches already linked into a
cutout's dado set are not offered again (that would double-cut).
"""

import FreeCAD as App
from PySide import QtWidgets

import ShaperCutout  # noqa: F401  (registers the ShaperCutout type)
import ShaperDados  # noqa: F401  (registers the ShaperDados type)

from shaper_cutout_command.create_shaper_dados import (
    CreateShaperDadosCmd, _cutouts_for_sketch, _selected_objects)

from util import assert_true, make_cutout, make_plane, make_sketch, stub_selection


class _StubbedGetItem:
    """Capture QInputDialog.getItem, picking via a callback over the items."""

    def __init__(self, pick):
        self.pick = pick
        self.calls = []
        self._real = QtWidgets.QInputDialog.getItem

    def __enter__(self):
        def fake(parent, title, label, items, current=0, selectable=True, *a, **k):
            self.calls.append((title, str(label), list(items)))
            idx = self.pick(list(items))
            return (items[idx], True)

        QtWidgets.QInputDialog.getItem = staticmethod(fake)
        return self

    def __exit__(self, *exc):
        QtWidgets.QInputDialog.getItem = self._real


class _StubbedCritical:
    """Capture QMessageBox.critical calls; canned answers are unused."""

    def __init__(self):
        self.calls = []
        self._real = QtWidgets.QMessageBox.critical

    def __enter__(self):
        def fake(parent, title, text, *a, **k):
            self.calls.append((title, str(text)))
            return QtWidgets.QMessageBox.Ok

        QtWidgets.QMessageBox.critical = staticmethod(fake)
        return self

    def __exit__(self, *exc):
        QtWidgets.QMessageBox.critical = self._real


def _doc_with_two_parallel_cutouts(name):
    doc = App.newDocument(name)
    plane = make_plane(doc, "Plane1")
    outline = make_sketch(doc, plane, "Outline")
    cutout1 = make_cutout(doc, plane, "Cutout1")
    cutout1.OutlineSketch = outline
    plane2 = make_plane(doc, "Plane2")
    outline2 = make_sketch(doc, plane2, "Outline2")
    cutout2 = make_cutout(doc, plane2, "Cutout2")
    cutout2.OutlineSketch = outline2
    doc.recompute()
    return doc, cutout1, cutout2


def test_sketch_selection_targets_parallel_cutouts():
    """Sketch-only selection: candidates are the parallel cutouts that do
    not already dado this sketch."""
    doc, cutout1, cutout2 = _doc_with_two_parallel_cutouts("dsk_targets")
    # A nonparallel cutout must never be a candidate.
    plane3 = make_plane(doc, "Plane3", origin=(0, 0, 0),
                        rot=(0.70710678, 0, 0, 0.70710678))
    outline3 = make_sketch(doc, plane3, "Outline3")
    cutout3 = make_cutout(doc, plane3, "Cutout3")
    cutout3.OutlineSketch = outline3
    doc.recompute()

    dsk = make_sketch(doc, cutout1.FrontFace, "DadoLine", closed=False)
    doc.recompute()

    assert_true(_cutouts_for_sketch(dsk) == [cutout1, cutout2],
                "parallel cutouts only, in document order")
    assert_true(cutout3 not in _cutouts_for_sketch(dsk),
                "nonparallel cutout is not a candidate")

    # Once the sketch is dado'd into cutout1, cutout1 must drop out (the
    # sketch already cuts there) but cutout2 stays available.
    dados = ShaperDados.create_uninitialized(cutout1, "Dados1")
    dados.Face = cutout1.FrontFace
    dados.Sketches = [dsk]
    doc.recompute()

    assert_true(_cutouts_for_sketch(dsk) == [cutout2],
                "a cutout that already dados this sketch is not offered")

    App.closeDocument(doc.Name)


def test_selection_parse():
    """_selected_objects truth table over selection shapes."""
    doc, cutout1, cutout2 = _doc_with_two_parallel_cutouts("dsk_parse")
    cube = doc.addObject("Part::Box", "Box")
    dsk = make_sketch(doc, cutout1.FrontFace, "DadoLine", closed=False)
    doc.recompute()

    stub_selection([cutout1])
    cutout, sketches = _selected_objects()
    assert_true(cutout == cutout1 and sketches == [],
                "single cutout selection unchanged")

    stub_selection([cutout1, dsk])
    cutout, sketches = _selected_objects()
    assert_true(cutout == cutout1 and sketches == [dsk],
                "cutout + sketch passes both through")

    stub_selection([cutout1, cube])
    cutout, sketches = _selected_objects()
    assert_true(cutout is None,
                "cutout + unrelated object: not a valid selection")

    stub_selection([dsk])
    cutout, sketches = _selected_objects()
    assert_true(cutout is None and sketches == [dsk],
                "sketch-only selection: parallel cutout candidates")

    stub_selection([])
    cutout, sketches = _selected_objects()
    assert_true(cutout is None, "empty selection: not valid")

    App.closeDocument(doc.Name)


def test_cmd_isactive():
    doc, cutout1, cutout2 = _doc_with_two_parallel_cutouts("dsk_isactive")
    dsk = make_sketch(doc, cutout1.FrontFace, "DadoLine", closed=False)
    doc.recompute()
    cmd = CreateShaperDadosCmd()

    stub_selection([cutout1])
    assert_true(cmd.IsActive(), "cutout selection: active")

    stub_selection([dsk])
    assert_true(cmd.IsActive(),
                "sketch selection with a parallel cutout: active")

    # A sketch parallel to no cutout stays active so Activated() can
    # explain why, instead of a silently greyed-out button.
    vertical = make_plane(doc, "Vertical", origin=(0, 0, 0),
                          rot=(0.70710678, 0, 0, 0.70710678))
    vsk = make_sketch(doc, vertical, "VerticalSketch")
    doc.recompute()
    stub_selection([vsk])
    assert_true(cmd.IsActive(),
                "sketch with no parallel cutout: still active (error on click)")

    stub_selection([])
    assert_true(not cmd.IsActive(), "empty selection: inactive")

    App.closeDocument(doc.Name)


def test_cmd_activated_sketch_only_multiple_candidates():
    """Sketch-only click with two parallel cutouts asks which one, then
    opens the dialog pre-seeded with the sketch on the chosen cutout."""
    doc, cutout1, cutout2 = _doc_with_two_parallel_cutouts("dsk_multi")
    dsk = make_sketch(doc, cutout1.FrontFace, "DadoLine", closed=False)
    doc.recompute()

    cmd = CreateShaperDadosCmd()
    opened = []
    real_open = cmd.__class__.__module__  # noqa: F841 (readability only)

    import shaper_cutout_command.create_shaper_dados as csd
    real_open_dados = csd.open_dados_task_panel
    csd.open_dados_task_panel = (
        lambda cutout, dados=None, initial_sketches=[], clone_from=None:
        opened.append((cutout, tuple(initial_sketches))))
    try:
        stub_selection([dsk])
        with _StubbedGetItem(lambda items: items.index("Cutout2")) as ask:
            cmd.Activated()

        assert_true(len(ask.calls) == 1, f"one chooser expected, got {ask.calls}")
        title, label, items = ask.calls[0]
        assert_true(items == ["Cutout1", "Cutout2"],
                    f"both parallel cutouts offered: {items}")
        assert_true("DadoLine" in label,
                    f"the question names the sketch: {label}")

        assert_true(len(opened) == 1, f"dialog opened once: {opened}")
        cutout, sketches = opened[0]
        assert_true(cutout is cutout2, "the chosen cutout was used")
        assert_true(sketches == (dsk,), "the selected sketch is pre-seeded")
    finally:
        csd.open_dados_task_panel = real_open_dados

    App.closeDocument(doc.Name)


def test_cmd_activated_sketch_only_single_candidate():
    """Sketch-only click with exactly one parallel cutout skips the chooser."""
    doc = App.newDocument("dsk_single")
    plane = make_plane(doc, "Plane1")
    outline = make_sketch(doc, plane, "Outline")
    cutout = make_cutout(doc, plane, "Cutout1")
    cutout.OutlineSketch = outline
    dsk = make_sketch(doc, cutout.FrontFace, "DadoLine", closed=False)
    doc.recompute()

    cmd = CreateShaperDadosCmd()
    opened = []
    import shaper_cutout_command.create_shaper_dados as csd
    real_open_dados = csd.open_dados_task_panel
    csd.open_dados_task_panel = (
        lambda cutout, dados=None, initial_sketches=[], clone_from=None:
        opened.append((cutout, tuple(initial_sketches))))
    try:
        stub_selection([dsk])
        with _StubbedGetItem(lambda items: 0) as ask:
            cmd.Activated()

        assert_true(len(ask.calls) == 1, f"one chooser expected, got {ask.calls}")
        title, label, items = ask.calls[0]
        assert_true(items == ["Cutout1"],
                    f"a single cutout offered: {items}")
        assert_true(len(opened) == 1 and opened[0][0] is cutout
                    and opened[0][1] == (dsk,),
                    f"dialog opened on the cutout with the sketch: {opened}")
    finally:
        csd.open_dados_task_panel = real_open_dados

    App.closeDocument(doc.Name)


def test_cmd_activated_sketch_only_no_candidates_errors():
    """Sketch parallel to no cutout: clicking shows an error, opens nothing."""
    doc = App.newDocument("dsk_nocandidates")
    plane = make_plane(doc, "Plane1")
    outline = make_sketch(doc, plane, "Outline")
    cutout = make_cutout(doc, plane, "Cutout1")
    cutout.OutlineSketch = outline
    vertical = make_plane(doc, "Vertical", origin=(0, 0, 0),
                          rot=(0.70710678, 0, 0, 0.70710678))
    vsk = make_sketch(doc, vertical, "VerticalSketch")
    doc.recompute()

    cmd = CreateShaperDadosCmd()
    opened = []
    import shaper_cutout_command.create_shaper_dados as csd
    real_open_dados = csd.open_dados_task_panel
    csd.open_dados_task_panel = (
        lambda cutout, dados=None, initial_sketches=[], clone_from=None:
        opened.append(cutout))
    try:
        stub_selection([vsk])
        with _StubbedCritical() as err:
            cmd.Activated()

        assert_true(opened == [], "no dialog was opened")
        assert_true(len(err.calls) == 1,
                    f"one error expected, got {err.calls}")
        title, text = err.calls[0]
        assert_true("VerticalSketch" in text,
                    f"the error names the sketch: {text}")
        assert_true("parallel" in text.lower(),
                    f"the error says why: {text}")
    finally:
        csd.open_dados_task_panel = real_open_dados

    App.closeDocument(doc.Name)


def test_cmd_activated_cutout_selection_unchanged():
    """The classic cutout-selection path still opens the dialog directly."""
    doc, cutout1, cutout2 = _doc_with_two_parallel_cutouts("dsk_cutoutpath")

    cmd = CreateShaperDadosCmd()
    opened = []
    import shaper_cutout_command.create_shaper_dados as csd
    real_open_dados = csd.open_dados_task_panel
    csd.open_dados_task_panel = (
        lambda cutout, dados=None, initial_sketches=[], clone_from=None:
        opened.append((cutout, tuple(initial_sketches))))
    try:
        stub_selection([cutout2])
        with _StubbedGetItem(lambda items: 0) as ask:
            cmd.Activated()

        assert_true(ask.calls == [],
                    f"no chooser for a cutout selection: {ask.calls}")
        assert_true(len(opened) == 1 and opened[0][0] is cutout2
                    and opened[0][1] == (),
                    f"dialog opened on the selected cutout: {opened}")
    finally:
        csd.open_dados_task_panel = real_open_dados

    App.closeDocument(doc.Name)


def register_tests(all_tests):
    all_tests.extend([
        test_sketch_selection_targets_parallel_cutouts,
        test_selection_parse,
        test_cmd_isactive,
        test_cmd_activated_sketch_only_multiple_candidates,
        test_cmd_activated_sketch_only_single_candidate,
        test_cmd_activated_sketch_only_no_candidates_errors,
        test_cmd_activated_cutout_selection_unchanged,
    ])
