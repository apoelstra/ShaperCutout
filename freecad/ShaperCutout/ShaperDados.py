# SPDX-License-Identifier: GPL-3.0-or-later

import math
import os
import FreeCAD as App
import Part
from PySide import QtGui

from command.create_shaper_dados import open_dados_task_panel
from shaper_cutout_util import global_normal, is_sketch, objects_are_parallel


def create_uninitialized(cutout, name):
    doc = App.ActiveDocument
    obj = doc.addObject('Part::FeaturePython', name)
    obj.Label = name
    ShaperDados(obj)
    if App.GuiUp:
        ViewProviderShaperDados(obj.ViewObject)

    # Nest inside the ShaperCutout group
    dados = list(cutout.Dados)
    dados.append(obj)
    cutout.Dados = dados

    _ensure_dado_plane(obj)

    return obj


def _parent_cutout(dados):
    for o in dados.InList:
        if (getattr(o, 'Type', None) == 'ShaperCutout' and dados in o.Dados):
            return o
    return None


def _ensure_dado_plane(collection):
    """Recreate dado plane if missing or link broken."""
    plane = collection.DadoPlane
    if plane is not None and plane in collection.Document.Objects:
        return plane
    plane = collection.Document.addObject(
        'Part::DatumPlane', collection.Name + '_Plane')
    collection.DadoPlane = plane
    collection.setEditorMode('DadoPlane', 2)
    return plane


def _wire_to_pipes(wire, normal, tol, width):
    # For open wires, we convert them into dados which use the edges as center
    # lines. It's an interesting question how we ought to consider edges that meet
    # at their endpoints but aren't tangent.
    #
    # There is the makeOffset2D function which rounds the corners, or you can also
    # set it to "tangent" which just extends the outer lines until they intersect,
    # but this causes a super far-out point on acute angles (and fails entirely
    # if the lines are parallel. There is the makePipe function which maintains
    # the angle that it's sweeping, so the second line's width is reduced, though
    # I am unsure if this is deliberate.
    #
    # But I think none of these ideas make physical sense. The point of a "dado" is
    # to be an inset that the edge of some material fits into. No physical material
    # can change direction instantaneously. If the user intended to represent a
    # bend, she could've drawn an arc connecting the two segments, with the meeting
    # endpoints tangent to each other. My guess is that what the user is actually
    # intending is that one sheet is butted up against another sheet. But drawing
    # this as a corner is (probably) a mistake and we shouldn't attempt to cut more
    # material to compensate. We should just treat the corner as representing the
    # start of a new dado, i.e. draw a pocket with a "corner missing".
    #
    # As long as edges are tangent to each other, we can use makePipe which will
    # do the right thing (and will curve along arcs, splines, etc).
    edges = []
    init_edge = wire.Edges[0]
    last_tangent = init_edge.tangentAt(init_edge.FirstParameter)
    last_vertex = init_edge.lastVertex()
    if tol > 0.0:
        edges.append(Part.makeLine(
            init_edge.firstVertex().Point - tol * last_tangent,
            init_edge.firstVertex().Point,
        ))

    wire_norm = normal.cross(last_tangent)
    sweep_wire = Part.makeLine(
        init_edge.firstVertex().Point - (width + tol) * wire_norm,
        init_edge.firstVertex().Point + (width + tol) * wire_norm,
    )

    pipes = []
    for edge in wire.Edges:
        tangent = edge.tangentAt(edge.FirstParameter)
        if (tangent - last_tangent).Length < 1e-4:
            edges.append(edge)
        else:
            if tol > 0.0:
                edges.append(Part.makeLine(
                    last_vertex.Point,
                    last_vertex.Point + tol * last_tangent,
                ))
            pipes.append(Part.Wire(edges).makePipe(sweep_wire).removeSplitter())

            edges = [edge]
            if tol > 0.0:
                edges.append(Part.makeLine(
                    edge.firstVertex().Point - tol * tangent,
                    edge.firstVertex().Point,
                ))
            wire_norm = normal.cross(tangent)
            sweep_wire = Part.makeLine(
                edge.firstVertex().Point - (width + tol) * wire_norm,
                edge.firstVertex().Point + (width + tol) * wire_norm,
            )

        last_tangent = edge.tangentAt(edge.LastParameter)
        last_vertex = edge.lastVertex()
    if tol > 0.0:
        edges.append(Part.makeLine(
            last_vertex.Point,
            last_vertex.Point + tol * last_tangent,
        ))
    pipes.append(Part.Wire(edges).makePipe(sweep_wire).removeSplitter())

    return pipes


