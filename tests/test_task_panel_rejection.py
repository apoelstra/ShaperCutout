# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for task-panel create-flow rejection paths (found by GUI fuzzing).

When a create panel declines to proceed (invalid selection/geometry) it must:
  * not crash in ShaperTaskPanel.__init__ on the None object,
  * abort the undo transaction it opened (no leaked open transaction),
  * let the open_* helper swallow the rejection quietly.

The slot panel additionally had a broken invert handler (self._slot instead
of self._object, and a missing recompute_objects argument) -- toggling the
checkbox always raised AttributeError in the GUI.
"""

import types

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtWidgets

import ShaperCutout  # noqa: F401
import ShaperDados  # noqa: F401
import ShaperSlot  # noqa: F401

from shaper_cutout_command.create_shaper_slot import (
    ShaperSlotTaskPanel, open_slot_task_panel)
from shaper_cutout_command.task_panel import ShaperTaskPanel

from util import assert_true, make_cutout, make_plane, make_sketch, mm


def _qapp():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def _stub_selection(objects):
    Gui.Selection = types.SimpleNamespace(
        getSelection=lambda: list(objects),
        getSelectionEx=lambda: [],
    )
    return getattr(Gui, 'Selection')


class _StubbedWarning:
    """Capture QMessageBox.warning calls instead of showing a modal."""

    def __init__(self):
        self.messages = []
        self._real = QtWidgets.QMessageBox.warning

    def __enter__(self):
        def fake(parent, title, text, *a, **k):
            self.messages.append((title, str(text)))
            return QtWidgets.QMessageBox.StandardButton.Ok
        QtWidgets.QMessageBox.warning = staticmethod(fake)
        return self

    def __exit__(self, *exc):
        QtWidgets.QMessageBox.warning = self._real


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


def _slot_pair(doc):
    """Two orthogonal cutouts + interface plane (valid geometry)."""
    p1 = make_plane(doc, "P1", origin=(0, 0, 0), rot=(0, 0, 0))
    p2 = make_plane(doc, "P2", origin=(0, 0, 0), rot=(0, 0, 90))
    s1 = make_sketch(doc, p1, "P1_outline", closed=True)
    s2 = make_sketch(doc, p2, "P2_outline", closed=True)
    c1 = make_cutout(doc, p1, "C1")
    c1.OutlineSketch = s1
    c2 = make_cutout(doc, p2, "C2")
    c2.OutlineSketch = s2
    doc.recompute()
    return c1, c2


def test_slot_panel_rejects_parallel_interface_plane():
    """Regression: with a parallel interface plane the panel warned, then
    crashed on self._object.Label, leaking the open undo transaction."""
    _qapp()
    doc = App.newDocument("slot_reject")
    old_control = getattr(Gui, 'Control', None)
    try:
        c1, c2 = _slot_pair(doc)
        # Parallel to C1's center plane -> rejection branch.
        ifp = make_plane(doc, "IFP", origin=(0, 0, mm(5)), rot=(0, 0, 0))
        doc.recompute()
        _stub_selection([c1, c2, ifp])
        control = _StubbedControl()
        Gui.Control = control

        with _StubbedWarning() as warns:
            open_slot_task_panel()   # must not raise

        assert_true(len(warns.messages) == 1,
                    f"expected one warning, got {warns.messages}")
        assert_true('Parallel' in warns.messages[0][0]
                    or 'parallel' in warns.messages[0][1],
                    f"unexpected warning: {warns.messages}")
        assert_true(control.shown == [], "panel should not have been shown")
        slots = [o for o in doc.Objects if getattr(o, 'Type', '') == 'ShaperSlot']
        assert_true(slots == [], f"rejection created a slot: {slots}")

        # The transaction must have been aborted: undo must be a no-op
        # (a leaked open transaction would swallow the next undo or crash
        # the next panel construction).
        n_before = len(doc.Objects)
        doc.undo()
        doc.recompute()
        assert_true(len(doc.Objects) == n_before,
                    "undo after rejection removed objects "
                    "(leaked transaction)")

        # And a subsequent valid panel must still construct cleanly.
        good_ifp = make_plane(doc, "IFP2", origin=(0, 0, mm(2)), rot=(0, 90, 0))
        doc.recompute()
        _stub_selection([c1, c2, good_ifp])
        old_widget = ShaperTaskPanel._quantity_widget
        ShaperTaskPanel._quantity_widget = \
            lambda self, prop, minimum=None, maximum=None: QtWidgets.QWidget()
        try:
            with _StubbedWarning():
                open_slot_task_panel()
        finally:
            ShaperTaskPanel._quantity_widget = old_widget
        assert_true(len(control.shown) == 1, "valid panel should be shown")
        panel = control.shown[0]
        panel.reject()
        assert_true(
            [o for o in doc.Objects if getattr(o, 'Type', '') == 'ShaperSlot']
            == [], "rejected valid panel left a slot")
    except Exception:
        raise
    finally:
        if old_control is not None:
            Gui.Control = old_control
        else:
            try:
                del Gui.Control
            except AttributeError:
                pass
        App.closeDocument(doc.Name)


def test_slot_panel_invert_checkbox_toggles():
    """Regression: _on_invert_changed used self._slot (never assigned) and
    called recompute_objects() without its required argument, so toggling
    'Invert' in the live GUI always raised AttributeError."""
    _qapp()
    doc = App.newDocument("slot_invert")
    try:
        c1, c2 = _slot_pair(doc)
        ifp = make_plane(doc, "IFP", origin=(0, 0, mm(2)), rot=(0, 90, 0))
        doc.recompute()
        _stub_selection([c1, c2, ifp])
        old_widget = ShaperTaskPanel._quantity_widget
        ShaperTaskPanel._quantity_widget = \
            lambda self, prop, minimum=None, maximum=None: QtWidgets.QWidget()
        try:
            panel = ShaperSlotTaskPanel()
        finally:
            ShaperTaskPanel._quantity_widget = old_widget
        try:
            before = panel._object.Invert
            panel.invert_checkbox.setChecked(not before)
            panel._on_invert_changed()
            assert_true(panel._object.Invert == (not before),
                        "invert checkbox did not update the slot object")
        finally:
            doc.abortTransaction()
    finally:
        App.closeDocument(doc.Name)


def register_tests(all_tests):
    all_tests.extend([
        test_slot_panel_rejects_parallel_interface_plane,
        test_slot_panel_invert_checkbox_toggles,
    ])
