# SPDX-License-Identifier: GPL-3.0-or-later

import os
from typing import Optional
import FreeCAD as App
import Part
from PySide import QtGui

from shaper_cutout_util import _ICON_ROOT, global_normal


class SlotData:
    """Computed data about a slot as it pertains to one of its cutouts.

    Constructed with ShaperSlot.slot_data_for."""
    def __init__(
        self,
        slot_index: int,
        edge_p0: Part.Point,
        edge_p1: Part.Point,
        slot_direction: App.Vector,
        width_tolerance: App.Units.Quantity,
        length_tolerance: App.Units.Quantity,
        sketch_bound_box: App.BoundBox,
        front_dado_depth: App.Units.Quantity,
        back_dado_depth: App.Units.Quantity,
        other_front_dado_depth: App.Units.Quantity,
        other_back_dado_depth: App.Units.Quantity,
    ):
        self.slot_index = slot_index
        self.edge_p0 = edge_p0
        self.edge_p1 = edge_p1
        self.slot_direction = slot_direction
        self.width_tolerance = width_tolerance.Value
        self.length_tolerance = length_tolerance.Value
        self.sketch_bound_box = sketch_bound_box
        self.front_dado_depth = front_dado_depth.Value
        self.back_dado_depth = back_dado_depth.Value
        self.other_front_dado_depth = other_front_dado_depth.Value
        self.other_back_dado_depth = other_back_dado_depth.Value

    def slot_wire(self) -> Part.Wire:
        normal = (self.edge_p1 - self.edge_p0).normalize()

        surf0 = self.edge_p0 - (self.width_tolerance - self.other_front_dado_depth) * normal
        surf1 = self.edge_p1 + (self.width_tolerance - self.other_back_dado_depth) * normal

        surface_line = Part.makeLine(surf0, surf1)
        full_bound_box = self.sketch_bound_box.united(surface_line.BoundBox)
        # side_length inspired by `ProfileBased::getThroughAllLength` in the PartDesign source
        side_length = full_bound_box.DiagonalLength * 1.01
        top0 = surf0 + side_length * self.slot_direction
        top1 = surf1 + side_length * self.slot_direction

        return Part.Wire(Part.makePolygon([surf0, surf1, top1, top0, surf0]))

    def dado_faces(self, cutout_face: Part.Shape) -> [Part.Face]:
        # Differs from slot_wire in that we don't reduce by dado depth, we reverse the
        # slot direction, and we intersect with the cutout face rather than just swagging
        # a bound and making a giant rectangle.
        #
        # Because this is kinda expensive, return an empty list and skip the computation
        # if the dado depth is 0.
        if self.front_dado_depth == 0.0 and self.back_dado_depth == 0.0:
            return []

        w_adj = self.width_tolerance * (self.edge_p1 - self.edge_p0).normalize()
        surf0 = self.edge_p0 - w_adj
        surf1 = self.edge_p1 + w_adj

        surface_line = Part.makeLine(surf0, surf1)
        full_bound_box = self.sketch_bound_box.united(surface_line.BoundBox)
        # side_length inspired by `ProfileBased::getThroughAllLength` in the PartDesign source
        side_length = full_bound_box.DiagonalLength * 1.01
        top0 = surf0 - side_length * self.slot_direction
        top1 = surf1 - side_length * self.slot_direction
        wire = Part.Wire(Part.makePolygon([surf0, surf1, top1, top0, surf0]))
        face = Part.Face(wire)

        # Because the cutout face might be multiple faces, the intersection might be
        # multiple faces. We don't do any cleanup here.
        return cutout_face.common(face).Faces


def create_uninitialized(cutout1, cutout2, interface_plane, name="ShaperSlot"):
    doc = App.ActiveDocument
    obj = doc.addObject('Part::FeaturePython', name)
    ShaperSlot(obj)
    if App.GuiUp:
        ViewProviderShaperSlot(obj.ViewObject)

    # Set properties
    obj.Cutout1Front = cutout1.FrontFace
    obj.Cutout2Front = cutout2.FrontFace
    obj.Cutout1Back = cutout1.BackFace
    obj.Cutout2Back = cutout2.BackFace
    obj.InterfacePlane = interface_plane

    # Add to both cutouts' slot lists
    slots1 = list(cutout1.Slots)
    slots1.append(obj)
    cutout1.Slots = slots1

    slots2 = list(cutout2.Slots)
    slots2.append(obj)
    cutout2.Slots = slots2

    return obj


