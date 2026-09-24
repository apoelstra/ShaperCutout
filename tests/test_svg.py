# SPDX-License-Identifier: GPL-3.0-or-later

import math
import os
import re

import FreeCAD as App
import Part
import ShaperCutout
import ShaperMiter
import ShaperSlot
import ShaperSvgPage
import ShaperSvgImage
import Sketcher
from shaper_cutout_svg import SvgData, SvgAnchorFrame, SvgAnchorPlacer, SvgAnchorPlacerMode

from util import assert_true
from util import make_plane, mm

MASTER_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "masters")
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")


def make_rect_sketch(doc, plane, name, width, height, x_offset=0, y_offset=0):
    """Create a rectangular sketch on the given plane."""
    sketch = doc.addObject("Sketcher::SketchObject", name)
    sketch.Label = name
    sketch.AttachmentSupport = (plane, [''])
    sketch.MapMode = 'FlatFace'

    half_w = width / 2.0
    half_h = height / 2.0

    p1 = App.Vector(-half_w + x_offset, -half_h + y_offset, 0)
    p2 = App.Vector(half_w + x_offset, -half_h + y_offset, 0)
    p3 = App.Vector(half_w + x_offset, half_h + y_offset, 0)
    p4 = App.Vector(-half_w + x_offset, half_h + y_offset, 0)

    sketch.addGeometry(Part.LineSegment(p1, p2), False)
    sketch.addGeometry(Part.LineSegment(p2, p3), False)
    sketch.addGeometry(Part.LineSegment(p3, p4), False)
    sketch.addGeometry(Part.LineSegment(p4, p1), False)

    sketch.addConstraint(Sketcher.Constraint('Coincident', 0, 2, 1, 1))
    sketch.addConstraint(Sketcher.Constraint('Coincident', 1, 2, 2, 1))
    sketch.addConstraint(Sketcher.Constraint('Coincident', 2, 2, 3, 1))
    sketch.addConstraint(Sketcher.Constraint('Coincident', 3, 2, 0, 1))
    sketch.addConstraint(Sketcher.Constraint('Horizontal', 0))
    sketch.addConstraint(Sketcher.Constraint('Vertical', 1))
    sketch.addConstraint(Sketcher.Constraint('DistanceX', 0, width))
    sketch.addConstraint(Sketcher.Constraint('DistanceY', 1, height))

    return sketch


def make_cutout(doc, plane, name, thickness=mm(0.5)):
    """Create a ShaperCutout with the given plane, outline sketch, and thickness."""
    cutout = ShaperCutout.create_uninitialized(name)
    cutout.Label = name
    cutout.CenterPlane = plane
    cutout.Thickness = thickness
    cutout.Proxy.ensure_front_face(cutout)
    cutout.Proxy.ensure_back_face(cutout)
    return cutout


def make_rect_cutout(doc, name, thickness=mm(0.5)):
    """Create a simple rectangular cutout (4\" x 6\")."""
    plane = make_plane(doc, name + "_plane")
    sketch = make_rect_sketch(doc, plane, name + "_sketch", mm(4), mm(6))
    cutout = make_cutout(doc, plane, name, thickness)
    cutout.OutlineSketch = sketch
    return cutout


def get_straight_edge_names(sketch):
    """Get the list of EdgeN subnames for straight edges in a sketch."""
    doc = sketch.Document
    doc.recompute()
    names = []
    for i, edge in enumerate(sketch.Shape.Edges):
        if isinstance(edge.Curve, Part.Line):
            names.append(f'Edge{i + 1}')
    return names


def make_cutout_with_miter(doc, name):
    """Create a cutout with a miter on one edge."""
    cutout = make_rect_cutout(doc, name)
    sketch = cutout.OutlineSketch
    edge_names = get_straight_edge_names(sketch)
    if edge_names:
        ShaperMiter.create(cutout, [(sketch, [edge_names[0]])], 15, "Center", "Miter")
    doc.recompute()
    return cutout


def make_two_cutouts_with_slot(doc, name1="C1_slot", name2="C2_slot"):
    """Create two perpendicular cutouts with a slot between them."""
    p1_plane = make_plane(doc, name1 + "_plane", rot=(0, 0, 0))
    p2_plane = make_plane(doc, name2 + "_plane", rot=(0, 0, 90))

    p1_sketch = make_rect_sketch(doc, p1_plane, name1 + "_sketch", mm(4), mm(6))
    p2_sketch = make_rect_sketch(doc, p2_plane, name2 + "_sketch", mm(4), mm(6))

    c1 = make_cutout(doc, p1_plane, name1)
    c1.OutlineSketch = p1_sketch
    c2 = make_cutout(doc, p2_plane, name2)
    c2.OutlineSketch = p2_sketch

    interface = make_plane(doc, "Interface", rot=(0, 45, 0))
    slot = ShaperSlot.create_uninitialized(c1, c2, interface, "Slot")
    slot.Cutout1_FrontDadoDepth = mm(0.1)
    slot.Cutout2_FrontDadoDepth = mm(0.1)

    doc.recompute()
    return c1, c2, slot


