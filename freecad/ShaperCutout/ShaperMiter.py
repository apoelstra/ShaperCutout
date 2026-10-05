# SPDX-License-Identifier: GPL-3.0-or-later

import math
import os
from typing import List

import FreeCAD as App
import Part

from shaper_cutout_util import _ICON_ROOT, global_normal, parent_cutout


def _plane_offset_translation(sketch, center_plane):
    """Translation from the sketch's plane onto the cutout's center plane.

    The cutout solid is extruded from the center plane (ShaperCutout::execute
    translates the sketch face by this amount before extruding), so geometry
    derived from sketch-space edge points must get the same translation when
    the sketch lives on a parallel plane offset from the center plane."""
    normal = global_normal(center_plane)
    plane_origin = center_plane.getGlobalPlacement().Base
    sketch_origin = sketch.getGlobalPlacement().Base
    dist = (plane_origin - sketch_origin).dot(normal)
    return dist * normal


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
    grp = list(cutout.Miters)
    grp.append(obj)
    cutout.Miters = grp

    return obj


def _miter_edge(shape, edge_shape, angle_deg, miter_axis, center_plane, thickness,
                sketch=None):
    """Manipulates `shape` in place to add a miter.

    sketch -- the outline sketch the edge belongs to; used to translate the edge
    onto the center plane when the sketch sits on a parallel offset plane.
    When None, the edge is assumed to already lie on the center plane."""
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
    # Edge points are in the sketch's space; the solid we are cutting was
    # extruded from the center plane. Translate the wedge onto the center plane.
    if sketch is not None:
        offset_t = _plane_offset_translation(sketch, center_plane)
        p0 = p0 + offset_t
        p1 = p1 + offset_t
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
        shape = shape.fuse(fuse_tri_face.extrude(edge_vec)).removeSplitter()
        shape = shape.cut(cut_tri_face.extrude(edge_vec))
    except Exception as e:
        App.Console.PrintWarning(f"ShaperMiter: failed to build wedge: {e}\n")

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

    def rectangles(
        self,
        miter: App.DocumentObject,
        plane_normal: App.Vector,
        thickness: App.Units.Quantity,
        center_plane: App.DocumentObject = None,
    ) -> List[Part.Wire]:
        """Given the 3D normal vector and thickness of the cutout the miter applies to, and
        a matrix which projects the cutout into XY space, return its rectangles in XY space.

        When center_plane is given, edge points taken from a sketch that lies on a
        parallel plane offset from the center plane are translated onto the center
        plane first (matching how ShaperCutout::execute builds the solid)."""
        if not miter.Edges or not miter.Angle:
            return []  # cannot compute the miter
        angle_deg = miter.Angle.Value
        if angle_deg == 0:
            return []  # miter is a nop
        if angle_deg <= -90 or angle_deg >= 90:
            return []  # cannot compute the miter
        miter_axis = miter.MiterAxis

        import math as _math

        ret_wires = []
        for (linked_obj, subnames) in miter.Edges:
            # Translate edges onto the center plane when the sketch is offset from it.
            offset_t = (_plane_offset_translation(linked_obj, center_plane)
                        if center_plane is not None else App.Vector(0, 0, 0))
            for subname in subnames:
                if not subname.startswith('Edge'):
                    continue
                try:
                    edge_shape = linked_obj.Shape.getElement(subname)
                except Exception:
                    continue
                if not isinstance(edge_shape.Curve, Part.Line):
                    continue

                p0_3d = edge_shape.Vertexes[0].Point + offset_t
                p1_3d = edge_shape.Vertexes[1].Point + offset_t
                edge_vec_3d = p1_3d - p0_3d
                face_normal_3d = edge_vec_3d.cross(plane_normal).normalize()

                far_dist = _math.tan(_math.radians(angle_deg)) * thickness
                far_vec_3d = far_dist * face_normal_3d

                if miter_axis == 'Front':
                    offset_vec_3d = App.Vector(0, 0, 0)
                elif miter_axis == 'Center':
                    offset_vec_3d = -far_vec_3d / 2
                else:  # Back
                    offset_vec_3d = -far_vec_3d

                # The 4 corners of the miter rectangle in 3D (on the center plane)
                near_a = p0_3d + offset_vec_3d
                near_b = p1_3d + offset_vec_3d
                far_a = near_a + far_vec_3d
                far_b = near_b + far_vec_3d

                ret_wires.append(Part.makePolygon([near_a, near_b, far_b, far_a, near_a]))

        return ret_wires

    def apply_miter_to_shape(
        self,
        miter: App.DocumentObject,
        shape: Part.Shape,
        center_plane: App.DocumentObject,
        thickness: App.Units.Quantity,
    ) -> Part.Shape:
        """Given a 3D cutout shape extruded from an outline sketch, apply the miters to it."""
        if not miter.Edges or miter.Angle is None:
            # Skip uninitialized/null/broken miters. (Should we warn here?)
            return Part.Shape()

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

                shape = _miter_edge(shape, edge, miter.Angle, miter.MiterAxis, center_plane,
                                    thickness, sketch=linked_obj)

        return shape

    def parent_cutout(self, obj):
        return parent_cutout(obj, 'Miters')


class ViewProviderShaperMiter:
    def __init__(self, vobj):
        vobj.Proxy = self

    def attach(self, vobj):
        pass

    def doubleClicked(self, vobj):
        from shaper_cutout_command.create_shaper_miter import open_miter_task_panel
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
        return os.path.join(_ICON_ROOT, "miter.svg")

    def dumps(self):
        return None

    def loads(self, state):
        return None
