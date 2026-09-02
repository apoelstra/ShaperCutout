# SPDX-License-Identifier: GPL-3.0-or-later

"""
Integration tests for ShaperSvgShape: putting arbitrary sketches / Draft
objects onto a ShaperSvgPage.
"""

import FreeCAD as App
import Part

import ShaperSvgPage
import ShaperSvgShape

from util import assert_true


def _make_page(doc, name):
    page = ShaperSvgPage.create(name + "_page")
    page.Label = name + "_page"
    page.Width = '24 in'
    page.Height = '12 in'
    page.GridSpacing = '1 in'
    return page


def _make_plane(doc, name, origin=(100, 200, 5), rot_z=30):
    """A datum plane deliberately placed off-origin and rotated, so that tests
    catch projection errors."""
    plane = doc.addObject("Part::DatumPlane", name)
    plane.Label = name
    plane.Placement = App.Placement(App.Vector(*origin), App.Rotation(0, 0, rot_z))
    return plane


def _make_closed_sketch(doc, plane, name, width_mm=40, height_mm=60, with_hole=False):
    sketch = doc.addObject("Sketcher::SketchObject", name)
    sketch.Label = name
    sketch.AttachmentSupport = (plane, [''])
    sketch.MapMode = 'FlatFace'
    hw, hh = width_mm / 2.0, height_mm / 2.0
    p1 = App.Vector(-hw, -hh, 0)
    p2 = App.Vector(hw, -hh, 0)
    p3 = App.Vector(hw, hh, 0)
    p4 = App.Vector(-hw, hh, 0)
    sketch.addGeometry(Part.LineSegment(p1, p2), False)
    sketch.addGeometry(Part.LineSegment(p2, p3), False)
    sketch.addGeometry(Part.LineSegment(p3, p4), False)
    sketch.addGeometry(Part.LineSegment(p4, p1), False)
    if with_hole:
        sketch.addGeometry(
            Part.Circle(App.Vector(0, 0, 0), App.Vector(0, 0, 1), 5), False)
    doc.recompute()
    return sketch


def _make_open_sketch(doc, plane, name, length_mm=30):
    """A sketch with a single open wire."""
    sketch = doc.addObject("Sketcher::SketchObject", name)
    sketch.Label = name
    sketch.AttachmentSupport = (plane, [''])
    sketch.MapMode = 'FlatFace'
    sketch.addGeometry(
        Part.LineSegment(App.Vector(0, 0, 0), App.Vector(length_mm, 0, 0)), False)
    sketch.addGeometry(
        Part.LineSegment(App.Vector(length_mm, 0, 0),
                         App.Vector(length_mm, 10, 0)), False)
    doc.recompute()
    return sketch


def _bbox_page_coords(shape, page):
    """Compute the bbox left / bottom (y-up from page bottom) of how the shape
    lands on the page, using the same transforms the page uses to render."""
    cx, cy = shape.Proxy.centerXY(shape)
    tx, ty = shape.Proxy.translateXY(shape, page.Height.Value)
    left = tx + (cx - shape.Svg_BBLength.x / 2)
    bottom = page.Height.Value - (ty + cy + shape.Svg_BBLength.y / 2)
    return left, bottom


# ============================================================================
# Tests
# ============================================================================

def test_svg_shape_basic():
    """A sketch on a page produces a ShaperSvgShape whose SVG renders and has
    default cutType=outside, no cutDepth."""
    doc = App.newDocument("t_svg_shape_basic")
    try:
        plane = _make_plane(doc, "Plane")
        sketch = _make_closed_sketch(doc, plane, "Rect")
        page = _make_page(doc, "Basic")
        shape = ShaperSvgShape.create(page, sketch, "RectShape")

        assert_true(shape in page.Group, "shape is in the page Group")
        assert_true(len(shape.Svg_Full) > 0, "Svg_Full is populated")
        assert_true(shape.Svg_Full.count('shaper:cutType="outside"') == 1,
                    "closed wire defaults to outside cutType")
        assert_true('cutDepth' not in shape.Svg_Full, "no cutDepth by default")
        assert_true(abs(shape.Svg_BBLength.x - 40) < 1e-6
                    and abs(shape.Svg_BBLength.y - 60) < 1e-6,
                    "bounding box matches the sketch (40x60)")

        page_svg = page.Proxy.compute_svg(page)
        assert_true('shaper:cutType="outside"' in page_svg,
                    "page SVG includes the shape")
    finally:
        App.closeDocument(doc.Name)