def export_svg_front(cutout):
    """Export the front-face SVG for a cutout."""
    return SvgData(cutout, export_front=True).extract_complete_svg()


def export_svg_back(cutout):
    """Export the back-face SVG for a cutout."""
    return SvgData(cutout, export_front=False).extract_complete_svg()


def assert_svg_eq(test_svg, master_file):
    """Compare a test SVG string against a master file.
    Returns (match: bool, message: str)."""
    if not os.path.exists(master_file):
        # Create master if it doesn't exist
        os.makedirs(os.path.dirname(master_file), exist_ok=True)
        with open(master_file, 'w') as f:
            f.write(test_svg)
        return

    with open(master_file, 'r') as f:
        master_svg = f.read()

    if test_svg != master_svg:
        # Show diff info
        test_lines = test_svg.splitlines()
        master_lines = master_svg.splitlines()
        min_len = min(len(test_lines), len(master_lines))
        errstr = ""
        diffs = 0
        for i in range(min_len):
            if test_lines[i] != master_lines[i]:
                diffs += 1
                if diffs <= 3:
                    errstr += f"  Line {i+1} differs:\n"
                    errstr += f"    test:   {test_lines[i][:80]}\n"
                    errstr += f"    master: {master_lines[i][:80]}\n"
        errstr += f"MISMATCH: {diffs} line(s) differ\n"
        if len(test_lines) != len(master_lines):
            errstr += f"  Line count differs: test={len(test_lines)}, master={len(master_lines)}\n"
        raise ValueError(errstr)


# ============================================================================
# 1. SVG export tests (front and back, with masters)
# ============================================================================

def test_svg_export_simple_front():
    """Export SVG of a simple cutout's front face and compare against master."""
    doc = App.newDocument("test_svg_simple_front")
    try:
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        cutout = make_rect_cutout(doc, "Simple")
        doc.recompute()

        svg = export_svg_front(cutout)
        assert_true(len(svg) > 0, "page SVG is non-empty")

        # Save test output
        test_file = os.path.join(OUTPUT_DIR, "svg_simple_front.svg")
        with open(test_file, 'w') as f:
            f.write(svg)

        # Compare against master
        master_file = os.path.join(MASTER_DIR, "svg_simple_front.master")
        assert_svg_eq(svg, master_file)
    except Exception as e:
        App.Console.PrintError(f"  ERROR: {e}")
        raise e
    finally:
        App.closeDocument(doc.Name)


def test_svg_export_simple_back():
    """Export SVG of a simple cutout's back face and compare against master."""
    doc = App.newDocument("test_svg_simple_back")
    try:
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        cutout = make_rect_cutout(doc, "Simple")
        doc.recompute()

        svg = export_svg_back(cutout)
        test_file = os.path.join(OUTPUT_DIR, "svg_simple_back.svg")
        with open(test_file, 'w') as f:
            f.write(svg)

        master_file = os.path.join(MASTER_DIR, "svg_simple_back.master")
        assert_svg_eq(svg, master_file)
    except Exception as e:
        App.Console.PrintError(f"  ERROR: {e}")
        raise e
    finally:
        App.closeDocument(doc.Name)


def test_svg_export_with_miter_front():
    """Export SVG of a cutout with a miter, front face."""
    doc = App.newDocument("test_svg_miter_front")
    try:
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        cutout = make_cutout_with_miter(doc, "Mitered")
        doc.recompute()

        svg = export_svg_front(cutout)
        assert_true(len(svg) > 0, "page SVG is non-empty")

        # Verify SVG contains miter path (blue stroke, guide cutType)
        has_miter = 'stroke="blue"' in svg and 'cutType="guide"' in svg
        assert_true(has_miter, "miter SVG contains guide paths")

        test_file = os.path.join(OUTPUT_DIR, "svg_miter_front.svg")
        with open(test_file, 'w') as f:
            f.write(svg)

        master_file = os.path.join(MASTER_DIR, "svg_miter_front.master")
        assert_svg_eq(svg, master_file)
    except Exception as e:
        App.Console.PrintError(f"  ERROR: {e}")
        raise e
    finally:
        App.closeDocument(doc.Name)


