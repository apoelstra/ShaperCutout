# SPDX-License-Identifier: GPL-3.0-or-later

import os

import FreeCAD as App
import Part
import ShaperCutout
import ShaperMiter
import ShaperSlot
import ShaperSvgPage
import ShaperSvgImage
import Sketcher
from shaper_cutout_svg import SvgData

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
    image.IncludeAnchor = include_anchor

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
    """Create an SVG page with a piece that includes an anchor."""
    doc = App.newDocument("test_svg_page_anchor")
    try:
        cutout = make_rect_cutout(doc, "Anchor")
        page, image = make_svg_page_with_image(doc, cutout, "Anchor", include_anchor=True)
        svg = page.Proxy.compute_svg(page)
        assert_true(len(svg) > 0, "page SVG non-empty with anchor")

        # Verify SVG contains anchor (red fill, no stroke)
        has_anchor = 'fill="red"' in svg
        assert_true(has_anchor, "page SVG contains anchor")
    except Exception as e:
        App.Console.PrintError(f"  ERROR: {e}")
        raise e
    finally:
        App.closeDocument(doc.Name)


def register_tests(all_tests):
    # SVG export comparison tests
    all_tests.append(test_svg_export_simple_front)
    all_tests.append(test_svg_export_simple_back)
    all_tests.append(test_svg_export_with_miter_front)
    all_tests.append(test_svg_export_with_slot_front)
    all_tests.append(test_svg_export_back_is_mirrored)
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
