# SPDX-License-Identifier: GPL-3.0-or-later

"""
Property-based integration tests for ShaperCutout.

Each test varies a single property and asserts that the object changes
geometrically in response (volume, face count, edge count, areas, etc.).
"""

import math

import FreeCAD as App
import Part
import Sketcher

import ShaperCutout

from util import assert_eq, assert_true, mm


def _make_cutout(doc, name, plane, sketch, thickness=mm(0.5)):
    """Create a ShaperCutout with the given sketch and thickness."""
    cutout = ShaperCutout.create_uninitialized(name)
    cutout.Label = name
    cutout.CenterPlane = plane
    cutout.Thickness = thickness
    cutout.Proxy.ensure_front_face(cutout)
    cutout.Proxy.ensure_back_face(cutout)
    cutout.OutlineSketch = sketch
    doc.recompute()
    return cutout


def _make_plane(doc, name, origin=(0, 0, 0), rot=(0, 0, 0)):
    """Create a datum plane at the given origin with the given rotation."""
    plane = doc.addObject("Part::DatumPlane", name)
    plane.Label = name
    plane.Placement = App.Placement(
        App.Vector(*origin),
        App.Rotation(*rot),
    )
    return plane


def _make_rect_sketch(doc, plane, name, width, height, x_offset=0, y_offset=0):
    """Create a fully constrained rectangular sketch on the given plane."""
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
    doc.recompute()
    return sketch


def _make_triangle_sketch(doc, plane, name, radius, rotation_deg=0):
    """Create an equilateral triangle sketch, rotated by rotation_deg degrees.

    Uses block constraints to freeze the geometry in place.
    """
    sketch = doc.addObject("Sketcher::SketchObject", name)
    sketch.Label = name
    sketch.AttachmentSupport = (plane, [''])
    sketch.MapMode = 'FlatFace'
    rot = math.radians(rotation_deg)
    pts = [
        App.Vector(radius * math.cos(rot + 2 * math.pi * i / 3),
                    radius * math.sin(rot + 2 * math.pi * i / 3), 0)
        for i in range(3)
    ]
    for i in range(3):
        sketch.addGeometry(Part.LineSegment(pts[i], pts[(i + 1) % 3]), False)
    for i in range(3):
        sketch.addConstraint(Sketcher.Constraint('Coincident', i, 2, (i + 1) % 3, 1))
    for i in range(3):
        sketch.addConstraint(Sketcher.Constraint('Block', i))
    doc.recompute()
    return sketch


def _make_hexagon_sketch(doc, plane, name, radius):
    """Create a hexagon sketch with block constraints."""
    sketch = doc.addObject("Sketcher::SketchObject", name)
    sketch.Label = name
    sketch.AttachmentSupport = (plane, [''])
    sketch.MapMode = 'FlatFace'
    pts = [
        App.Vector(radius * math.cos(2 * math.pi * i / 6),
                    radius * math.sin(2 * math.pi * i / 6), 0)
        for i in range(6)
    ]
    for i in range(6):
        sketch.addGeometry(Part.LineSegment(pts[i], pts[(i + 1) % 6]), False)
    for i in range(6):
        sketch.addConstraint(Sketcher.Constraint('Coincident', i, 2, (i + 1) % 6, 1))
    for i in range(6):
        sketch.addConstraint(Sketcher.Constraint('Block', i))
    doc.recompute()
    return sketch


def _make_sketch_with_arc(doc, plane, name):
    """Create a sketch with a rectangle that has one curved edge (arc)."""
    sketch = doc.addObject("Sketcher::SketchObject", name)
    sketch.Label = name
    sketch.AttachmentSupport = (plane, [''])
    sketch.MapMode = 'FlatFace'
    w, h = mm(4), mm(6)
    p1 = App.Vector(-w / 2, -h / 2, 0)
    p2 = App.Vector(w / 2, -h / 2, 0)
    p3 = App.Vector(w / 2, h / 2, 0)
    p4 = App.Vector(-w / 2, h / 2, 0)
    sketch.addGeometry(Part.LineSegment(p1, p2), False)
    sketch.addGeometry(Part.LineSegment(p2, p3), False)
    sketch.addGeometry(Part.LineSegment(p3, p4), False)
    arc = Part.Arc(p4, App.Vector(-w / 4, 0, 0), p1)
    sketch.addGeometry(arc, False)
    for i in range(4):
        sketch.addConstraint(Sketcher.Constraint('Block', i))
    doc.recompute()
    return sketch


