# SPDX-License-Identifier: GPL-3.0-or-later

"""
Regression tests for _PageWidget's viewport metrics (ShaperSvgPage.
page_view_metrics).

This was broken by commit 0b21722 ("ShaperSvgPage: fix page metrics"): in the
width-limited branch, `avail_h = avail_w * page_ar` should have been
`avail_h = avail_w / page_ar`. This caused all sorts of weird broken-looking
behavior.
"""

import FreeCAD as App

import ShaperSvgPage
from util import assert_true, assert_eq, mm


MIN_PAD = 2  # mirrored from page_view_metrics


def _assert_metrics_invariants(widget_w, widget_h, page_w_mm, page_h_mm,
                               grid_mm):
    """Assert every invariant stated in page_view_metrics' docstring."""
    m = ShaperSvgPage.page_view_metrics(widget_w, widget_h, page_w_mm,
                                        page_h_mm, grid_mm)
    assert_true(m is not None,
                f"widget {widget_w}x{widget_h} page {page_w_mm}x{page_h_mm}: "
                "metrics returned")
    pad_x, pad_y, grid_px, avail_w, avail_h = m

    # The viewport must fit inside the widget exactly: avail + 2*pad == widget.
    assert_eq("avail_w + 2*pad_x == widget_w", avail_w + 2 * pad_x, widget_w)
    assert_eq("avail_h + 2*pad_y == widget_h", avail_h + 2 * pad_y, widget_h)

    # Padding can never be negative (otherwise the viewport overflows the
    # widget and the content is scaled/clipped against the wrong rect).
    assert_true(pad_x >= 0, f"pad_x {pad_x} >= 0 (widget {widget_w}x{widget_h})")
    assert_true(pad_y >= 0, f"pad_y {pad_y} >= 0 (widget {widget_w}x{widget_h})")

    # The rendered viewport must preserve the page's aspect ratio, so that
    # QSvgRenderer's fill of the rect is a uniform (isometric) scale.
    assert_eq("avail aspect == page aspect (widget "
              f"{widget_w}x{widget_h})",
              avail_w / avail_h, page_w_mm / page_h_mm, tol=1e-9)

    # The pixel ratio must be the same on both axes and match avail/page,
    # which is what _hit_test / mouseMoveEvent rely on when converting mouse
    # pixels to page millimeters.
    px_ratio = grid_px / grid_mm
    assert_eq("grid_px/grid_mm == avail_w/page_w", px_ratio,
              avail_w / page_w_mm, tol=1e-9)
    assert_eq("grid_px/grid_mm == avail_h/page_h", px_ratio,
              avail_h / page_h_mm, tol=1e-9)

    # The page must fit inside the widget on both axes.
    assert_true(avail_w <= widget_w and avail_h <= widget_h,
                f"viewport {avail_w}x{avail_h} fits widget "
                f"{widget_w}x{widget_h}")


def test_page_metrics_invariants():
    """Viewport metrics obey their documented invariants for a matrix of
    window shapes and page aspect ratios (portrait, landscape, square,
    extreme)."""
    page_shapes = [
        ('24 in', '12 in', '1 in'),   # ShaperSvgPage default-ish, 2:1
        ('8 ft', '4 ft', '1 in'),     # the default page, 2:1
        ('12 in', '24 in', '1 in'),   # portrait 1:2
        ('1000', '1000', '50'),       # square
        ('2400', '300', '25.4'),      # extreme strip 8:1
        ('300', '2400', '25.4'),      # extreme strip 1:8
    ]
    widget_shapes = [
        (1000, 700),   # typical MDI subwindow, landscape ~1.43:1
        (800, 600),    # 4:3
        (600, 900),    # portrait
        (1900, 400),   # very wide and short
        (400, 1900),   # very tall and narrow
    ]
    for pw_s, ph_s, grid_s in page_shapes:
        # Bare numbers are already interpreted as mm by Quantity.
        page_w = App.Units.Quantity(pw_s).Value
        page_h = App.Units.Quantity(ph_s).Value
        grid_mm = App.Units.Quantity(grid_s).Value
        for (ww, wh) in widget_shapes:
            _assert_metrics_invariants(ww, wh, page_w, page_h, grid_mm)


def test_page_metrics_landscape_page_in_landscape_window():
    """Regression for the exact real-world case: the rocker-bassinet page
    (8 ft x 4 ft, aspect 2.0) displayed in a normal landscape MDI subwindow
    (~1.43:1). The page is 'width-limited', which is the branch that was
    broken: avail_h was computed as avail_w * page_ar (= 4x the correct
    height), giving a negative pad_y and stretching the view vertically by
    page_ar, so in-plane Rotation looked like rotation about a tilted axis
    and OffsetX/OffsetY disagreed with the rendered positions.

    Expected for widget 1000x700, page 2438.4x1219.2mm, grid 25.4mm:
      avail_w = 996, avail_h = 498, pad = (2, 101),
      grid_px = 25.4 * 996 / 2438.4
    """
    widget_w, widget_h = 1000.0, 700.0
    page_w = mm(8 * 12)     # 8 ft
    page_h = mm(4 * 12)     # 4 ft
    grid_mm = mm(1)

    pad_x, pad_y, grid_px, avail_w, avail_h = \
        ShaperSvgPage.page_view_metrics(widget_w, widget_h, page_w, page_h,
                                        grid_mm)

    assert_eq("avail_w", avail_w, 996.0)
    assert_eq("avail_h", avail_h, 498.0)
    assert_eq("pad_x", pad_x, float(MIN_PAD))
    assert_eq("pad_y", pad_y, (widget_h - 498.0) / 2.0)
    assert_eq("grid_px", grid_px, grid_mm * 996.0 / page_w)
    assert_eq("avail aspect ratio", avail_w / avail_h, 2.0, tol=1e-9)

    _assert_metrics_invariants(widget_w, widget_h, page_w, page_h, grid_mm)


def test_page_metrics_degenerate():
    """Zero/negative dimensions and tiny widgets return None."""
    assert_true(ShaperSvgPage.page_view_metrics(1000, 700, 0, 1000, 25) is None,
                "zero page width -> None")
    assert_true(ShaperSvgPage.page_view_metrics(1000, 700, 1000, -5, 25) is None,
                "negative page height -> None")
    assert_true(ShaperSvgPage.page_view_metrics(1, 700, 1000, 1000, 25) is None,
                "widget narrower than 2*min_pad -> None")


def register_tests(all_tests):
    all_tests.append(test_page_metrics_invariants)
    all_tests.append(test_page_metrics_landscape_page_in_landscape_window)
    all_tests.append(test_page_metrics_degenerate)