def autodrill_holes(wire, min_distance, end_distance, max_holes):
    """Return list of (center_3d, radius) tuples for autodrill holes."""
    if max_holes == 0:
        return []

    cylinders = []
    for edge in wire.Edges:
        p0 = edge.FirstParameter
        p1 = edge.LastParameter
        # Assume that parameter -> position on curve is linear. This is definitely
        # true for edges and arcs, at least.
        scale = (p1 - p0) / edge.Length

        # If we can't even fit one hole, skip.
        if edge.Length < 2 * end_distance:
            continue

        len_minus_ends = edge.Length - 2 * end_distance
        if min_distance == 0:
            n_holes = max_holes
        else:
            max_holes_that_fit = math.floor(len_minus_ends / min_distance) + 1
            n_holes = min(max_holes, max_holes_that_fit)

        # Determine hole center points along the segment
        if n_holes == 1:
            # If we're drilling one hole, it goes right in the center.
            cylinders.append(edge.valueAt((p0 + p1) * 0.5))
        else:
            # At this point we know we are drilling at least two holes. We put one each at the ends
            # (end_distance from the endpoints) and then equally space the remainder.
            cylinders.append(edge.valueAt(p0 + end_distance * scale))
            cylinders.append(edge.valueAt(p1 - end_distance * scale))

            dist = len_minus_ends / (n_holes - 1)
            for i in range(n_holes):
                cylinders.append(edge.valueAt(p0 + (i * dist + end_distance) * scale))

    return cylinders


