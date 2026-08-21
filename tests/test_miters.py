# SPDX-License-Identifier: GPL-3.0-or-later

from typing import List

import FreeCAD as App
import Part
import Sketcher
import ShaperMiter

from util import assert_true, assert_volume
from util import make_cutout, make_plane, mm


def _make_cutout_with_sketch(doc, name, outline_points=None):
    """Create a cutout with a sketch outline. Returns (cutout, sketch)."""
    plane = make_plane(doc, name + "_plane", origin=(0, 0, 0), rot=(0, 0, 0))
    sketch = doc.addObject("Sketcher::SketchObject", name + "_sketch")
    sketch.Label = name + "_sketch"
    sketch.AttachmentSupport = (plane, [''])
    sketch.MapMode = 'FlatFace'
    if outline_points:
        for i in range(len(outline_points)):
            sketch.addGeometry(
                Part.LineSegment(outline_points[i], outline_points[(i + 1) % len(outline_points)]),
                False,
            )
        n = len(outline_points)
        for i in range(n):
            sketch.addConstraint(Sketcher.Constraint('Coincident', i, 2, (i + 1) % n, 1))
    else:
        w, h = mm(4), mm(6)
        pts = [
            App.Vector(-w / 2, -h / 2, 0),
            App.Vector(w / 2, -h / 2, 0),
            App.Vector(w / 2, h / 2, 0),
            App.Vector(-w / 2, h / 2, 0),
        ]
        for i in range(4):
            sketch.addGeometry(Part.LineSegment(pts[i], pts[(i + 1) % 4]), False)
        for i in range(4):
            sketch.addConstraint(Sketcher.Constraint('Coincident', i, 2, (i + 1) % 4, 1))
        sketch.addConstraint(Sketcher.Constraint('Horizontal', 0))
        sketch.addConstraint(Sketcher.Constraint('Vertical', 1))
        sketch.addConstraint(Sketcher.Constraint('DistanceX', 0, w))
        sketch.addConstraint(Sketcher.Constraint('DistanceY', 1, h))

    cutout = make_cutout(doc, plane, name)
    cutout.OutlineSketch = sketch
    return cutout, sketch


def _make_cutout_with_rect_outline(doc, name):
    """Create a cutout with a simple rectangular outline sketch."""
    return _make_cutout_with_sketch(doc, name, None)


def _get_straight_edge_names(sketch):
    """Get the list of EdgeN subnames for straight edges in a sketch."""
    names = []
    for i, edge in enumerate(sketch.Shape.Edges):
        if isinstance(edge.Curve, Part.Line):
            names.append(f'Edge{i + 1}')
    return names


def _test_miter_single_angle(
    angle_deg: float,
    miter_axis: float,
    target_volume: float,
    edge_names: List[str] = None,
):
    """Run a single miter test. Returns (success, volume)."""
    doc = App.newDocument(f"test_miter_{angle_deg}_{miter_axis}")
    try:
        cutout, sketch = _make_cutout_with_rect_outline(doc, "Cutout")

        # Solve the sketch so its Shape is populated before we query edges
        doc.recompute()

        if edge_names is None:
            edge_names = _get_straight_edge_names(sketch)

        if not edge_names:
            raise ValueError("no straight edges found")

        edges = [(sketch, edge_names)]
        ShaperMiter.create(cutout, edges, angle_deg, miter_axis, "Miter")

        doc.recompute()
        assert_volume(cutout, target_volume)
    except Exception as e:
        App.Console.PrintError(f"  ERROR: {e}")
        raise e
    finally:
        App.closeDocument(doc.Name)


def test_miter_one_edge():
    """Miter a single edge."""
    # _test_miter_single_angle with edge_names=None will get all edges;
    # we pass a single edge to test one-edge mitering.
    # We need to create the doc first to get the edge name.
    doc = App.newDocument("test_miter_one_edge_tmp")
    try:
        cutout, sketch = _make_cutout_with_rect_outline(doc, "Cutout")
        doc.recompute()
        edge_names = _get_straight_edge_names(sketch)
        first_edge = [edge_names[0]] if edge_names else []
    finally:
        App.closeDocument(doc.Name)
    if not first_edge:
        raise ValueError("no straight edges found")
    _test_miter_single_angle(15, "Center", 196644.768, edge_names=first_edge)


def test_miter_multiple_edges():
    """Miter two edges (adjacent sides of the rectangle)."""
    doc = App.newDocument("test_miter_multiple_edges_tmp")
    try:
        cutout, sketch = _make_cutout_with_rect_outline(doc, "Cutout")
        doc.recompute()
        edge_names = _get_straight_edge_names(sketch)
        two_edges = edge_names[:2] if len(edge_names) >= 2 else edge_names
    finally:
        App.closeDocument(doc.Name)
    if not two_edges:
        raise ValueError("not enough straight edges found")
    _test_miter_single_angle(15, "Center", 196653.95970516, edge_names=two_edges)


def test_miter_all_edges():
    """Miter all four edges of the rectangle."""
    doc = App.newDocument("test_miter_all_edges_tmp")
    try:
        cutout, sketch = _make_cutout_with_rect_outline(doc, "Cutout")
        doc.recompute()
        edge_names = _get_straight_edge_names(sketch)
    finally:
        App.closeDocument(doc.Name)
    if not edge_names:
        raise ValueError("no straight edges found")
    _test_miter_single_angle(15, "Center", 196681.53482064, edge_names=edge_names)