def test_svg_export_with_slot_front():
    """Export SVG of two cutouts with a slot, front face."""
    doc = App.newDocument("test_svg_slot_front")
    try:
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        c1, c2, slot = make_two_cutouts_with_slot(doc)
        doc.recompute()

        # Check slot data
        svg = export_svg_front(c1)
        assert_true(len(svg) > 0, "page SVG is non-empty")

        # Verify SVG contains slot dado paths (cutDepth attribute)
        # Note: slot_data_for may return None in headless mode if the datum plane
        # surfaces don't intersect properly, so we check conditionally
        has_dado = 'cutDepth' in svg
        assert_true(has_dado, "slot SVG contains dado depth")

        test_file = os.path.join(OUTPUT_DIR, "svg_slot_front.svg")
        with open(test_file, 'w') as f:
            f.write(svg)

        master_file = os.path.join(MASTER_DIR, "svg_slot_front.master")
        assert_svg_eq(svg, master_file)
    except Exception as e:
        App.Console.PrintError(f"  ERROR: {e}")
        raise e
    finally:
        App.closeDocument(doc.Name)


def test_svg_export_back_is_mirrored():
    """Verify that front and back SVGs are different (mirrored)."""
    doc = App.newDocument("test_svg_mirror")
    try:
        cutout = make_rect_cutout(doc, "Mirror")
        doc.recompute()

        front_svg = export_svg_front(cutout)
        back_svg = export_svg_back(cutout)

        # They should be different (front is mirrored relative to back)
        are_different = front_svg != back_svg
        assert_true(are_different, "front and back SVGs are different")
    except Exception as e:
        App.Console.PrintError(f"  ERROR: {e}")
        raise e
    finally:
        App.closeDocument(doc.Name)


def test_svg_export_with_circle_front():
    """Regression: a circle in the outline sketch appears in the exported SVG.

    draftfunctions renders a wire that is a single complete circle as a
    compact <circle> element instead of a <path>, so d-attribute-based path
    extraction silently dropped sketch circles from the SVG even though the
    3D cutout volume correctly accounted for them.
    """
    doc = App.newDocument("test_svg_circle_front")
    try:
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        cutout = make_rect_cutout(doc, "Circle")
        doc.recompute()
        svg_without = export_svg_front(cutout)
        assert_true('<circle' not in svg_without, "no <circle> before sketch edit")

        # Punch a 10mm-radius hole at (10, 20) in the outline sketch. The
        # volume must drop by the cylinder's volume.
        vol_before = sum(s.Volume for s in cutout.Shape.Solids)
        cutout.OutlineSketch.addGeometry(
            Part.Circle(App.Vector(10, 20, 0), App.Vector(0, 0, 1), 10), False)
        doc.recompute()
        vol_after = sum(s.Volume for s in cutout.Shape.Solids)
        expected_drop = math.pi * 10.0 * 10.0 * mm(0.5)
        assert_true(abs((vol_before - vol_after) - expected_drop) < 0.1,
                    f"3D volume dropped by the circle cut ({expected_drop})")

        svg = export_svg_front(cutout)
        assert_true(svg != svg_without, "SVG changes when a circle is added")
        assert_true(svg.count('<circle') == 1, "SVG contains exactly one <circle>")

        m = re.search(r'<circle cx="([^"]+)" cy="([^"]+)" r="([^"]+)"[^>]*'
                      r'shaper:cutType="inside"/>', svg)
        assert_true(m is not None, f'circle element with inside cutType:\n{svg}')
        # The front export mirrors x (see SvgData.__init__), so the projected
        # center is (-10, 20).
        assert_true(abs(float(m.group(1)) + 10.0) < 1e-6, "circle cx is projected/mirrored")
        assert_true(abs(float(m.group(2)) - 20.0) < 1e-6, "circle cy is projected")
        assert_true(abs(float(m.group(3)) - 10.0) < 1e-6, "circle radius is 10mm")

        test_file = os.path.join(OUTPUT_DIR, "svg_circle_front.svg")
        with open(test_file, 'w') as f:
            f.write(svg)

        master_file = os.path.join(MASTER_DIR, "svg_circle_front.master")
        assert_svg_eq(svg, master_file)
    except Exception as e:
        App.Console.PrintError(f"  ERROR: {e}")
        raise e
    finally:
        App.closeDocument(doc.Name)


