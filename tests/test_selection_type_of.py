# SPDX-License-Identifier: GPL-3.0-or-later
"""ShaperCutoutType.type_of must recognize miters and slots.

Regression: type_of had no branches for the 'ShaperMiter' / 'ShaperSlot'
Type strings, so both classified as OTHER -- the report view's Miter and
Slot tables were always empty, and selection parsers under-counted any
miter/slot in a selection.
"""

import FreeCAD as App
from PySide import QtCore, QtWidgets

import ShaperCutout  # noqa: F401
import ShaperDados  # noqa: F401
import ShaperMiter  # noqa: F401
import ShaperSlot  # noqa: F401

from shaper_cutout_util import Objects, ShaperCutoutType
from shaper_cutout_command.report_view import ReportViewTaskPanel

from test_dialog_ok_cancel import _slot_fixture, _cutout_fixture
from test_report_and_page_mouse import _stub_report_gui_services

from util import assert_true


def test_type_of():
    doc = App.newDocument("sel_type_of")
    try:
        _plane, sketch, cutout = _cutout_fixture(doc)
        dados = ShaperDados.create_uninitialized(cutout, "Dados")
        miter = ShaperMiter.create(
            cutout=cutout, edges=[(sketch, ['Edge1'])], angle=45.0,
            miter_axis="Center", name="Miter")
        c1, c2, ifp = _slot_fixture(doc)
        slot = ShaperSlot.create_uninitialized(c1, c2, ifp, "Slot")
        doc.recompute()

        cases = [
            (cutout, ShaperCutoutType.CUTOUT),
            (dados, ShaperCutoutType.DADOS),
            (miter, ShaperCutoutType.MITER),
            (slot, ShaperCutoutType.SLOT),
        ]
        for obj, expected in cases:
            got = ShaperCutoutType.type_of(obj)
            assert_true(got == expected,
                        f"type_of({obj.Type}) returned {got}, "
                        f"expected {expected}")
    finally:
        App.closeDocument(doc.Name)


def _model_rows(model):
    """(obj, [display strings per column]) for every row of a report model,
    exercising each column's compute function through the real data() path."""
    rows = []
    for r in range(model.rowCount()):
        obj = model._doc_objs[r]
        cells = [model.data(model.index(r, c), QtCore.Qt.DisplayRole)
                 for c in range(1, model.columnCount())]
        rows.append((obj, cells))
    return rows


def test_report_view_tables_populate():
    """The report view's tables must list all their respective objects."""
    QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    doc = App.newDocument("report_tables")
    try:
        _plane, sketch, cutout = _cutout_fixture(doc)
        miter = ShaperMiter.create(
            cutout=cutout, edges=[(sketch, ['Edge1'])], angle=45.0,
            miter_axis="Center", name="Miter")
        c1, c2, ifp = _slot_fixture(doc)
        slot = ShaperSlot.create_uninitialized(c1, c2, ifp, "Slot")
        doc.recompute()

        _control, restore = _stub_report_gui_services()
        try:
            panel = ReportViewTaskPanel()
            try:
                cutout_rows = _model_rows(panel._cutouts_section._table._model)
                dados_rows = _model_rows(panel._dados_section._table._model)
                miter_rows = _model_rows(panel._miter_section._table._model)
                slot_rows = _model_rows(panel._slots_section._table._model)

                assert_true([obj for obj, _ in cutout_rows] == [cutout, c1, c2],
                            f"cutouts table should list the cutouts, "
                            f"got {[getattr(o, 'Type', '?') for o, _ in cutout_rows]}")
                # FIXME should have a dado in this test lol
                assert_true([obj for obj, _ in dados_rows] == [],
                            f"cutouts table should list the cutouts, "
                            f"got {[getattr(o, 'Type', '?') for o, _ in dados_rows]}")
                assert_true([obj for obj, _ in miter_rows] == [miter],
                            f"miter table should list the miter, "
                            f"got {[getattr(o, 'Type', '?') for o, _ in miter_rows]}")
                assert_true([obj for obj, _ in slot_rows] == [slot],
                            f"slot table should list the slot, "
                            f"got {[getattr(o, 'Type', '?') for o, _ in slot_rows]}")

                # All columns computed real values (no None / error strings).
                for obj, cells in cutout_rows + dados_rows + miter_rows + slot_rows:
                    for cell in cells:
                        assert_true(cell is not None,
                                    f"{obj.Type} table column empty")
                        assert_true('Error' not in str(cell)
                                    and 'error' not in str(cell),
                                    f"{obj.Type} table cell shows an "
                                    f"error: {cell}")
            finally:
                panel.accept()
        finally:
            restore()
    finally:
        App.closeDocument(doc.Name)


def test_selection_helpers_respect_their_type_argument():
    """is_single/is_nonempty_exclusive must filter by the requested type.

    Regression: both were written with `self.dict[ty.CUTOUT]` -- a typo that
    Python's enum resolves to ShaperCutoutType.CUTOUT regardless of which
    member it is accessed through. So is_single(SVG_PAGE) was really testing
    is_single CUTOUT, and any command whose IsActive used the wrong bucket
    stayed active for the wrong selection (e.g. CreateDados inactive with one
    dados selected, ExportShaperSvgPage active with one cutout selected)."""
    doc = App.newDocument("sel_helpers")
    try:
        _plane, sketch, cutout = _cutout_fixture(doc)
        dados = ShaperDados.create_uninitialized(cutout, "Dados_h2")
        c1, c2, ifp = _slot_fixture(doc)
        slot = ShaperSlot.create_uninitialized(c1, c2, ifp, "Slot_h2")
        doc.recompute()

        sel = Objects([dados])
        assert_true(not sel.is_single(ShaperCutoutType.CUTOUT),
                    "is_single(CUTOUT) false when only a dado is selected")
        assert_true(not sel.is_nonempty_exclusive(ShaperCutoutType.CUTOUT),
                    "is_nonempty_exclusive(CUTOUT) false when only a dado selected")
        assert_true(sel.is_single(ShaperCutoutType.DADOS),
                    "is_single(DADOS) true when only a dado is selected")
        assert_true(sel.is_nonempty_exclusive(ShaperCutoutType.SLOT) is False,
                    "is_nonempty_exclusive(SLOT) is False when only a dado is selected")

        sel = Objects([slot])
        assert_true(sel.is_single(ShaperCutoutType.SLOT),
                    "is_single(SLOT) true for exactly one slot")
        assert_true(not sel.is_single(ShaperCutoutType.CUTOUT),
                    "is_single(CUTOUT) false when only a slot is selected")

        sel = Objects([cutout])
        assert_true(sel.is_single(ShaperCutoutType.CUTOUT),
                    "is_single(CUTOUT) true for exactly one cutout")
        assert_true(not sel.is_single(ShaperCutoutType.DADOS),
                    "is_single(DADOS) false for exactly one cutout")
    finally:
        App.closeDocument(doc.Name)


def register_tests(all_tests):
    all_tests.append(test_type_of)
    all_tests.append(test_selection_helpers_respect_their_type_argument)
    all_tests.append(test_report_view_tables_populate)
