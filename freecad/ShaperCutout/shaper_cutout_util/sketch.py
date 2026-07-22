# SPDX-License-Identifier: GPL-3.0-or-later

import FreeCAD as App


def is_sketch(obj):
    return obj.TypeId in (
        'Sketcher::SketchObject',
        'Part::Part2DObject',
        'Part::Part2DObjectPython',
    )


def global_normal(obj):
    """Determines the normal vector to the plane of the object's global placement.

    Intended for use with sketches and planes."""
    return obj.getGlobalPlacement().Rotation.multVec(App.Vector(0, 0, 1))


def objects_are_parallel(obj1, obj2):
    """Determines whether two objects are parallel (or anti-parallel) based on global placement.

    Intended for use with sketches and planes."""
    if obj1 is None or obj2 is None:
        return False
    return global_normal(obj1).cross(global_normal(obj2)).Length < 1e-6
