# SPDX-License-Identifier: GPL-3.0-or-later
"""GUI-fuzzing regression tests: the report view dialog and page-widget
mouse handling must not raise.

The report dialog is exercised the same way the other dialogs are (open /
okay / cancel). The page widget is driven through the same event handlers
Qt invokes when the user mouses around: hover moves, presses, drags,
releases, and wheel events, including over page children.
"""

import types

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore, QtGui, QtWidgets

import ShaperCutout  # noqa: F401
import ShaperSvgPage
import ShaperSvgImage
import ShaperSvgShape

from shaper_cutout_command.report_view import ReportViewTaskPanel

from ShaperSvgPage import _PageWidget

from util import assert_true, make_cutout, make_plane, make_sketch, mm, stub_selection


def _qapp():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def _page_with_children(doc, with_children=True):
    """A page; optionally with a cutout image and a shape child on it."""
    page = ShaperSvgPage.create("Page")
    page.Width = '600 mm'
    page.Height = '300 mm'
    page.GridSpacing = '10 mm'
    if with_children:
        plane = make_plane(doc, "Plane")
        sketch = make_sketch(doc, plane, "Rect")
        cutout = make_cutout(doc, plane, "Cutout")
        cutout.OutlineSketch = sketch
        doc.recompute()
        ShaperSvgImage.create(page, cutout, "img")
        #ShaperSvgShape.create(page, sketch, "shape")
    doc.recompute()
    return page


def _make_widget(page, w_px=604, h_px=304):
    """Same 1:1 px/mm sizing trick as test_svg_page_widget."""
    widget = _PageWidget(page)
    widget.resize(w_px, h_px)
    widget.update_svg()
    return widget


# ============================================================================
# Report view dialog
# ============================================================================

class _StubbedControl:
    def __init__(self):
        self.close_calls = 0

    def activeDialog(self):
        return False

    def closeDialog(self):
        self.close_calls += 1

    def showDialog(self, panel):
        pass


class _FakeUiLoader:
    def createWidget(self, name):
        return QtWidgets.QWidget()


class _FakeTemplate:
    """Stand-in for the expression-engine template (which needs a real
    ViewObject / Gui.ExpressionBinding)."""

    def bind(self, widget, prop, initial):
        pass

    def update_object(self, obj, prop):
        pass


def _stub_report_gui_services():
    """Stub the headless-missing GUI services the report sections use, so
    the test exercises the real panel logic (table population, buttons)."""
    import shaper_cutout_command.report_view.cutouts as cutouts
    import shaper_cutout_command.report_view.dados as dados
    import shaper_cutout_command.report_view.miters as miters
    import shaper_cutout_command.report_view.slots as slots

    modules = (cutouts, dados, miters, slots)
    saved_templates = [(m, m.make_expr_template) for m in modules]
    for m in modules:
        m.make_expr_template = lambda *a, **k: _FakeTemplate()

    saved_ui_loader = getattr(Gui, 'UiLoader', None)
    Gui.UiLoader = _FakeUiLoader

    control = _StubbedControl()
    saved_control = getattr(Gui, 'Control', None)
    Gui.Control = control

    def restore():
        for m, fn in saved_templates:
            m.make_expr_template = fn
        if saved_ui_loader is not None:
            Gui.UiLoader = saved_ui_loader
        else:
            try:
                del Gui.UiLoader
            except AttributeError:
                pass
        if saved_control is not None:
            Gui.Control = saved_control
        else:
            try:
                del Gui.Control
            except AttributeError:
                pass

    return control, restore


def test_report_view_open_okay_cancel():
    """Opening the report view panel must not raise, and okay/cancel must
    close the transaction and the dialog."""
    _qapp()
    doc = App.newDocument("dlg_report")
    try:
        plane = make_plane(doc, "Plane")
        sketch = make_sketch(doc, plane, "Rect")
        cutout = make_cutout(doc, plane, "Cutout")
        cutout.OutlineSketch = sketch
        dsk = make_sketch(doc, plane, "DadoSketch")
        import ShaperDados
        dados = ShaperDados.create_uninitialized(cutout, "Dados")
        dados.Face = cutout.FrontFace
        dados.Sketches = [dsk]
        doc.recompute()

        control, restore = _stub_report_gui_services()
        try:
            panel = ReportViewTaskPanel()
            assert_true(panel.form is not None, "report panel built its form")
            panel.accept()
            assert_true(control.close_calls == 1,
                        f"okay closed the dialog "
                        f"(close_calls={control.close_calls})")

            panel2 = ReportViewTaskPanel()
            panel2.reject()
            assert_true(control.close_calls == 2,
                        f"cancel closed the dialog "
                        f"(close_calls={control.close_calls})")
        finally:
            restore()
    finally:
        App.closeDocument(doc.Name)