def test_miter_curved_edge():
    """Mitering a curved edge should have no effect (warning printed, no crash).

    We test this two ways:
    1. Direct unit test of _miter_edge with a curved edge shape
    2. Integration test: create a sketch with a curved edge, add a miter on it,
       and verify the cutout shape doesn't change significantly.
    """
    doc = App.newDocument("test_miter_curved")
    try:
        plane = make_plane(doc, "Plane", origin=(0, 0, 0), rot=(0, 0, 0))
        sketch = doc.addObject("Sketcher::SketchObject", "Curved_sketch")
        sketch.AttachmentSupport = (plane, [''])
        sketch.MapMode = 'FlatFace'

        # Draw a rectangle with one curved edge (arc)
        w, h = mm(4), mm(6)
        p1 = App.Vector(-w/2, -h/2, 0)
        p2 = App.Vector(w/2, -h/2, 0)
        p3 = App.Vector(w/2, h/2, 0)
        p4 = App.Vector(-w/2, h/2, 0)
        sketch.addGeometry(Part.LineSegment(p1, p2), False)
        sketch.addGeometry(Part.LineSegment(p2, p3), False)
        sketch.addGeometry(Part.LineSegment(p3, p4), False)
        # Arc from p4 to p1 (concave arc) - midpoint offset from the edge line
        arc = Part.Arc(p4, App.Vector(-w/4, 0, 0), p1)
        sketch.addGeometry(arc, False)

        # Close the sketch
        n_geoms = 4  # 3 lines + 1 arc
        for i in range(n_geoms):
            # Just use "block" constraints to force everything into place rather than trying to
            # do this cleverly and leaving the sketch unconstrained, which causes nondeterministic
            # behavior throughout the test.
            sketch.addConstraint(Sketcher.Constraint('Block', i))

        cutout = make_cutout(doc, plane, "Cutout")
        cutout.OutlineSketch = sketch

        # Get volume before mitering
        doc.recompute()
        assert_volume(cutout, 163153.478826669)

        # An empty miter should work and have no effect.
        ShaperMiter.create(cutout, [], 15, "Center", "Miter_empty")
        doc.recompute()
        assert_volume(cutout, 163153.478826669)

        # Find the arc edge (non-line edge)
        arc_edges = []
        for i, edge in enumerate(sketch.Shape.Edges):
            if not isinstance(edge.Curve, Part.Line):
                arc_edges.append(f'Edge{i + 1}')

        if not arc_edges:
            App.Console.PrintWarning("no curved edges in sketch, testing _miter_edge directly")
            # Direct test of _miter_edge with a curved edge
            from ShaperMiter import _miter_edge
            curved_edge = Part.Arc(
                App.Vector(0, 0, 0),
                App.Vector(1, 1, 0),
                App.Vector(2, 0, 0)
            ).toShape()
            test_shape = Part.makeBox(10, 10, 10)
            result = _miter_edge(test_shape, curved_edge, 15, "Center", plane, mm(0.5))
            assert_true(result is test_shape or result.Volume == test_shape.Volume,
                        "_miter_edge returns unchanged shape for curved edge")
            return

        # Now add a miter on the curved edge
        ShaperMiter.create(cutout, [(sketch, arc_edges)], 15, "Center", "Miter_curved")
        doc.recompute()

        # The miter on a curved edge should be skipped, so volumes should be equal.
        assert_volume(cutout, 163153.478826669)
    except Exception as e:
        App.Console.PrintError(f"  ERROR: {e}")
        raise e
    finally:
        App.closeDocument(doc.Name)


def test_miter_angles():
    """Test various miter angles: -89.9, -45, -30, -1, 0, 15, 89.9."""
    angles = [
        (11639408.6124811, -89.9),
        (197156.86375, -45),
        (196815.466583333, -30),
        (196644.924024970, -1),
        (196644.768, 0),
        (196681.534820640, 15),
        (196815.466583333, 30),
        (197156.86375, 45),
        (11639408.6124806, 89.9),
    ]
    for target_volume, angle in angles:
        _test_miter_single_angle(angle, "Center", target_volume)


def test_miter_all_alignment_values():
    """Test all three miter axis values: Front, Back, Center."""
    axes = [
        (207622.01941279, 'Front'),
        (185961.65115232, 'Back'),
        (196681.53482064, 'Center'),
    ]
    for target_volume, axis in axes:
        _test_miter_single_angle(15, axis, target_volume)


def test_miter_angle_0_is_noop():
    """Angle 0 should not change the shape."""
    doc = App.newDocument("test_miter_zero_noop")
    try:
        cutout, sketch = _make_cutout_with_rect_outline(doc, "Cutout")
        doc.recompute()
        # See also the 0 angle in `test_miter_angles`
        assert_volume(cutout, 196644.768)

        edge_names = _get_straight_edge_names(sketch)
        ShaperMiter.create(cutout, [(sketch, [edge_names[0]])], 0, "Center", "Miter_zero")
        doc.recompute()
        assert_volume(cutout, 196644.768)
    except Exception as e:
        App.Console.PrintError(f"  ERROR: {e}")
        raise e
    finally:
        App.closeDocument(doc.Name)


def register_tests(all_tests):
    all_tests.append(test_miter_one_edge)
    all_tests.append(test_miter_multiple_edges)
    all_tests.append(test_miter_all_edges)
    all_tests.append(test_miter_curved_edge)
    all_tests.append(test_miter_angles)
    all_tests.append(test_miter_all_alignment_values)
    all_tests.append(test_miter_angle_0_is_noop)