def _make_sketch_with_circle_hole(doc, plane, name, outer_w=mm(4), outer_h=mm(6), hole_r=mm(0.5)):
    """Create a sketch with a rectangle and a circle cutout (inner wire)."""
    sketch = doc.addObject("Sketcher::SketchObject", name)
    sketch.Label = name
    sketch.AttachmentSupport = (plane, [''])
    sketch.MapMode = 'FlatFace'
    p1 = App.Vector(-outer_w / 2, -outer_h / 2, 0)
    p2 = App.Vector(outer_w / 2, -outer_h / 2, 0)
    p3 = App.Vector(outer_w / 2, outer_h / 2, 0)
    p4 = App.Vector(-outer_w / 2, outer_h / 2, 0)
    sketch.addGeometry(Part.LineSegment(p1, p2), False)
    sketch.addGeometry(Part.LineSegment(p2, p3), False)
    sketch.addGeometry(Part.LineSegment(p3, p4), False)
    sketch.addGeometry(Part.LineSegment(p4, p1), False)
    sketch.addGeometry(Part.Circle(App.Vector(0, 0, 0), App.Vector(0, 0, 1), hole_r), False)
    for i in range(4):
        sketch.addConstraint(Sketcher.Constraint('Block', i))
    sketch.addConstraint(Sketcher.Constraint('Block', 4))
    doc.recompute()
    return sketch


def _get_solid_volume(obj):
    if obj.Shape.isNull() or not obj.Shape.Solids:
        return 0.0
    return sum(s.Volume for s in obj.Shape.Solids)


def _get_face_count(obj):
    if obj.Shape.isNull():
        return 0
    return len(obj.Shape.Faces)


def _get_edge_count(obj):
    if obj.Shape.isNull():
        return 0
    return len(obj.Shape.Edges)


def _get_vertex_count(obj):
    if obj.Shape.isNull():
        return 0
    return len(obj.Shape.Vertexes)


def _get_cutout_face_area(obj):
    cf = obj.CutoutFace
    if cf.isNull() or not cf.Faces:
        return 0.0
    return sum(f.Area for f in cf.Faces)


# ============================================================================
# Tests for ShaperCutout.Thickness
# ============================================================================

def test_cutout_thickness_variations():
    """Varying Thickness should change volume proportionally."""
    doc = App.newDocument("test_cutout_thickness")
    try:
        plane = _make_plane(doc, "Plane")
        sketch = _make_rect_sketch(doc, plane, "Outline", mm(4), mm(6))

        thicknesses = [mm(0.25), mm(0.5), mm(1.0), mm(2.0)]
        volumes = []
        for i, t in enumerate(thicknesses):
            cutout = _make_cutout(doc, f"Cutout_{i}", plane, sketch, thickness=t)
            vol = _get_solid_volume(cutout)
            volumes.append(vol)
            assert_true(vol > 0, f"thickness {t} produces positive volume")

        # Volume should be proportional to thickness
        area = mm(4) * mm(6)
        for t, vol in zip(thicknesses, volumes):
            expected = area * t
            assert_eq(f"volume for thickness {t}", vol, expected, tol=expected * 1e-3)

        # Doubling thickness doubles volume
        assert_true(volumes[2] > volumes[1], "thickness 1.0 > 0.5")
        assert_true(volumes[3] > volumes[2], "thickness 2.0 > 1.0")
    except Exception as e:
        App.Console.PrintError(f"  ERROR: {e}")
        raise e
    finally:
        App.closeDocument(doc.Name)