# ============================================================================
# 2. ShaperSvgPage layout tests
# ============================================================================

def make_svg_page_with_image(doc, cutout, name, offset_x=0, offset_y=0,
                             rotation=0, flip=False, invert=False, include_anchor=False):
    """Create a ShaperSvgPage with a single ShaperSvgImage of the given cutout."""
    page = ShaperSvgPage.create(name + "_page")
    page.Label = name + "_page"
    page.Width = '24 in'
    page.Height = '12 in'
    page.GridSpacing = '1 in'

    image = ShaperSvgImage.create(page, cutout, name + "_image")
    image.OffsetX = offset_x
    image.OffsetY = offset_y
    image.Rotation = rotation
    image.Flip = flip
    image.Invert = invert

    doc.recompute()
    if include_anchor:
        frame = SvgAnchorFrame(App.Vector(0, 0, 0), App.Vector(1, 0, 0), App.Vector(0, 1, 0))
        page.Proxy.set_anchor_frame(page, frame)
        doc.recompute()
    return page, image


def test_svg_page_single_piece():
    """Create an SVG page with a single piece at default offset."""
    doc = App.newDocument("test_svg_page_single")
    try:
        cutout = make_rect_cutout(doc, "Single")
        page, image = make_svg_page_with_image(doc, cutout, "Single")

        # Compute the page SVG
        svg = page.Proxy.compute_svg(page)
        assert_true(len(svg) > 0, "page SVG is non-empty")

        # Verify the SVG contains the page border and the piece
        has_border = 'shaper:cutType="guide"' in svg
        has_piece = 'shaper:cutType="outside"' in svg
        assert_true(has_border, "page SVG has border")
        assert_true(has_piece, "page SVG has piece outline")

        # Verify the image has been computed (non-empty SVG)
        has_svg_full = len(image.Svg_Full) > 0
        has_svg_bb = image.Svg_BBLength.Length > 0
        assert_true(has_svg_full, "image has Svg_Full")
        assert_true(has_svg_bb, "image has bounding box")
    except Exception as e:
        App.Console.PrintError(f"  ERROR: {e}")
        raise e
    finally:
        App.closeDocument(doc.Name)


def test_svg_page_offset_positions():
    """Create SVG pages with pieces at various offsets."""
    offsets = [(0, 0), (50, 0), (0, 50), (50, 50), (100, 100)]
    for ox, oy in offsets:
        doc = App.newDocument(f"test_svg_page_offset_{ox}_{oy}")
        try:
            cutout = make_rect_cutout(doc, "Offset")
            page, image = make_svg_page_with_image(doc, cutout, "Offset",
                                                   offset_x=ox, offset_y=oy)
            svg = page.Proxy.compute_svg(page)
            assert_true(len(svg) > 0, f"page SVG non-empty at offset ({ox},{oy})")
        except Exception as e:
            App.Console.PrintError(f"  offset=({ox},{oy}): ERROR: {e}")
            raise e
        finally:
            App.closeDocument(doc.Name)


def test_svg_page_rotations():
    """Create SVG pages with pieces at various rotations."""
    angles = [0, 15, 30, 45, 90, 180, -30, -45]
    for angle in angles:
        doc = App.newDocument(f"test_svg_page_rot_{angle}")
        try:
            cutout = make_rect_cutout(doc, "Rotate")
            page, image = make_svg_page_with_image(doc, cutout, "Rotate",
                                                   rotation=angle)
            svg = page.Proxy.compute_svg(page)
            assert_true(len(svg) > 0, f"page SVG non-empty at rotation {angle}")
        except Exception as e:
            App.Console.PrintError(f"  rotation={angle}: ERROR: {e}")
            raise e
        finally:
            App.closeDocument(doc.Name)


def test_svg_page_flip_invert():
    """Create SVG pages with various flip and invert combinations."""
    doc = App.newDocument("test_svg_page_flip_invert")
    try:
        cutout = make_rect_cutout(doc, "FlipInvert")
        page, image = make_svg_page_with_image(doc, cutout, "FlipInvert")

        results = []
        for flip in [False, True]:
            for invert in [False, True]:
                image.Flip = flip
                image.Invert = invert
                doc.recompute()
                svg = page.Proxy.compute_svg(page)
                results.append((flip, invert, len(svg) > 0))
                assert_true(len(svg) > 0, f"SVG non-empty for flip={flip}, invert={invert}")
        return True
    except Exception as e:
        App.Console.PrinError(f"  ERROR: {e}")
        raise e
    finally:
        App.closeDocument(doc.Name)


