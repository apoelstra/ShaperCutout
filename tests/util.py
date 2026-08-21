# SPDX-License-Identifier: GPL-3.0-or-later

import FreeCAD as App
import Part
import Sketcher
import ShaperCutout


def assert_true(condition, message):
    """Simple assertion that returns True/False for test reporting."""
    if not condition:
        raise AssertionError(message)


def assert_eq(description, val, target, tol=1e-6):
    if abs(val - target) > tol:
        raise AssertionError(f"{description} {val} not in [{target - tol}..{target + tol}]")


def assert_volume(obj: App.DocumentObject, target: float, tol: float = 1e-4):
    assert_true(has_solids(obj), f"{obj.Name} has solids")
    vol = get_solid_volume(obj)
    assert_eq(f"{obj.Name} volume", vol, target, tol)


def mm(inches):
    """Convert inches to millimeters."""
    return inches * 25.4


def get_solid_volume(obj):
    """Get the total volume of all solids in an object's Shape."""
    if obj.Shape.isNull() or not obj.Shape.Solids:
        return 0.0
    return sum(s.Volume for s in obj.Shape.Solids)


def has_solids(obj):
    """Check that an object has non-null solids."""
    return hasattr(obj, 'Shape') and not obj.Shape.isNull() and len(obj.Shape.Solids) > 0


def make_plane(doc, name, origin=(0, 0, 0), rot=(0, 0, 0)):
    """Create a datum plane at the given origin with the given rotation."""
    plane = doc.addObject("Part::DatumPlane", name)
    plane.Label = name
    plane.Placement = App.Placement(
        App.Vector(*origin),
        App.Rotation(*rot),
    )
    return plane


def make_sketch(doc, plane, name, closed=True):
    """Create a sketch on the given plane. If closed, draw a rectangle.

    Returns the sketch object.
    """
    sketch = doc.addObject("Sketcher::SketchObject", name)
    sketch.Label = name
    sketch.AttachmentSupport = (plane, [''])
    sketch.MapMode = 'FlatFace'
    w = mm(4)
    h = mm(6)
    p1 = App.Vector(-w / 2, -h / 2, 0)
    p2 = App.Vector(w / 2, -h / 2, 0)
    p3 = App.Vector(w / 2, h / 2, 0)
    p4 = App.Vector(-w / 2, h / 2, 0)
    sketch.addGeometry(Part.LineSegment(p1, p2), False)
    sketch.addGeometry(Part.LineSegment(p2, p3), False)
    sketch.addGeometry(Part.LineSegment(p3, p4), False)
    if closed:
        sketch.addGeometry(Part.LineSegment(p4, p1), False)
    sketch.addConstraint(Sketcher.Constraint('Coincident', 0, 2, 1, 1))
    sketch.addConstraint(Sketcher.Constraint('Coincident', 1, 2, 2, 1))
    if closed:
        sketch.addConstraint(Sketcher.Constraint('Coincident', 2, 2, 3, 1))
        sketch.addConstraint(Sketcher.Constraint('Coincident', 3, 2, 0, 1))
    sketch.addConstraint(Sketcher.Constraint('Horizontal', 0))
    sketch.addConstraint(Sketcher.Constraint('Vertical', 1))
    sketch.addConstraint(Sketcher.Constraint('DistanceX', 0, w))
    sketch.addConstraint(Sketcher.Constraint('DistanceY', 1, h))
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