def test_svg_shape_offset_normalization():
    """At offset (0, 0) the shape's bbox bottom-left lands at the page's bottom
    left corner; setting OffsetX/OffsetY moves it as expected (with Y measured
    up from the bottom, matching ShaperSvgImage)."""
    doc = App.newDocument("t_svg_shape_offset")
    try:
        plane = _make_plane(doc, "Plane")
        sketch = _make_closed_sketch(doc, plane, "Rect")
        page = _make_page(doc, "Offset")
        shape = ShaperSvgShape.create(page, sketch, "RectShape")

        left, bottom = _bbox_page_coords(shape, page)
        assert_true(abs(left) < 1e-6 and abs(bottom) < 1e-6,
                    f"zero offsets place bbox bottom-left at page origin "
                    f"(got {left}, {bottom})")

        shape.OffsetX = 100
        shape.OffsetY = 50
        doc.recompute()
        left, bottom = _bbox_page_coords(shape, page)
        assert_true(abs(left - 100) < 1e-6 and abs(bottom - 50) < 1e-6,
                    f"offsets 100/50 honored (got {left}, {bottom})")
    finally:
        App.closeDocument(doc.Name)


def test_svg_shape_circle_wire():
    """Sketch circles (which draftfunctions renders as <circle> elements)
    appear in the shape SVG."""
    doc = App.newDocument("t_svg_shape_circle")
    try:
        plane = _make_plane(doc, "Plane")
        sketch = _make_closed_sketch(doc, plane, "RectHole", with_hole=True)
        page = _make_page(doc, "Circle")
        shape = ShaperSvgShape.create(page, sketch, "HoleShape")

        assert_true('<circle' in shape.Svg_Full,
                    "sketch circle renders as a <circle> element")
        assert_true(shape.Svg_Full.count('shaper:cutType="outside"') == 2,
                    "both rect and circle get the closed-wire cutType")
    finally:
        App.closeDocument(doc.Name)


def test_svg_shape_open_wire():
    """Open wires use OpenWireType; the synthetic closing Z segment is removed;
    guide wires are stroked blue."""
    doc = App.newDocument("t_svg_shape_open")
    try:
        plane = _make_plane(doc, "Plane")
        sketch = _make_open_sketch(doc, plane, "Open")
        page = _make_page(doc, "OpenWire")
        shape = ShaperSvgShape.create(page, sketch, "OpenShape")

        assert_true('shaper:cutType="guide"' in shape.Svg_Full,
                    "open wires default to guide")
        assert_true('stroke="blue"' in shape.Svg_Full,
                    "guide wires are blue")

        # The path must not contain a closing Z segment.
        import re
        d = re.search(r'd="([^"]+)"', shape.Svg_Full).group(1)
        assert_true(not d.rstrip().endswith('Z'),
                    f"open wire path is not closed: {d}")

        shape.OpenWireType = 'on line'
        doc.recompute()
        assert_true('shaper:cutType="onLine"' in shape.Svg_Full,
                    "OpenWireType=on line produces onLine cutType")
        # Closed wires are unaffected by the open wire type.
        assert_true('shaper:cutType="outside"' not in shape.Svg_Full,
                    "no closed wires in an open-only shape")
    finally:
        App.closeDocument(doc.Name)


def test_svg_shape_cut_types():
    """ClosedWireType selects guide/onLine/inside/outside."""
    doc = App.newDocument("t_svg_shape_cuttypes")
    try:
        plane = _make_plane(doc, "Plane")
        sketch = _make_closed_sketch(doc, plane, "Rect")
        page = _make_page(doc, "CutTypes")
        shape = ShaperSvgShape.create(page, sketch, "RectShape")

        for cut_type, svg_type in [('guide', 'guide'), ('on line', 'onLine'),
                                   ('inside', 'inside'), ('outside', 'outside')]:
            shape.ClosedWireType = cut_type
            doc.recompute()
            assert_true(f'shaper:cutType="{svg_type}"' in shape.Svg_Full,
                        f"ClosedWireType '{cut_type}' produces '{svg_type}'")
    finally:
        App.closeDocument(doc.Name)


def test_svg_shape_cut_depth():
    """CutDepthEnabled + CutDepth add/remove shaper:cutDepth."""
    doc = App.newDocument("t_svg_shape_depth")
    try:
        plane = _make_plane(doc, "Plane")
        sketch = _make_closed_sketch(doc, plane, "Rect")
        page = _make_page(doc, "Depth")
        shape = ShaperSvgShape.create(page, sketch, "RectShape")

        assert_true('cutDepth' not in shape.Svg_Full, "disabled by default")

        shape.CutDepthEnabled = True
        shape.CutDepth = '3 mm'
        doc.recompute()
        assert_true('shaper:cutDepth="3.0000mm"' in shape.Svg_Full,
                    f"enabled cut depth appears: {shape.Svg_Full}")

        shape.CutDepthEnabled = False
        doc.recompute()
        assert_true('cutDepth' not in shape.Svg_Full, "disabled again removes it")
    finally:
        App.closeDocument(doc.Name)


def test_svg_shape_source_change():
    """Editing the source sketch updates the shape SVG."""
    doc = App.newDocument("t_svg_shape_source")
    try:
        plane = _make_plane(doc, "Plane")
        sketch = _make_closed_sketch(doc, plane, "Rect")
        page = _make_page(doc, "Source")
        shape = ShaperSvgShape.create(page, sketch, "RectShape")
        old_svg = shape.Svg_Full

        sketch.addGeometry(
            Part.LineSegment(App.Vector(60, 60, 0), App.Vector(70, 60, 0)), False)
        doc.recompute()
        assert_true(shape.Svg_Full != old_svg,
                    "source geometry edit propagates to the shape SVG")
    finally:
        App.closeDocument(doc.Name)


