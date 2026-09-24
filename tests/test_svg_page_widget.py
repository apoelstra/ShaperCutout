# SPDX-License-Identifier: GPL-3.0-or-later

import sys
import time
import FreeCAD as App
from PySide import QtGui, QtWidgets

from ShaperSvgPage import _PageWidget
import ShaperSvgPage

from util import assert_true

GRID_MM = 10.0


def _qapp():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def _make_page(doc, name, w_mm=600, h_mm=300):
    page = ShaperSvgPage.create(name + "_page")
    page.Label = name + "_page"
    page.Width = f'{w_mm} mm'
    page.Height = f'{h_mm} mm'
    page.GridSpacing = f'{GRID_MM} mm'
    doc.recompute()
    return page


def _make_widget(page, w_px=604, h_px=304):
    """A _PageWidget sized so that grid_px == GridSpacing mm (1:1 px/mm),
    with pad_x == pad_y == 2: avail = 600x300 for a 604x304 widget and a
    600x300 page at 10mm grid."""
    _qapp()
    widget = _PageWidget(page)
    widget.resize(w_px, h_px)
    widget.update_svg()
    return widget


def test_page_view_close_after_page_deleted_1():
    """Regression: closing the page MDI view after the page object was
    deleted from the document used to raise AttributeError out of the Qt
    closeEvent override (ViewObject becomes None after deletion; only
    NameError was caught)."""
    doc = App.newDocument("view_close_deleted")
    page = _make_page(doc, "Del")
    widget = _make_widget(page)
    doc.removeObject(page.Name)
    doc.recompute()
    # Must not raise.
    widget.closeEvent(QtGui.QCloseEvent())
    App.closeDocument(doc.Name)


def test_page_view_close_after_page_deleted_2():
    """Same as test_page_view_close_after_page_deleted_1 but doesn't call
    widget.closeEvent before closing the doc."""
    doc = App.newDocument("view_close_deleted")
    page = _make_page(doc, "Del")
    _make_widget(page)
    doc.removeObject(page.Name)
    doc.recompute()
    # Must not raise.
    App.closeDocument(doc.Name)




def test_page_widget_pending_overlap_timer_after_doc_close():
    """Regression: the page view's overlap-recompute timer chains itself every
    100ms with a captured page reference. Closing the document inside a timer
    window used to fire the callback against the deleted page, raising
    ReferenceError from the Qt callback. The chain must now end silently."""

    doc = App.newDocument("line_timer_close")
    page = _make_page(doc, "Timer")
    widget = _make_widget(page)
    widget.update_svg()          # arms the pending 100ms timer
    App.closeDocument(doc.Name)  # page dies while the timer is still queued

    errors = []
    old_hook = sys.excepthook
    sys.excepthook = lambda t, v, tb: errors.append((t, v))
    try:
        end = time.time() + 0.6  # well past the 100ms timer window
        while time.time() < end:
            QtWidgets.QApplication.processEvents()
            time.sleep(0.02)
    finally:
        sys.excepthook = old_hook

    referrs = [f"{t.__name__}: {v}" for t, v in errors
               if issubclass(t, ReferenceError)]
    assert_true(not referrs,
                f"pending overlap timer raised after doc close: {referrs}")


def register_tests(all_tests):
    all_tests.append(test_page_view_close_after_page_deleted_1)
    all_tests.append(test_page_view_close_after_page_deleted_2)
    all_tests.append(test_page_widget_pending_overlap_timer_after_doc_close)
