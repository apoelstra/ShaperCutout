# SPDX-License-Identifier: GPL-3.0-or-later

import math
import os

import FreeCAD as App
import Part


def create(cutout, edges, angle, miter_axis, name="ShaperMiter"):
    """Create a ShaperMiter inside a ShaperCutout.

    edges      -- list of (obj, subnames) tuples referencing straight edges of the outline sketch
    angle      -- miter angle in degrees
    miter_axis -- one of 'Front', 'Back', 'Center'
    """
    doc = cutout.Document
    obj = doc.addObject('Part::FeaturePython', name)
    ShaperMiter(obj)
    if App.GuiUp:
        ViewProviderShaperMiter(obj.ViewObject)

    obj.Edges = edges
    obj.Angle = angle
    obj.MiterAxis = miter_axis

    # Nest inside the ShaperCutout group
    grp = list(cutout.Group)
    grp.append(obj)
    cutout.Group = grp

    return obj


def _miter_edge(shape, edge_shape, angle_deg, miter_axis, center_plane, thickness):
    """Manipulates `shape` in place to add a miter"""
    if not isinstance(edge_shape.Curve, Part.Line):
        App.Console.PrintWarning("ShaperMiter: edge is not straight, skipping.\n")
        return shape

    if angle_deg == 0:
        return shape
    if angle_deg <= -90 or angle_deg >= 90:
        App.Console.PrintWarning(f"ShaperMiter: angle must be in (-90, 90), not {angle_deg}\n")
        return shape

    normal = center_plane.Placement.Rotation.multVec(App.Vector(0, 0, 1))
    half = thickness / 2.0

    p0 = edge_shape.Vertexes[0].Point
    p1 = edge_shape.Vertexes[1].Point
    edge_vec = p1 - p0

    # Face normal: perpendicular to both the edge and the extrusion direction
    face_normal = edge_vec.cross(normal).normalize()

    # We start by defining a rectangle that contains the miter and its inverse,
    # normal to the extrusion. We will extrude it along the edge_vec, fusing
    # the inverse then cutting the miter. (We need to fuse the inverse because
    # for some choices of miter axis we increase the size of the shape.)
    far_vec = math.tan(math.radians(angle_deg)) * thickness * face_normal
    if miter_axis == 'Front':
        offset_vec = App.Vector(0, 0, 0)
    elif miter_axis == 'Center':
        offset_vec = -far_vec / 2
    else:
        offset_vec = -far_vec

    near_a = p0 + half * normal + offset_vec
    near_b = p0 - half * normal + offset_vec
    far_a = near_a + far_vec
    far_b = near_b + far_vec

    try:
        fuse_tri = Part.makePolygon([near_a, near_b, far_a, near_a])
        cut_tri = Part.makePolygon([near_b, far_a, far_b, near_b])
        if angle_deg < 0.0:
            fuse_tri, cut_tri = cut_tri, fuse_tri

        fuse_tri_face = Part.Face(fuse_tri)
        cut_tri_face = Part.Face(cut_tri)
        shape = shape.fuse(fuse_tri_face.extrude(edge_vec))
        shape = shape.cut(cut_tri_face.extrude(edge_vec))
    except Exception as e:
        App.Console.PrintWarning(f"ShaperMiter: failed to build wedge: {e}\n")

    return shape


def miter_edges(shape, miter, center_plane, thickness):
    if not miter.Edges or miter.Angle is None:
        # Skip uninitialized/null/broken miters. (Should we warn here?)
        return

    for (linked_obj, subnames) in miter.Edges:
        for subname in subnames:
            if not subname.startswith('Edge'):
                App.Console.PrintWarning(
                    f"ShaperMiter: sub-element '{subname}' is not an edge, skipping.\n")
                continue
            try:
                edge = linked_obj.Shape.getElement(subname)
            except Exception as e:
                App.Console.PrintWarning(
                    f"ShaperMiter: could not get edge '{subname}': {e}\n")
                continue

            shape = _miter_edge(shape, edge, miter.Angle, miter.MiterAxis, center_plane, thickness)

    return shape


class ShaperMiter:
    def __init__(self, obj):
        obj.Proxy = self

        obj.addProperty('App::PropertyString', 'Type', 'Internal',
                        'Type ID used to identify instances')
        obj.addProperty('App::PropertyLinkSubList', 'Edges', 'Base',
                        'Straight edges of the outline sketch to miter.')
        obj.addProperty('App::PropertyAngle', 'Angle', 'Base',
                        'Miter angle in degrees. Positive = outward, negative = inward.')
        obj.addProperty('App::PropertyEnumeration', 'MiterAxis', 'Base',
                        'Which face plane stays fixed during the miter.')

        obj.Type = 'ShaperMiter'
        obj.MiterAxis = ['Center', 'Front', 'Back']
        obj.setEditorMode('Type', 2)

    def onChanged(self, obj, prop):
        pass

    def execute(self, obj):
        # We cannot do anything here, because we don't know the cutout's planes or thickness
        # (and we cannot know this without creating a circular DAG). Instead, the cutting
        # shape is computed and applied in ShaperCutout::execute.
        pass

    def dumps(self):
        return None

    def loads(self, state):
        return None


class ViewProviderShaperMiter:
    def __init__(self, vobj):
        vobj.Proxy = self

    def attach(self, vobj):
        pass

    def doubleClicked(self, vobj):
        from command.create_shaper_miter import open_miter_task_panel
        miter = vobj.Object
        cutout = next(
            (p for p in miter.InList if getattr(p, 'Type', None) == 'ShaperCutout'),
            None
        )
        if cutout is None:
            App.Console.PrintWarning("ShaperMiter: could not find parent ShaperCutout.\n")
            return False
        open_miter_task_panel(cutout, miter)
        return True

    def getIcon(self):
        return os.path.join(os.path.dirname(__file__), "resources/icons/miter.svg")

    def dumps(self):
        return None

    def loads(self, state):
        return None