# ============================================================================
# Page widget mouse handling
# ============================================================================

def _hover(widget, x, y):
    widget.mouseMoveEvent(QtGui.QMouseEvent(
        QtCore.QEvent.MouseMove, QtCore.QPointF(x, y),
        QtCore.Qt.NoButton, QtCore.Qt.NoButton, QtCore.Qt.NoModifier))


def _press(widget, x, y):
    widget.mousePressEvent(QtGui.QMouseEvent(
        QtCore.QEvent.MouseButtonPress, QtCore.QPointF(x, y),
        QtCore.Qt.LeftButton, QtCore.Qt.LeftButton, QtCore.Qt.NoModifier))


def _release(widget, x, y):
    widget.mouseReleaseEvent(QtGui.QMouseEvent(
        QtCore.QEvent.MouseButtonRelease, QtCore.QPointF(x, y),
        QtCore.Qt.LeftButton, QtCore.Qt.NoButton, QtCore.Qt.NoModifier))


def _wheel(widget, x, y, delta=120):
    widget.wheelEvent(QtGui.QWheelEvent(
        QtCore.QPointF(x, y), QtCore.QPointF(x, y),
        QtCore.QPoint(0, delta), QtCore.QPoint(0, delta),
        QtCore.Qt.NoButton, QtCore.Qt.NoModifier,
        QtCore.Qt.ScrollUpdate, False))


def test_page_widget_mouse_around():
    """Mousing around the page (hover / press / drag / release / wheel,
    on children and on empty page) must not raise."""
    _qapp()
    doc = App.newDocument("page_mouse")
    try:
        page = _page_with_children(doc)
        widget = _make_widget(page)
        stub_selection([])

        # Sweep a grid of positions: over the child (center-ish), over empty
        # page, and over padding. The image sits at the page bottom-left.
        positions = [(302, 152), (302, 200), (10, 10), (600, 300), (2, 2)]
        for x, y in positions:
            _hover(widget, x, y)
        for x, y in positions:
            _press(widget, x, y)
            _release(widget, x, y)
        for x, y in positions:
            _wheel(widget, x, y)

        # A press-move-release drag over the child position.
        _press(widget, 302, 152)
        _hover(widget, 312, 162)
        _hover(widget, 322, 172)
        _release(widget, 322, 172)

        widget.deleteLater()
        QtWidgets.QApplication.processEvents()
    finally:
        App.closeDocument(doc.Name)


def test_page_widget_mouse_drag_moves_child():
    """Dragging a child with the mouse must move it (the mouse handlers do
    the move; a pure hover must not)."""
    _qapp()
    doc = App.newDocument("page_mouse_drag")
    try:
        page = _page_with_children(doc)
        widget = _make_widget(page)
        stub_selection([])

        target = widget._hit_test(QtCore.QPoint(20, 280))
        assert_true(target is not None,
                    "press position must land on a page child")
        x0 = target.OffsetX.Value

        # Click on the child and drag right/down by 30 px (= 30 mm at 1:1).
        # Down is clamped at the page's bottom edge, so only X moves.
        _press(widget, 20, 280)
        _hover(widget, 50, 310)
        _release(widget, 50, 310)
        QtWidgets.QApplication.processEvents()

        assert_true(abs(target.OffsetX.Value - (x0 + 30)) < 1e-6,
                    f"drag moved the image by ~30mm in X "
                    f"(moved {target.OffsetX.Value - x0})")

        widget.deleteLater()
        QtWidgets.QApplication.processEvents()
    finally:
        App.closeDocument(doc.Name)


def register_tests(all_tests):
    all_tests.append(test_report_view_open_okay_cancel)
    all_tests.append(test_page_widget_mouse_around)
    all_tests.append(test_page_widget_mouse_drag_moves_child)