def test_svg_page_with_miter():
    """Create an SVG page with a piece that has a miter."""
    doc = App.newDocument("test_svg_page_miter")
    try:
        cutout = make_cutout_with_miter(doc, "Mitered")
        page, image = make_svg_page_with_image(doc, cutout, "Mitered",
                                               offset_x=50, offset_y=50,
                                               rotation=30)
        svg = page.Proxy.compute_svg(page)
        assert_true(len(svg) > 0, "page SVG non-empty with miter")

        # Verify SVG contains miter guide paths
        has_miter = 'stroke="blue"' in svg and 'cutType="guide"' in svg
        assert_true(has_miter, "page SVG contains miter guides")

        # Verify Svg_Full contains miter paths
        has_miter_svg = 'stroke="blue"' in image.Svg_Full and 'cutType="guide"' in image.Svg_Full
        assert_true(has_miter_svg, "Svg_Full contains miter guides")
    except Exception as e:
        App.Console.PrintError(f"  ERROR: {e}")
        raise e
    finally:
        App.closeDocument(doc.Name)


def test_svg_page_with_slot():
    """Create an SVG page with pieces that have a slot between them."""
    doc = App.newDocument("test_svg_page_slot")
    try:
        c1, c2, slot = make_two_cutouts_with_slot(doc)
        page, image1 = make_svg_page_with_image(doc, c1, "Slot_c1", offset_x=50, offset_y=50)
        doc.recompute()
        svg = page.Proxy.compute_svg(page)
        assert_true(len(svg) > 0, "page SVG non-empty with slot")

        # Verify SVG contains dado depth attributes from the slot
        has_dado = 'cutDepth' in svg
        assert_true(has_dado, "page SVG contains dado depth from slot")
    except Exception as e:
        App.Console.PrintError(f"  ERROR: {e}")
        raise e
    finally:
        App.closeDocument(doc.Name)


def test_svg_page_multiple_pieces():
    """Create an SVG page with multiple pieces at different positions."""
    doc = App.newDocument("test_svg_page_multi")
    try:
        page = ShaperSvgPage.create("Multi_page")
        page.Label = "Multi_page"
        page.Width = '24 in'
        page.Height = '12 in'
        page.GridSpacing = '1 in'

        # Create 3 pieces with different features
        c1 = make_rect_cutout(doc, "P1")
        c2 = make_cutout_with_miter(doc, "P2_miter")
        c3, c4, slot = make_two_cutouts_with_slot(doc, "P3_slot1", "P4_slot2")

        img1 = ShaperSvgImage.create(page, c1, "P1_image")
        img1.OffsetX = 0
        img1.OffsetY = 0
        img1.Rotation = 0

        img2 = ShaperSvgImage.create(page, c2, "P2_image")
        img2.OffsetX = 100
        img2.OffsetY = 0
        img2.Rotation = 45

        img3 = ShaperSvgImage.create(page, c3, "P3_image")
        img3.OffsetX = 0
        img3.OffsetY = 80
        img3.Rotation = -30

        doc.recompute()

        svg = page.Proxy.compute_svg(page)
        assert_true(len(svg) > 0, "multi-piece page SVG non-empty")

        # Count how many pieces are in the SVG (each has an outside cutType)
        outside_count = svg.count('cutType="outside"')
        assert_true(outside_count >= 3, f"at least 3 pieces in SVG (got {outside_count})")
    except Exception as e:
        App.Console.PrintError(f"  ERROR: {e}")
        raise e
    finally:
        App.closeDocument(doc.Name)


def test_svg_page_rotation_changes_svg():
    """Verify that rotation actually changes the SVG output."""
    doc = App.newDocument("test_svg_page_rot_change")
    try:
        cutout = make_rect_cutout(doc, "RotChange")
        page, image = make_svg_page_with_image(doc, cutout, "RotChange")

        image.Rotation = 0
        doc.recompute()
        svg_0 = page.Proxy.compute_svg(page)

        image.Rotation = 90
        doc.recompute()
        svg_90 = page.Proxy.compute_svg(page)
        assert_true(svg_0 != svg_90, "rotation changes SVG output")

        # The SVG should contain a rotate transform with the rotation value
        has_rot_0 = 'rotate(180' in svg_0  # 0 + 180 = 180
        assert_true(has_rot_0, "0deg rotation produces rotate(180) in SVG")
        has_rot_90 = 'rotate(270' in svg_90  # 90 + 180 = 270
        assert_true(has_rot_90, "90deg rotation produces rotate(270) in SVG")
    except Exception as e:
        App.Console.PrintError(f"  ERROR: {e}")
        raise e
    finally:
        App.closeDocument(doc.Name)