class ShaperDados:
    def __init__(self, obj):
        obj.Proxy = self

        obj.addProperty('App::PropertyString', 'Version', 'Internal',
                        'ShaperCutout version used to create this object')
        obj.addProperty('App::PropertyString', 'Type', 'Internal',
                        'Type ID used to identify instances')
        obj.addProperty('App::PropertyLink', 'Face', 'Base',
                        'Front or back face this dado cuts into.')
        obj.addProperty('App::PropertyBool', 'Invert', 'Base',
                        'Direction to cut dado pockets into the face')
        obj.addProperty('App::PropertyLinkList', 'Sketches', 'Base',
                        'The sketches associated with this dado set.')

        self.addV2Properties(obj)

        obj.addProperty('App::PropertyLink', 'DadoPlane', 'Internal',
                        'Datum plane at the dado depth.')
        obj.addProperty('Part::PropertyPartShape', 'PocketShape', 'Internal',
                        'Computed pocket solid for subtraction.')

        self.addV3Properties(obj)

        obj.Version = "3"
        obj.Type = "ShaperDados"

        obj.setEditorMode('Version', 2)
        obj.setEditorMode('Type', 2)
        obj.setEditorMode('DadoPlane', 2)
        obj.setEditorMode('PocketShape', 2)
        obj.setPropertyStatus('Face', 2)

    def onChanged(self, obj, prop):
        if prop == 'MaxHolesPerLine':
            if getattr(obj, 'MaxHolesPerLine', 0) < 0:
                obj.MaxHolesPerLine = 0

    def execute(self, obj):
        if not obj.Face or not obj.Depth:
            return

        parent = _parent_cutout(obj)
        if parent is not None and parent.Thickness:
            if obj.Depth.Value > parent.Thickness.Value:
                App.Console.PrintWarning(
                    f"ShaperDados '{obj.Label}': Depth ({obj.Depth}) "
                    f"exceeds sheet Thickness ({parent.Thickness})\n")

        normal = global_normal(obj.Face)

        depth = -obj.Depth.Value if obj.Invert else obj.Depth.Value
        extrude_vec = App.Vector(
            normal.x * depth,
            normal.y * depth,
            normal.z * depth,
        )

        dado_plane = _ensure_dado_plane(obj)
        dado_plane.AttachmentSupport = [(obj.Face)]
        dado_plane.MapMode = 'FlatFace'
        dado_plane.AttachmentOffset = App.Placement(
            App.Vector(0, 0, depth),
            App.Rotation(0, 0, 0),
        )
        dado_plane.purgeTouched()

        solids = []
        for member in (obj.Sketches or []):
            if member is None:
                continue
            try:
                source = member.LinkedObject if member.TypeId == 'App::Link' else member
                wires = source.Shape.Wires
            except Exception:
                App.Console.PrintWarning(
                    f"ShaperDados '{obj.Label}': could not get wires from "
                    f"'{member.Label}'\n")
                continue

            member_normal = global_normal(member)
            if member_normal.cross(normal).Length >= 1e-6:
                App.Console.PrintWarning(
                    f"ShaperDados '{obj.Label}':"
                    f"'{member.Label}' is not parallel to face; skipping\n")
                continue

            face_origin = obj.Face.Placement.Base
            for wire in wires:
                dist = (face_origin - wire.CenterOfGravity).dot(normal)
                translated_wire = wire.copy()
                translated_wire.translate(App.Vector(
                    normal.x * dist,
                    normal.y * dist,
                    normal.z * dist,
                ))
                if translated_wire.isClosed():
                    # Treat closed wires as arbitrary shapes to cut into the sheet.
                    face = Part.Face(translated_wire)
                    solids.append(face.extrude(extrude_vec))
                elif obj.Width.Value == 0.0:
                    App.Console.PrintWarning(
                        f"ShaperDados '{obj.Label}': open wires in "
                        f"'{member.Label}' but zero Width set for dados; skipping\n")
                elif translated_wire.Edges == []:
                    pass
                else:
                    tol = obj.Tolerance.Value
                    width = obj.Width.Value / 2.0

                    for pipe in _wire_to_pipes(translated_wire, normal, tol, width):
                        # Ideally we would sew any overlapping shapes together. This seems tricky
                        # to do. For the 3D model it doesn't really matter I suppose.
                        for face in pipe.Faces:
                            solids.append(face.extrude(extrude_vec))

                    # Open wires can have autodrill holes
                    hole_radius = obj.HoleDiameter.Value / 2.0
                    parent = _parent_cutout(obj)
                    thickness = parent.Thickness.Value if parent and parent.Thickness else None

                    if obj.HoleDiameter > obj.Width:
                        App.Console.PrintWarning(
                            f"ShaperDados '{obj.Label}': autodrill hole diameter set to "
                            f"{obj.HoleDiameter} > dado width {obj.Width}; not drilling\n")
                    elif obj.MaxHolesPerLine > 0 and hole_radius == 0.0:
                        App.Console.PrintWarning(
                            f"ShaperDados '{obj.Label}': autodril has positive MaxHolesPerLine"
                            f"but zero hole diameter; not drilling\n")
                    elif obj.HoleDiameter.Value < hole_radius:
                        App.Console.PrintWarning(
                            f"ShaperDados '{obj.Label}': autodrill has end distance "
                            f"{obj.HoleDiameter.Value} < hole radius {hole_radius}; not drilling\n")
                    elif obj.MaxHolesPerLine == 0:
                        # fine. this means "disable autodriller"
                        pass
                    else:
                        cylinders = autodrill_holes(translated_wire, obj.MinHoleDistance.Value,
                                                    obj.EndDistance.Value, obj.MaxHolesPerLine)
                        for center in cylinders:
                            cyl_norm = -normal if obj.Invert else normal
                            cyl = Part.makeCylinder(hole_radius, thickness, center, cyl_norm)
                            solids.append(cyl)

        if not solids:
            obj.PocketShape = Part.Shape()
            return

        shape = solids[0]
        for s in solids[1:]:
            shape = shape.fuse(s)
        obj.PocketShape = shape

    def dumps(self):
        return None

    def loads(self, state):
        return None

    def addV2Properties(self, obj):
        obj.addProperty('App::PropertyLength', 'Depth', 'Dado',
                        'Depth of pockets cut by this dado set (no tolerance added).')
        obj.addProperty('App::PropertyLength', 'Width', 'Dado',
                        'Width of rectangular dados cut based on unclosed wires.')
        obj.addProperty('App::PropertyLength', 'Tolerance', 'Dado',
                        'Tolerance to add to each side, and the ends, of rectangular ' +
                        'cuts generated based on unclosed wires.')

    def addV3Properties(self, obj):
        obj.addProperty('App::PropertyInteger', 'MaxHolesPerLine', 'Autodrill',
                        'Max drill holes per line pair. 0 = disable autodriller.')
        obj.addProperty('App::PropertyLength', 'HoleDiameter', 'Autodrill',
                        'Diameter of autodrill holes.')
        obj.addProperty('App::PropertyLength', 'MinHoleDistance', 'Autodrill',
                        'Minimum allowable distance between holes.')
        obj.addProperty('App::PropertyLength', 'EndDistance', 'Autodrill',
                        'Distance from ends of dados to put drill holes.')

    def onDocumentRestored(self, obj):
        version = getattr(obj, 'Version', "1")
        if version == "1":
            # Add version
            obj.addProperty('App::PropertyString', 'Version', 'Internal',
                            'ShaperCutout version used to create this object')
            obj.Version = "2"
            obj.setEditorMode('Version', 2)
            # Move Depth property to Dado group (if we do this a second time, let's pull
            # this out into util.py)
            old_depth = obj.Depth
            old_depth_expr = None
            for prop, expr in obj.ExpressionEngine:
                if prop == 'Depth':
                    old_depth_expr = expr

            obj.removeProperty('Depth')

            # Add new properties
            self.addV2Properties(obj)
            obj.Tolerance = 0.0
            obj.Width = 0.0

            # Re-set Depth to previous value
            obj.Depth = old_depth
            if old_depth_expr is not None:
                obj.setExpression('Depth', old_depth_expr)

        if obj.Version == "2":
            self.addV3Properties(obj)

            obj.MaxHolesPerLine = 0
            obj.HoleDiameter = "0.13 in"  # will bite #8 screw, Shaper willing to helix with 1/8 bit
            obj.MinHoleDistance = "3 in"
            obj.EndDistance = "0.5 in"
            obj.Version = "3"

        # Old versions stored the plane in the group, but this is wrong/redundant. We only want
        # sketches -- and also let's not use Group, because we want to be able to share sketches
        # between dado sets. We already have the Sketches list.
        group = []
        for gchild in getattr(obj, 'Group', []):
            if is_sketch(gchild):
                group.append(gchild)