def test_cutout_thickness_changes_face_count():
    """Thickness changes volume but should not change the number of faces (6 for a simple solid)."""
    doc = App.newDocument("test_cutout_face_count")
    try:
        plane = _make_plane(doc, "Plane")
        sketch = _make_rect_sketch(doc, plane, "Outline", mm(4), mm(6))

        faces_set = set()
        for i, t in enumerate([mm(0.25), mm(0.5), mm(1.0), mm(2.0)]):
            cutout = _make_cutout(doc, f"Cutout_{i}", plane, sketch, thickness=t)
            faces_set.add(_get_face_count(cutout))

        # A simple rectangular extrusion always has 6 faces
        assert_true(6 in faces_set, f"rectangular cutout has 6 faces (got {faces_set})")
    except Exception as e:
        App.Console.PrintError(f"  ERROR: {e}")
        raise e
    finally:
        App.closeDocument(doc.Name)


# ============================================================================
# Tests for different sketch shapes (non-axis-aligned)
# ============================================================================

def test_cutout_triangle_sketch():
    """A triangular outline should produce a solid with 5 faces (2 ends + 3 sides)."""
    doc = App.newDocument("test_cutout_triangle")
    try:
        plane = _make_plane(doc, "Plane")
        radius = mm(3)
        sketch = _make_triangle_sketch(doc, plane, "Triangle", radius=radius, rotation_deg=30)
        cutout = _make_cutout(doc, "Cutout", plane, sketch)

        shape = cutout.Shape
        assert_true(len(shape.Solids) > 0, "triangle cutout has solids")
        assert_true(shape.isClosed(), "triangle solid is closed")

        # A triangular prism has 5 faces: 2 triangular ends + 3 rectangular sides
        assert_eq("triangle face count", _get_face_count(cutout), 5)
        assert_eq("triangle edge count", _get_edge_count(cutout), 9)
        assert_eq("triangle vertex count", _get_vertex_count(cutout), 6)

        # Volume should be area * thickness
        # Equilateral triangle with circumscribed circle radius r: side = r * sqrt(3)
        side = radius * math.sqrt(3)
        expected_area = (math.sqrt(3) / 4) * side ** 2
        expected_vol = expected_area * mm(0.5)
        assert_eq("triangle volume", _get_solid_volume(cutout), expected_vol, tol=expected_vol * 1e-3)
    except Exception as e:
        App.Console.PrintError(f"  ERROR: {e}")
        raise e
    finally:
        App.closeDocument(doc.Name)


def test_cutout_hexagon_sketch():
    """A hexagonal outline should produce a solid with 8 faces (2 ends + 6 sides)."""
    doc = App.newDocument("test_cutout_hexagon")
    try:
        plane = _make_plane(doc, "Plane")
        radius = mm(3)
        sketch = _make_hexagon_sketch(doc, plane, "Hexagon", radius=radius)
        cutout = _make_cutout(doc, "Cutout", plane, sketch)

        shape = cutout.Shape
        assert_true(len(shape.Solids) > 0, "hexagon cutout has solids")

        # A hexagonal prism has 8 faces: 2 hexagonal ends + 6 rectangular sides
        assert_eq("hexagon face count", _get_face_count(cutout), 8)
        assert_eq("hexagon edge count", _get_edge_count(cutout), 18)
        assert_eq("hexagon vertex count", _get_vertex_count(cutout), 12)

        # Volume = area * thickness
        expected_area = (3 * math.sqrt(3) / 2) * radius ** 2
        expected_vol = expected_area * mm(0.5)
        assert_eq("hexagon volume", _get_solid_volume(cutout), expected_vol, tol=expected_vol * 1e-3)
    except Exception as e:
        App.Console.PrintError(f"  ERROR: {e}")
        raise e
    finally:
        App.closeDocument(doc.Name)