def test_svg_page_with_anchor():
    """Auto-placing an anchor stores a positioned anchor on the page."""
    doc = App.newDocument("test_svg_page_anchor")
    try:
        cutout = make_rect_cutout(doc, "Anchor")
        page, image = make_svg_page_with_image(doc, cutout, "Anchor")

        # No anchor by default.
        assert_true(not page.HasAnchor, "no anchor by default")
        svg = page.Proxy.compute_svg(page)
        assert_true('fill="red"' not in svg, "no anchor in SVG by default")

        frame = SvgAnchorFrame(App.Vector(0, 0, 0), App.Vector(1, 0, 0), App.Vector(0, 1, 0))
        page.Proxy.set_anchor_frame(page, frame)
        svg = page.Proxy.compute_svg(page)
        assert_true(page.HasAnchor, "HasAnchor set after placing")
        assert_true('fill="red"' in svg, "page SVG contains anchor")

        # The anchor lives on the page, not the image.
        assert_true(not hasattr(image, 'IncludeAnchor'),
                    "image has no per-image IncludeAnchor property")
        assert_true(not hasattr(image, 'Svg_Anchor'),
                    "image has no per-image Svg_Anchor property")

        # The stored anchor is within the page, with a sensible orientation.
        assert_true(-1e-6 <= page.AnchorX.Value <= page.Width.Value + 1e-6,
                    "anchor X within page")
        assert_true(-1e-6 <= page.AnchorY.Value <= page.Height.Value + 1e-6,
                    "anchor Y within page")

        # Disabling HasAnchor hides the anchor but keeps the stored position.
        x0, y0 = page.AnchorX.Value, page.AnchorY.Value
        page.HasAnchor = False
        svg_off = page.Proxy.compute_svg(page)
        assert_true('fill="red"' not in svg_off, "anchor absent when disabled")
        assert_true(page.AnchorX.Value == x0 and page.AnchorY.Value == y0,
                    "position retained when disabled")
        page.HasAnchor = True

        # The anchor is a fixed point: moving the piece does not move it.
        anchor_before = (page.AnchorX.Value, page.AnchorY.Value)
        image.OffsetX = 100
        doc.recompute()
        assert_true((page.AnchorX.Value, page.AnchorY.Value) == anchor_before,
                    "anchor stays put when the piece moves")
    except Exception as e:
        App.Console.PrintError(f"  ERROR: {e}")
        raise e
    finally:
        App.closeDocument(doc.Name)