def test_svg_shape_draft_object():
    """A Draft wire object can be added to a page."""
    doc = App.newDocument("t_svg_shape_draft")
    try:
        import Draft
        dw = Draft.make_wire(
            [App.Vector(0, 0, 0), App.Vector(40, 0, 0), App.Vector(40, 25, 0)])
        doc.recompute()

        page = _make_page(doc, "Draft")
        shape = ShaperSvgShape.create(page, dw, "DraftShape")

        assert_true(len(shape.Svg_Full) > 0, "draft wire produces SVG")
        assert_true(abs(shape.Svg_BBLength.x - 40) < 1e-6
                    and abs(shape.Svg_BBLength.y - 25) < 1e-6,
                    "draft wire bounding box is 40x25")
    finally:
        App.closeDocument(doc.Name)


def test_svg_shape_overlap_detection():
    """Two overlapping shapes on a page are reported by compute_overlaps."""
    doc = App.newDocument("t_svg_shape_overlap")
    try:
        page = _make_page(doc, "Overlap")

        # Two closed sketches at overlapping page offsets.
        p1 = _make_plane(doc, "P1")
        p2 = _make_plane(doc, "P2")
        s1 = _make_closed_sketch(doc, p1, "S1", width_mm=50, height_mm=50)
        s2 = _make_closed_sketch(doc, p2, "S2", width_mm=50, height_mm=50)

        sh1 = ShaperSvgShape.create(page, s1, "Sh1")
        sh2 = ShaperSvgShape.create(page, s2, "Sh2")
        sh1.OffsetX = 0
        sh1.OffsetY = 0
        sh2.OffsetX = 20  # overlaps sh1 (both 50 wide)
        sh2.OffsetY = 0
        doc.recompute()

        overlaps, _ = page.Proxy.compute_overlaps(page)
        pair_names = [{a.Name, b.Name} for a, b, _ in overlaps]
        assert_true({sh1.Name, sh2.Name} in pair_names,
                    f"overlapping shapes detected (got {pair_names})")
    finally:
        App.closeDocument(doc.Name)


def test_svg_shape_group_filter():
    """The page Group accepts ShaperSvgShape children but rejects random
    objects."""
    doc = App.newDocument("t_svg_shape_group")
    try:
        page = _make_page(doc, "Filter")
        plane = _make_plane(doc, "Plane")
        sketch = _make_closed_sketch(doc, plane, "Rect")
        shape = ShaperSvgShape.create(page, sketch, "RectShape")
        assert_true(shape in page.Group, "shape stays in group")

        page.addObject(plane)
        assert_true(plane not in page.Group, "datum plane rejected from group")
    finally:
        App.closeDocument(doc.Name)


def test_svg_shape_save_restore():
    """Save / restore roundtrip preserves properties and regenerates the SVG."""
    import os
    path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "output", "shape_restore.FCStd")
    os.makedirs(os.path.dirname(path), exist_ok=True)

    doc = App.newDocument("t_svg_shape_restore")
    try:
        plane = _make_plane(doc, "Plane")
        sketch = _make_closed_sketch(doc, plane, "Rect")
        page = _make_page(doc, "Restore")
        shape = ShaperSvgShape.create(page, sketch, "RectShape")
        shape.OffsetX = 77
        shape.ClosedWireType = 'inside'
        shape.CutDepthEnabled = True
        doc.recompute()

        doc.saveAs(path)
    finally:
        App.closeDocument(doc.Name)

    doc = App.openDocument(path)
    try:
        shape = doc.getObject("RectShape")
        assert_true(getattr(shape, 'Type', '') == 'ShaperSvgShape',
                    "restored object has the right Type")
        assert_true(abs(shape.OffsetX.Value - 77) < 1e-6, "OffsetX restored")
        assert_true(shape.ClosedWireType == 'inside', "ClosedWireType restored")
        assert_true(shape.CutDepthEnabled, "CutDepthEnabled restored")
        assert_true(len(shape.Svg_Full) > 0, "Svg_Full regenerated after restore")
        assert_true('shaper:cutType="inside"' in shape.Svg_Full,
                    "restored SVG uses the restored cut type")
    finally:
        App.closeDocument(doc.Name)
        if os.path.exists(path):
            os.remove(path)


def register_tests(all_tests):
    all_tests.append(test_svg_shape_basic)
    all_tests.append(test_svg_shape_offset_normalization)
    all_tests.append(test_svg_shape_circle_wire)
    all_tests.append(test_svg_shape_open_wire)
    all_tests.append(test_svg_shape_cut_types)
    all_tests.append(test_svg_shape_cut_depth)
    all_tests.append(test_svg_shape_source_change)
    all_tests.append(test_svg_shape_draft_object)
    all_tests.append(test_svg_shape_overlap_detection)
    all_tests.append(test_svg_shape_group_filter)
    all_tests.append(test_svg_shape_save_restore)