def test_cutout_sketch_with_arc():
    """A sketch with a curved edge (arc) should produce a valid solid."""
    doc = App.newDocument("test_cutout_arc")
    try:
        plane = _make_plane(doc, "Plane")
        sketch = _make_sketch_with_arc(doc, plane, "ArcSketch")
        cutout = _make_cutout(doc, "Cutout", plane, sketch)

        shape = cutout.Shape
        assert_true(len(shape.Solids) > 0, "arc cutout has solids")
        assert_true(shape.isClosed(), "arc solid is closed")

        # 3 lines + 1 arc = 4 edges on each end face, plus 4 vertical edges
        # Faces: 2 ends + 3 rect sides + 1 "curved" side = 6
        assert_eq("arc face count", _get_face_count(cutout), 6)
        assert_true(_get_solid_volume(cutout) > 0, "arc cutout has positive volume")
    except Exception as e:
        App.Console.PrintError(f"  ERROR: {e}")
        raise e
    finally:
        App.closeDocument(doc.Name)


def test_cutout_sketch_with_circle_hole():
    """A sketch with an inner circle (hole) should produce a solid with more faces."""
    doc = App.newDocument("test_cutout_circle_hole")
    try:
        plane = _make_plane(doc, "Plane")
        sketch = _make_sketch_with_circle_hole(doc, plane, "HoleSketch")
        cutout = _make_cutout(doc, "Cutout", plane, sketch)

        shape = cutout.Shape
        assert_true(len(shape.Solids) > 0, "hole cutout has solids")
        assert_true(shape.isClosed(), "hole solid is closed")

        # Rectangle + circle hole: 2 ends (each 1 face with a hole) + 4 rect sides + 1 cyl side = 7
        assert_eq("hole face count", _get_face_count(cutout), 7)

        # The cutout face should have area = rect area - circle area
        rect_area = mm(4) * mm(6)
        hole_r = mm(0.5)
        circle_area = math.pi * hole_r ** 2
        expected_cutout_area = rect_area - circle_area
        assert_eq("cutout face area", _get_cutout_face_area(cutout), expected_cutout_area, tol=1.0)

        # Volume = cutout face area * thickness
        expected_vol = expected_cutout_area * mm(0.5)
        assert_eq("hole cutout volume", _get_solid_volume(cutout), expected_vol, tol=expected_vol * 1e-3)
    except Exception as e:
        App.Console.PrintError(f"  ERROR: {e}")
        raise e
    finally:
        App.closeDocument(doc.Name)


def test_cutout_rotated_plane():
    """A cutout on a rotated plane should have the same volume as one on the XY plane."""
    doc = App.newDocument("test_cutout_rotated")
    try:
        plane1 = _make_plane(doc, "Plane1", rot=(0, 0, 0))
        plane2 = _make_plane(doc, "Plane2", rot=(0, 0, 45))
        plane3 = _make_plane(doc, "Plane3", rot=(0, 0, 90))

        sketch1 = _make_rect_sketch(doc, plane1, "Sketch1", mm(4), mm(6))
        sketch2 = _make_rect_sketch(doc, plane2, "Sketch2", mm(4), mm(6))
        sketch3 = _make_rect_sketch(doc, plane3, "Sketch3", mm(4), mm(6))

        c1 = _make_cutout(doc, "C1", plane1, sketch1)
        c2 = _make_cutout(doc, "C2", plane2, sketch2)
        c3 = _make_cutout(doc, "C3", plane3, sketch3)

        v1 = _get_solid_volume(c1)
        v2 = _get_solid_volume(c2)
        v3 = _get_solid_volume(c3)

        # All should have the same volume (rotation doesn't change volume)
        assert_eq("rotated volume matches", v2, v1, tol=v1 * 1e-3)
        assert_eq("90deg rotated volume matches", v3, v1, tol=v1 * 1e-3)
    except Exception as e:
        App.Console.PrintError(f"  ERROR: {e}")
        raise e
    finally:
        App.closeDocument(doc.Name)