class ShaperSlot:
    def __init__(self, obj):
        obj.Proxy = self

        obj.addProperty('App::PropertyDistance', 'LengthTolerance', 'Slot',
                        'Amount to offset the slot surface; positive numbers create a longer slot.')
        obj.addProperty('App::PropertyDistance', 'WidthTolerance', 'Slot',
                        'Amount to offset each side of the slot to widen it.')
        obj.addProperty('App::PropertyBool', 'Invert', 'Slot',
                        'Invert the slot direction')
        obj.addProperty('App::PropertyLink', 'InterfacePlane', 'Slot',
                        'Plane defining the slot interface')

        obj.addProperty('App::PropertyString', 'Type', 'Internal',
                        'Type ID used to identify instances')

        obj.addProperty('App::PropertyLink', 'Cutout1_Front', 'Cutout1',
                        'Front face plane of first ShaperCutout')
        obj.addProperty('App::PropertyLink', 'Cutout1_Back', 'Cutout1',
                        'Back face plane of first ShaperCutout')
        obj.addProperty('App::PropertyLink', 'Cutout2_Front', 'Cutout2',
                        'Front face plane of second ShaperCutout')
        obj.addProperty('App::PropertyLink', 'Cutout2_Back', 'Cutout2',
                        'Back face plane of second ShaperCutout')
        self.addDadoProperties(obj)

        obj.Type = 'ShaperSlot'
        obj.Invert = False

        obj.setEditorMode('Type', 2)

    def execute(self, obj):
        pass

    def dumps(self):
        return None

    def loads(self, state):
        return None

    def addDadoProperties(self, obj):
        if not hasattr(obj, 'Cutout1_FrontDadoDepth'):
            obj.addProperty('App::PropertyLength', 'Cutout1_FrontDadoDepth', 'Cutout1',
                            "Depth of the dado cut into cutout 1's front face (0 to disable)")
        if not hasattr(obj, 'Cutout1_BackDadoDepth'):
            obj.addProperty('App::PropertyLength', 'Cutout1_BackDadoDepth', 'Cutout1',
                            "Depth of the dado cut into cutout 1's back face (0 to disable)")
        if not hasattr(obj, 'Cutout2_FrontDadoDepth'):
            obj.addProperty('App::PropertyLength', 'Cutout2_FrontDadoDepth', 'Cutout2',
                            "Depth of the dado cut into cutout 2's front face (0 to disable)")
        if not hasattr(obj, 'Cutout2_BackDadoDepth'):
            obj.addProperty('App::PropertyLength', 'Cutout2_BackDadoDepth', 'Cutout2',
                            "Depth of the dado cut into cutout 2's back face (0 to disable)")

    def onDocumentRestored(self, obj):
        self.addDadoProperties(obj)

        if hasattr(obj, 'Cutout1Front') and not hasattr(obj, 'Cutout1_Front'):
            obj.addProperty('App::PropertyLink', 'Cutout1_Front', 'Cutout1',
                            'Front face plane of first ShaperCutout')
            obj.Cutout1_Front = obj.Cutout1Front
            obj.removeProperty("Cutout1Front")
        if hasattr(obj, 'Cutout1Back') and not hasattr(obj, 'Cutout1_Back'):
            obj.addProperty('App::PropertyLink', 'Cutout1_Back', 'Cutout1',
                            'Back face plane of first ShaperCutout')
            obj.Cutout1_Back = obj.Cutout1Back
            obj.removeProperty("Cutout1Back")
        if hasattr(obj, 'Cutout2Front') and not hasattr(obj, 'Cutout2_Front'):
            obj.addProperty('App::PropertyLink', 'Cutout2_Front', 'Cutout2',
                            'Front face plane of second ShaperCutout')
            obj.Cutout2_Front = obj.Cutout2Front
            obj.removeProperty("Cutout2Front")
        if hasattr(obj, 'Cutout2Back') and not hasattr(obj, 'Cutout2_Back'):
            obj.addProperty('App::PropertyLink', 'Cutout2_Back', 'Cutout2',
                            'Back face plane of second ShaperCutout')
            obj.Cutout2_Back = obj.Cutout2Back
            obj.removeProperty("Cutout2Back")

    def find_cutout1(self, obj):
        for parent in obj.Cutout1_Back.InList:
            if getattr(parent, 'Type', '') != 'ShaperCutout':
                continue
            if obj in getattr(parent, 'Slots', []):
                return parent

    def find_cutout2(self, obj):
        for parent in obj.Cutout2_Back.InList:
            if getattr(parent, 'Type', '') != 'ShaperCutout':
                continue
            if obj in getattr(parent, 'Slots', []):
                return parent

    def slot_data_for(
        self,
        slot: App.DocumentObject,
        cutout: App.DocumentObject,
        warn: bool = True,
    ) -> Optional[SlotData]:
        if slot.Cutout1_Front == cutout.FrontFace and slot.Cutout1_Back == cutout.BackFace:
            slot_index = 1
            # The front faces of the *other* cutout, which represent the walls of our
            # slot, and the dado depth that we cut into *this* cutout.
            front_face = slot.Cutout2_Front
            back_face = slot.Cutout2_Back
            front_dado_depth = slot.Cutout1_FrontDadoDepth
            back_dado_depth = slot.Cutout1_BackDadoDepth
            other_front_dado_depth = slot.Cutout2_FrontDadoDepth
            other_back_dado_depth = slot.Cutout2_BackDadoDepth
        elif slot.Cutout2_Front == cutout.FrontFace and slot.Cutout2_Back == cutout.BackFace:
            slot_index = 2
            front_face = slot.Cutout1_Front
            back_face = slot.Cutout1_Back
            front_dado_depth = slot.Cutout2_FrontDadoDepth
            back_dado_depth = slot.Cutout2_BackDadoDepth
            other_front_dado_depth = slot.Cutout1_FrontDadoDepth
            other_back_dado_depth = slot.Cutout1_BackDadoDepth
        else:
            return None

        if not slot.InterfacePlane:
            return None

        our_normal = global_normal(cutout.CenterPlane)
        other_normal = global_normal(front_face)  # assume front and back have same normal
        slot_dir = (-1.0 if slot.Invert else 1.0) * our_normal.cross(other_normal)
        if 1.0 - slot_dir.Length > 1e-4:
            if warn:
                App.Console.PrintWarning(
                    f"Cutout '{cutout.Label}' slot '{slot.Label}': the two cutouts are "
                    "not orthogonal, so the slot would require miter cuts for the sides. "
                    "This is not implemented and hard to manufacture. Failing slot.\n")
            return None

        # The slot rectangle is defined by:
        # - The sides: two boundary lines from other cutout's front/back faces
        # - The surface: a boundary line orthogonal to these, centered on interface plane
        # - Another boundary line outside the extent of the sketch's bounding box.

        # Get the center point where the three planes meet, by taking the two endpoints
        # and averaging them. This center point is the only one that we fix to: we need
        # both slots to be rectangles (all angles 90) and both slots' sides to lie along
        # to the opposing cutouts' face planes. Which leaves us only one degree of freedom,
        # which we fix by having the two slots touch at one point, their mutual center.
        #
        # We do *not* attempt to make the slot surface parallel to the intersection plane.
        # In general, this would require at least one of the two slot *surfaces* to be a
        # miter cut which is basically impossible with the tools I have, and anyway is never
        # necessary (even if we later allow the sides to be miters).
        front_wall = front_face.Shape.Surface.intersect(cutout.CenterPlane.Shape.Surface)
        back_wall = back_face.Shape.Surface.intersect(cutout.CenterPlane.Shape.Surface)
        if not front_wall or not back_wall:
            if warn:
                App.Console.PrintWarning(
                    f"ShaperCutout '{cutout.Label}' slot '{slot.Label}': could not find "
                    "intersection between center plane and other cutout's side.\n")
            return None
        front_wall = front_wall[0]
        back_wall = back_wall[0]
        front_intersect = slot.InterfacePlane.Shape.Surface.intersect(front_wall)
        back_intersect = slot.InterfacePlane.Shape.Surface.intersect(back_wall)
        if not front_intersect or not front_intersect[0] \
                or not back_intersect or not back_intersect[0]:
            if warn:
                App.Console.PrintWarning(
                    f"ShaperCutout '{cutout.Label}' slot '{slot.Label}': could not find "
                    f"intersection between side and interface '{slot.InterfacePlane.Label}.\n")
            return None
        front_intersect = App.Vector(
            front_intersect[0][0].X,
            front_intersect[0][0].Y,
            front_intersect[0][0].Z,
        )
        back_intersect = App.Vector(
            back_intersect[0][0].X,
            back_intersect[0][0].Y,
            back_intersect[0][0].Z,
        )
        intersect = (front_intersect + back_intersect) / 2.0

        sketch_bound_box = cutout.OutlineSketch.Shape.BoundBox
        # The two points of "the surface" described in the block comment above.
        edge_p0 = front_wall.projectPoint(intersect) - slot.LengthTolerance.Value * slot_dir
        edge_p1 = back_wall.projectPoint(intersect) - slot.LengthTolerance.Value * slot_dir

        return SlotData(
            slot_index, edge_p0, edge_p1, slot_dir,
            slot.WidthTolerance, slot.LengthTolerance, sketch_bound_box,
            front_dado_depth, back_dado_depth, other_front_dado_depth, other_back_dado_depth,
        )


class ViewProviderShaperSlot:
    def __init__(self, vobj):
        vobj.Proxy = self

    def attach(self, vobj):
        self.ViewObject = vobj
        self.Object = vobj.Object

    def getIcon(self):
        return os.path.join(_ICON_ROOT, "slot.svg")

    def claimChildren(self):
        return []

    def doubleClicked(self, vobj):
        from command.create_shaper_slot import open_slot_task_panel
        open_slot_task_panel(vobj.Object)
        return True

    def setupContextMenu(self, vobj, menu):
        from command.create_shaper_slot import open_slot_task_panel
        edit_action = QtGui.QAction("Edit Slot", menu)
        edit_action.triggered.connect(lambda: open_slot_task_panel(vobj.Object))
        menu.addAction(edit_action)

    def dumps(self):
        return None

    def loads(self, state):
        return None