def test_svg_page_anchor_frames():
    """Manual anchor placement primitives: vertex frames, intersection frames,
    and the stored-frame round trip."""
    doc = App.newDocument("test_svg_page_anchor_frames")
    try:
        page = ShaperSvgPage.create("Frames_page")
        placer = SvgAnchorPlacer(SvgAnchorPlacerMode.VERTEX)  # mode irrelevant the way we use it
        page.Width = '24 in'
        page.Height = '12 in'
        cutout = make_rect_cutout(doc, "Frames")
        image = ShaperSvgImage.create(page, cutout, "Frames_image")
        image.OffsetX = 50
        image.OffsetY = 50
        doc.recompute()

        # Snapping: a corner of the rect is a snap point.
        placer.set_page_data(page.Width, page.Height, page.Proxy._collect_snap_wires(page))
        segs = placer._line_segments
        assert_true(len(segs) >= 4, "page has line segments")
        corner = segs[0][0]
        snap = placer._snap_point_near(corner, 5.0)
        assert_true(snap is not None and (snap - corner).Length < 1e-6,
                    "corner point snaps")
        far = placer._snap_point_near(App.Vector(-500, -500, 0), 5.0)
        assert_true(far is None, "off-object point does not snap")

        # Vertex frame aligns the long leg with an incident edge.
        frame = placer._frame_for_vertex(corner)
        assert_true((frame.vertex - corner).Length < 1e-9, "vertex frame at the vertex")
        aligned = any(abs(abs(d.dot(frame.long_dir())) - 1.0) < 1e-6
                      for p0, p1 in segs if (p0 - corner).Length < 1e-3 or
                      (p1 - corner).Length < 1e-3
                      for d in [(p1 - p0).normalize()])
        assert_true(aligned, "vertex frame long leg aligns with an incident edge")

        # Intersection frames: two perpendicular edges of the rect.
        horiz = max(segs, key=lambda s: abs(s[1].x - s[0].x))
        vert = max(segs, key=lambda s: abs(s[1].y - s[0].y))
        frame, ortho = placer._frame_for_intersection(horiz, vert)
        assert_true(frame is not None, "perpendicular edges intersect")
        assert_true(ortho, "perpendicular edges report orthogonal")
        # Long leg aligns with the FIRST clicked segment.
        d1 = (horiz[1] - horiz[0]).normalize()
        assert_true(abs(abs(d1.dot(frame.long_dir())) - 1.0) < 1e-6,
                    "intersection frame long leg aligns with first segment")

        # Parallel segments have no intersection.
        par = [s for s in segs if abs(abs(((s[1] - s[0]).normalize()).dot(d1)) - 1.0) < 1e-6]
        assert_true(len(par) >= 2, "found two parallel segments")
        frame, ortho = placer._frame_for_intersection(par[0], par[1])
        assert_true(frame is None, "parallel lines produce no intersection")

        # Non-orthogonal pair (a rotated second object provides an angled edge).
        sketch = doc.addObject("Sketcher::SketchObject", "Diag")
        sketch.AttachmentSupport = (doc.getObject("Frames_plane"), [''])
        sketch.MapMode = 'FlatFace'
        sketch.addGeometry(Part.LineSegment(App.Vector(0, 0, 0),
                                            App.Vector(100, 30, 0)), False)
        import ShaperSvgShape
        shape = ShaperSvgShape.create(page, sketch, "Diag_shape")
        shape.OffsetX = 400
        doc.recompute()
        placer.set_page_data(page.Width, page.Height, page.Proxy._collect_snap_wires(page))
        segs = placer._line_segments
        diag = next(s for s in segs
                    if abs((s[1] - s[0]).y) > 1 and abs((s[1] - s[0]).x) > 1)
        frame, ortho = placer._frame_for_intersection(horiz, diag)
        assert_true(frame is not None and not ortho,
                    "angled pair reports non-orthogonal")

        # Stored-frame round trip: anchor_triangle reproduces what was set.
        page.Proxy.set_anchor_frame(page, frame)
        tri = page.Proxy.anchor_triangle(page)
        pts = tri.Vertexes
        assert_true(len(pts) == 3, "anchor triangle has 3 vertices")
        origin = App.Vector(page.AnchorX.Value, page.AnchorY.Value, 0)
        assert_true(min((v.Point - origin).Length for v in pts) < 1e-9,
                    "triangle vertex sits at stored origin")
    except Exception as e:
        App.Console.PrintError(f"  ERROR: {e}")
        raise e
    finally:
        App.closeDocument(doc.Name)


def test_export_to_svg_page():
    """'Export to ShaperSvgPage' creates a page sized to the cutout with one child."""
    from shaper_cutout_command.export_to_shaper_svg_page import create_page

    doc = App.newDocument("test_export_to_svg_page")
    try:
        cutout = make_rect_cutout(doc, "ExportPiece")
        page = create_page(cutout)

        assert_true(getattr(page, 'Type', None) == 'ShaperSvgPage',
                    "export creates a ShaperSvgPage")
        assert_true(len(page.Group) == 1,
                    f"page has exactly one child (got {len(page.Group)})")
        image = page.Group[0]
        assert_true(getattr(image, 'Type', None) == 'ShaperSvgImage',
                    "page child is a ShaperSvgImage")
        assert_true(image.Cutout is cutout, "image links to the cutout")

        # The page is sized exactly to the cutout bounding box (4" x 6").
        assert_true(abs(page.Width.Value - image.Svg_BBLength.x) < 1e-6,
                    f"page width matches cutout ({page.Width.Value} vs {image.Svg_BBLength.x})")
        assert_true(abs(page.Height.Value - image.Svg_BBLength.y) < 1e-6,
                    f"page height matches cutout ({page.Height.Value} vs {image.Svg_BBLength.y})")
        assert_true(abs(page.Width.Value - mm(4)) < 1e-6,
                    f"page width is cutout width {mm(4)}mm (got {page.Width.Value})")
        assert_true(abs(page.Height.Value - mm(6)) < 1e-6,
                    f"page height is cutout height {mm(6)}mm (got {page.Height.Value})")

        svg = page.Proxy.compute_svg(page)
        assert_true('cutType="outside"' in svg, "page SVG contains piece outline")
    except Exception as e:
        App.Console.PrintError(f"  ERROR: {e}")
        raise e
    finally:
        App.closeDocument(doc.Name)