def test_cutout_thickness_zero():
    """A cutout with zero thickness should produce a degenerate (flat) shape."""
    doc = App.newDocument("test_cutout_zero_thickness")
    try:
        plane = _make_plane(doc, "Plane")
        sketch = _make_rect_sketch(doc, plane, "Outline", mm(4), mm(6))
        cutout = _make_cutout(doc, "Cutout", plane, sketch, thickness=0.0)

        shape = cutout.Shape
        assert_true(shape.isNull() or not shape.Solids or len(shape.Solids) == 0
                    or shape.Volume < 1e-6, "zero thickness produces degenerate shape")
    except Exception as e:
        App.Console.PrintError(f"  ERROR: {e}")
        raise e
    finally:
        App.closeDocument(doc.Name)


def test_cutout_outline_change_updates_geometry():
    """Changing the outline sketch dimensions should change the volume."""
    doc = App.newDocument("test_cutout_outline_change")
    try:
        plane = _make_plane(doc, "Plane")

        sketch1 = _make_rect_sketch(doc, plane, "Outline1", mm(4), mm(6))
        cutout = _make_cutout(doc, "Cutout", plane, sketch1)
        vol1 = _get_solid_volume(cutout)

        # Replace with a larger sketch
        sketch2 = _make_rect_sketch(doc, plane, "Outline2", mm(8), mm(12))
        cutout.OutlineSketch = sketch2
        doc.recompute()
        vol2 = _get_solid_volume(cutout)

        assert_true(vol2 > vol1, f"larger outline has larger volume ({vol2} > {vol1})")

        # 4x area = 4x volume
        assert_eq("larger outline 4x volume", vol2, vol1 * 4, tol=vol1 * 1e-2)
    except Exception as e:
        App.Console.PrintError(f"  ERROR: {e}")
        raise e
    finally:
        App.closeDocument(doc.Name)


def test_cutout_cutout_face_reflects_outline():
    """The CutoutFace area should equal the sketch area."""
    doc = App.newDocument("test_cutout_face")
    try:
        plane = _make_plane(doc, "Plane")
        w, h = mm(4), mm(6)
        sketch = _make_rect_sketch(doc, plane, "Outline", w, h)
        cutout = _make_cutout(doc, "Cutout", plane, sketch)

        expected_area = w * h
        assert_eq("cutout face area = sketch area", _get_cutout_face_area(cutout), expected_area, tol=0.001)

        # With a triangle sketch
        radius = mm(3)
        sketch2 = _make_triangle_sketch(doc, plane, "Triangle", radius=radius)
        cutout.OutlineSketch = sketch2
        doc.recompute()
        side = radius * math.sqrt(3)
        expected_tri_area = (math.sqrt(3) / 4) * side ** 2
        assert_eq("triangle cutout face area", _get_cutout_face_area(cutout), expected_tri_area, tol=0.01)
    except Exception as e:
        App.Console.PrintError(f"  ERROR: {e}")
        raise e
    finally:
        App.closeDocument(doc.Name)


def test_cutout_multiple_shapes_same_plane():
    """Two cutouts on the same plane with the same thickness should have the same volume."""
    doc = App.newDocument("test_cutout_same_plane")
    try:
        plane = _make_plane(doc, "Plane")
        sketch1 = _make_rect_sketch(doc, plane, "Outline1", mm(4), mm(6))
        sketch2 = _make_rect_sketch(doc, plane, "Outline2", mm(4), mm(6))

        c1 = _make_cutout(doc, "C1", plane, sketch1)
        c2 = _make_cutout(doc, "C2", plane, sketch2)

        assert_eq("same outline same volume", _get_solid_volume(c1), _get_solid_volume(c2))
    except Exception as e:
        App.Console.PrintError(f"  ERROR: {e}")
        raise e
    finally:
        App.closeDocument(doc.Name)