class ViewProviderShaperDados:
    def __init__(self, vobj):
        vobj.Proxy = self

    def attach(self, vobj):
        self.ViewObject = vobj
        self.Object = vobj.Object
        pass

    def getIcon(self):
        return os.path.join(os.path.dirname(__file__), "resources/icons/dados.svg")

    # Which "children" show up in the Tree View. Curiously there is no requirement that
    # the parent relationship be unique, so many cutouts can claim the same sketches
    # or planes.
    def claimChildren(self):
        return [self.Object.DadoPlane] + self.Object.Sketches

    def canDragObjects(self):
        return True

    def canDropObjects(self):
        return True

    def doubleClicked(self, vobj):
        parent = _parent_cutout(vobj.Object)
        if parent is not None:
            open_dados_task_panel(parent, vobj.Object)
        return True

    def setupContextMenu(self, vobj, menu):
        edit_action = QtGui.QAction("Edit Dados", menu)
        edit_action.triggered.connect(lambda: open_dados_task_panel(
            _parent_cutout(vobj.Object), vobj.Object))
        menu.addAction(edit_action)

    def dumps(self):
        return None

    def loads(self, state):
        return None

    def canDragObject(self, child):
        return is_sketch(child)

    def dragObject(self, vobj, child):
        # Similar to cutouts, dados act kinda like groups except that sketches can live in
        # multiple instances at once, and dragging out of the group has no effect.
        pass

    def canDropObject(self, child):
        # Don't print warnings here, this event triggers many times while the user is hovering.
        # Just filter to "sketches only" which is easy for the user to understand, and do further
        # filters in `dropChild` where we can print warnings to explain why we reject things.
        return is_sketch(child)

    def dropObject(self, vobj, child):
        if not is_sketch(child):
            return

        if not objects_are_parallel(self.Object.DadoPlane, child):
            App.Console.PrintWarning(
                f"Sketch '{child.Label}': outline sketch is not parallel to Dados; rejecting.\n")

        grp = list(self.Object.Sketches)
        grp.append(child)
        self.Object.Sketches = grp