def test_svg_page_min_distance_rotated():
    """The 'minimum distance' display works for rotated images, not just
    axis-aligned ones. distToShape returns two endpoint pairs only when the
    closest features are parallel (axis-aligned placements); with a small
    rotation the closest pair is unique, and compute_overlaps must still
    report it (issue #24)."""
    doc = App.newDocument("test_svg_page_min_dist")
    try:
        c1 = make_rect_cutout(doc, "MinDistA")
        c2 = make_rect_cutout(doc, "MinDistB")
        page = ShaperSvgPage.create("MinDist_page")
        page.Width = '24 in'
        page.Height = '12 in'
        page.GridSpacing = '1 in'
        i1 = ShaperSvgImage.create(page, c1, "MinDist_iA")
        i1.OffsetX = 0
        i1.OffsetY = 0
        i2 = ShaperSvgImage.create(page, c2, "MinDist_iB")
        # 4" (101.6mm) wide rects placed 131.6mm apart -> 30mm gap.
        i2.OffsetX = 131.6
        i2.OffsetY = 0
        doc.recompute()

        # Axis-aligned: closest features are parallel edges; 30mm apart.
        _, close = page.Proxy.compute_overlaps(page)
        assert_true(len(close) == 1, "axis-aligned pair reports a distance")
        assert_true(abs(close[0][2].Value - 30.0) < 1e-6,
                    f"axis-aligned gap is 30mm (got {close[0][2].Value})")

        # Rotate the second image a few degrees: the closest feature is now a
        # unique corner, so distToShape yields a single pair -- this must not
        # break the distance display.
        i2.Rotation = 3
        doc.recompute()
        _, close = page.Proxy.compute_overlaps(page)
        assert_true(len(close) == 1, "rotated pair still reports a distance")
        assert_true(close[0][2].Value < 30.0,
                    "rotated gap is smaller than axis-aligned gap")

        # Moving them out of range (> 50mm) hides the distance again.
        i2.OffsetX = 0
        i2.OffsetY = 400
        doc.recompute()
        _, close = page.Proxy.compute_overlaps(page)
        assert_true(len(close) == 0, "far-apart rotated pair reports nothing")
    except Exception as e:
        App.Console.PrintError(f"  ERROR: {e}")
        raise e
    finally:
        App.closeDocument(doc.Name)


def test_svg_image_cutout_deleted():
    """Deleting the cutout behind a ShaperSvgImage must remove its stale
    geometry from the page SVG (same round-5 fuzz bug class as the shape
    wrapper: the image kept exporting the deleted piece's face)."""
    doc = App.newDocument("t_svg_image_cutdel")
    try:
        cutout = make_rect_cutout(doc, "Piece")
        doc.recompute()
        page, image = make_svg_page_with_image(doc, cutout, "Del")
        svg_before = page.Proxy.compute_svg(page)
        assert_true(len(svg_before) > len('<svg') + 200,
                    "image renders the cutout face")

        doc.removeObject(cutout.Name)
        doc.recompute()
        assert_true(image.Svg_Full == '', "stale image paths cleared")
        assert_true(image.Svg_TranslatedFace.isNull(),
                    "translated-face cache cleared")
        svg_after = page.Proxy.compute_svg(page)
        assert_true(len(svg_after) < len(svg_before),
                    "deleted piece disappears from the page SVG")
    finally:
        App.closeDocument(doc.Name)


def register_tests(all_tests):
    # SVG export comparison tests
    all_tests.append(test_svg_export_simple_front)
    all_tests.append(test_svg_export_simple_back)
    all_tests.append(test_svg_export_with_miter_front)
    all_tests.append(test_svg_export_with_slot_front)
    all_tests.append(test_svg_export_back_is_mirrored)
    all_tests.append(test_svg_export_with_circle_front)
    # SVG page layout tests
    all_tests.append(test_svg_page_single_piece)
    all_tests.append(test_svg_page_offset_positions)
    all_tests.append(test_svg_page_rotations)
    all_tests.append(test_svg_page_flip_invert)
    all_tests.append(test_svg_page_with_miter)
    all_tests.append(test_svg_page_with_slot)
    all_tests.append(test_svg_page_multiple_pieces)
    all_tests.append(test_svg_page_rotation_changes_svg)
    all_tests.append(test_svg_page_with_anchor)
    all_tests.append(test_svg_page_anchor_frames)
    all_tests.append(test_svg_page_min_distance_rotated)
    all_tests.append(test_export_to_svg_page)
    all_tests.append(test_svg_image_cutout_deleted)