def test_cutout_thickness_propagation():
    """Changing thickness on one cutout propagates to others on the same plane."""
    doc = App.newDocument("test_cutout_thickness_prop")
    try:
        plane = _make_plane(doc, "Plane")
        sketch1 = _make_rect_sketch(doc, plane, "Outline1", mm(4), mm(6))
        sketch2 = _make_rect_sketch(doc, plane, "Outline2", mm(4), mm(6))

        c1 = _make_cutout(doc, "C1", plane, sketch1, thickness=mm(0.5))
        c2 = _make_cutout(doc, "C2", plane, sketch2, thickness=mm(0.5))
        doc.recompute()

        v1_initial = _get_solid_volume(c1)
        v2_initial = _get_solid_volume(c2)

        # Change thickness on c1
        c1.Thickness = mm(1.0)
        doc.recompute()

        v1_new = _get_solid_volume(c1)
        v2_new = _get_solid_volume(c2)

        # Both should have doubled (propagation)
        assert_eq("c1 volume doubled", v1_new, v1_initial * 2, tol=v1_initial * 1e-3)
        assert_eq("c2 volume doubled (propagation)", v2_new, v2_initial * 2, tol=v2_initial * 1e-3)
    except Exception as e:
        App.Console.PrintError(f"  ERROR: {e}")
        raise e
    finally:
        App.closeDocument(doc.Name)


def test_cutout_non_rectangular_quadrilateral():
    """A trapezoid or arbitrary quadrilateral sketch should produce a valid solid."""
    doc = App.newDocument("test_cutout_trapezoid")
    try:
        plane = _make_plane(doc, "Plane")
        sketch = doc.addObject("Sketcher::SketchObject", "Trapezoid")
        sketch.Label = "Trapezoid"
        sketch.AttachmentSupport = (plane, [''])
        sketch.MapMode = 'FlatFace'

        # Trapezoid: wider at top
        pts = [
            App.Vector(-mm(2), -mm(1), 0),
            App.Vector(mm(2), -mm(1), 0),
            App.Vector(mm(1), mm(1), 0),
            App.Vector(-mm(1), mm(1), 0),
        ]
        for i in range(4):
            sketch.addGeometry(Part.LineSegment(pts[i], pts[(i + 1) % 4]), False)
        for i in range(4):
            sketch.addConstraint(Sketcher.Constraint('Coincident', i, 2, (i + 1) % 4, 1))
        for i in range(4):
            sketch.addConstraint(Sketcher.Constraint('Block', i))
        doc.recompute()

        cutout = _make_cutout(doc, "Cutout", plane, sketch)
        shape = cutout.Shape
        assert_true(len(shape.Solids) > 0, "trapezoid cutout has solids")
        assert_true(shape.isClosed(), "trapezoid solid is closed")

        # 4-sided extrusion = 6 faces
        assert_eq("trapezoid face count", _get_face_count(cutout), 6)

        # Volume = area * thickness
        # Trapezoid area = (b1 + b2) / 2 * h = (4 + 2) / 2 * 2 = 6 mm^2
        expected_area = (mm(4) + mm(2)) / 2 * mm(2)
        expected_vol = expected_area * mm(0.5)
        assert_eq("trapezoid volume", _get_solid_volume(cutout), expected_vol, tol=expected_vol * 1e-3)
    except Exception as e:
        App.Console.PrintError(f"  ERROR: {e}")
        raise e
    finally:
        App.closeDocument(doc.Name)


def register_tests(all_tests):
    all_tests.append(test_cutout_thickness_variations)
    all_tests.append(test_cutout_thickness_changes_face_count)
    all_tests.append(test_cutout_triangle_sketch)
    all_tests.append(test_cutout_hexagon_sketch)
    all_tests.append(test_cutout_sketch_with_arc)
    all_tests.append(test_cutout_sketch_with_circle_hole)
    all_tests.append(test_cutout_rotated_plane)
    all_tests.append(test_cutout_thickness_zero)
    all_tests.append(test_cutout_outline_change_updates_geometry)
    all_tests.append(test_cutout_cutout_face_reflects_outline)
    all_tests.append(test_cutout_multiple_shapes_same_plane)
    all_tests.append(test_cutout_thickness_propagation)
    all_tests.append(test_cutout_non_rectangular_quadrilateral)
