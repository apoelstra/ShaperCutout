# SPDX-License-Identifier: GPL-3.0-or-later

import os
import FreeCAD as App
import Part
from PySide import QtGui

from ShaperMiter import miter_edges
from command.create_shaper_cutout import open_cutout_task_panel
from util import move_to_root as _move_to_root, insert_if_missing as _insert_if_missing


def _remove_from_group(obj):
    for parent in obj.InList:
        if hasattr(parent, 'Group') and obj in parent.Group:
            App.Console.PrintLog(
                f"ShaperCutout: moving '{obj.Label}' out of current group '{parent.Label}'")
            parent.removeObject(obj)


def create(obj_name, center_plane, outline_sketch, thickness, own_sketch=True, own_plane=False):
    doc = App.ActiveDocument
    outer_name = 'ShaperCutout' if obj_name == '' else obj_name
    outer = doc.addObject('Part::FeaturePython', outer_name)
    # App::GroupExtensionPython gets us the .Group property
    outer.addExtension('App::GroupExtensionPython')
    ShaperCutout(outer)
    if App.GuiUp:
        ViewProviderShaperCutout(outer.ViewObject)
        # Gui::ViewProviderGroupExtensionPython gets us group-like behavior in the Tree View
        outer.ViewObject.addExtension('Gui::ViewProviderGroupExtensionPython')

        # Tweak appearances (just do this on creation; the user can do what they
        # want afterward)
        # Transparency seems to just not work very well and results in confusing tearing.
        # It would be nice to see how stuff slots into dados but I don't have a reliable
        # way to do it. This is not it.
        #outer.ViewObject.Transparency = 15  # slight transparency to help dado
        outline_sketch.Visibility = False

    # Wire up
    outer.Thickness = thickness
    outer.CenterPlane = center_plane
    outer.OutlineSketch = outline_sketch

    if not center_plane or not outline_sketch:
        # If we are missing data, give up here.
        return outer

    # Move the center and/or the outline into the group based on ownership.
    label_prefix = '' if obj_name == '' else obj_name + '_'
    initial_group = []
    if own_plane:
        _remove_from_group(center_plane)
        initial_group.append(center_plane)
        center_plane.Label = label_prefix + 'Center'
    if own_sketch:
        _remove_from_group(outline_sketch)
        outline_sketch.Label = label_prefix + 'Outline'
        initial_group.append(outline_sketch)
    outer.Group = initial_group

    _ensure_front_face(label_prefix, outer)
    _ensure_back_face(label_prefix, outer)

    doc.recompute()
    return outer


# ---------------------------------------------------------------------------
# Outer container
# ---------------------------------------------------------------------------

def _ensure_back_face(label_prefix, obj):
    """Recreate back face if missing or link broken."""
    face = obj.BackFace
    if face is not None and face in obj.Document.Objects:
        return face
    face = obj.Document.addObject('Part::DatumPlane', label_prefix + 'Back')
    obj.BackFace = face
    obj.setEditorMode('BackFace', 2)
    _insert_if_missing(obj, face)
    return face


def _ensure_front_face(label_prefix, obj):
    """Recreate front face if missing or link broken."""
    face = obj.FrontFace
    if face is not None and face in obj.Document.Objects:
        return face
    face = obj.Document.addObject('Part::DatumPlane', label_prefix + 'Front')
    obj.FrontFace = face
    obj.setEditorMode('FrontFace', 2)
    _insert_if_missing(obj, face)
    return face


class ShaperCutout:
    def __init__(self, obj):
        obj.Proxy = self

        obj.addProperty('App::PropertyString', 'Type', 'Internal',
                        'Type ID used to identify instances')
        obj.addProperty('App::PropertyLink', 'CenterPlane', 'Base',
                        'Datum plane representing the center of the sheet.')
        obj.addProperty('App::PropertyLink', 'OutlineSketch', 'Base',
                        'Sketch describing the sheet outline.')
        obj.addProperty('App::PropertyLength', 'Thickness', 'Base',
                        'Thickness of the sheet.')
        obj.addProperty('App::PropertyLink', 'FrontFace', 'Internal',
                        'Front (positive z offset) plane of the sheet.')
        obj.addProperty('App::PropertyLink', 'BackFace', 'Internal',
                        'Back (negative z offset) plane of the sheet.')

        obj.Type = "ShaperCutout"
        obj.setPropertyStatus('OutlineSketch', 2)
        obj.setPropertyStatus('CenterPlane', 2)
        obj.setEditorMode('Type', 2)
        obj.setEditorMode('FrontFace', 2)
        obj.setEditorMode('BackFace', 2)

    def onChanged(self, obj, prop):
        # Make a cursory effort to preserve the group structure.
        if prop == 'Group':
            _insert_if_missing(obj, obj.FrontFace)
            _insert_if_missing(obj, obj.BackFace)
            # If the user moved something into the group, and it wasn't one of
            # ours, reject it.
            keep = {
                obj.CenterPlane,
                obj.FrontFace,
                obj.BackFace,
                obj.OutlineSketch,
            } - {None}
            # Also keep any dados and miters
            for member in list(obj.Group):
                if (member is not None and
                        getattr(member, 'Type', None) in ('ShaperDados', 'ShaperMiter')):
                    keep.add(member)
            for member in list(obj.Group):
                if member not in keep:
                    _move_to_root(member)
            # Don't attempt to move the "user-owned" things back in. If the
            # user wants to pull the outline or center plane out of the group,
            # whatever, they can make a mess of the tree. We also don't worry
            # about the user changing links; we set the link properties to
            # ReadOnly, which should signal the user that they'll break stuff
            # if they mess with them.
            #
            # FIXME we probably should try to move Dados back in, since these
            # have links to the front/back face of the ShapeCutout but we don't
            # notice them unless they're in the group. So letting the user move
            # these sets around freely is likely to lead to confusing situations.

    def getSubObjects(self, obj, reason):
        # The FreeCAD STEP exporter, in App/ExportOCAF2.cpp line 476, calls this
        # `auto subs = obj->getSubObjects();` and then gates a bunch of code on
        # the result being empty. Part Booleans seem to return this being empty.
        # By default we don't, because we have the Group extensions on. But if
        # Part::Cut can do it then surely it's harmless if we do it.
        #
        # Having said this, this is almost certainly a bug in FreeCAD that we need
        # to do this. You can export ShaperCutouts with Part.export (deprecated)
        # but not with ImportGui.export (the new shiny version). Oh well, just work
        # around it.
        return []

    def execute(self, obj):
        # Do nothing, not even attempt to recreate stuff, if the links are bad.
        if not obj.CenterPlane or not obj.OutlineSketch or not obj.Thickness:
            return

        label_prefix = obj.Label + '_'
        front_face = _ensure_front_face(label_prefix, obj)
        back_face = _ensure_back_face(label_prefix, obj)

        # Compute data
        plane_origin = obj.CenterPlane.Placement.Base
        normal = obj.CenterPlane.Placement.Rotation.multVec(App.Vector(0, 0, 1))
        half = obj.Thickness.Value / 2.0
        extrude_vec = App.Vector(normal.x * half * 2,
                                 normal.y * half * 2,
                                 normal.z * half * 2)

        sketch_origin = obj.OutlineSketch.Shape.CenterOfGravity
        dist = (plane_origin - sketch_origin).dot(normal)
        offset_vec = App.Vector(normal.x * (-half + dist),
                                normal.y * (-half + dist),
                                normal.z * (-half + dist))

        # Create shape
        wires = obj.OutlineSketch.Shape.Wires
        if not wires:
            return

        try:
            sketch_axis = wires[0].findPlane().Axis
            if sketch_axis.cross(normal).Length >= 1e-6:
                App.Console.PrintWarning(
                    f"ShaperCutout '{obj.Label}': outline sketch is not parallel "
                    f"to center plane; projecting anyway\n")
        except Exception:
            pass

        # Create single Face from all wires, which will cause "inner" wires to cut
        # holes in "outer" wires. This seems more intuitive/useful than iterating
        # through the wires and fusing them. We may want to provide an option,
        # eventually.
        face = Part.makeFace(wires)
        face.translate(offset_vec)
        shape = face.extrude(extrude_vec)

        # Subtract dado pockets
        for member in obj.Group:
            if (member is not None and
                    getattr(member, 'Type', None) == 'ShaperDados'):
                pocket = member.PocketShape
                if pocket is not None and pocket.Solids:
                    shape = shape.cut(pocket)

        # Add/subtract miters
        for member in obj.Group:
            if (member is not None and
                    getattr(member, 'Type', None) == 'ShaperMiter'):
                if not member.Edges or member.Angle is None:
                    # Skip uninitialized/null/broken miters
                    continue
                shape = miter_edges(shape, member, obj.CenterPlane, obj.Thickness.Value)

        obj.Shape = shape

        back_face.AttachmentSupport = [(obj.CenterPlane)]
        back_face.MapMode = 'FlatFace'
        back_face.AttachmentOffset = App.Placement(App.Vector(0, 0, -half), App.Rotation(0, 0, 0))
        front_face.AttachmentSupport = [(obj.CenterPlane)]
        front_face.MapMode = 'FlatFace'
        front_face.AttachmentOffset = App.Placement(App.Vector(0, 0, half), App.Rotation(0, 0, 0))

        # The previous computations will cause FreeCAD to mark the children as "touched",
        # causing "wb_test#ShaperCutout_Body still touched after recompute" errors in the
        # console (and spurious blue "needs recompute" checkmarks). The 'correct' way to
        # avoid this would be for the objects to set their own properties in their own
        # execute() methods, but this is impossible for a couple of reasons. (One is that
        # ShaperCutout has a link to its child objects, and if they then tried to access
        # the Thickness property of their parent, this would cause a circularity in the
        # DAG. Another is that overriding execute() on the planes would require changing
        # them to by PythonFeatures rather than DatumPlanes, and then we couldn't use
        # them in sketches as external geometry, which is their whole point of existing.)
        front_face.purgeTouched()
        back_face.purgeTouched()

    def dumps(self):
        return None

    def loads(self, state):
        return None


class ViewProviderShaperCutout:
    def __init__(self, vobj):
        vobj.Proxy = self

    def attach(self, vobj):
        pass

    def getIcon(self):
        return os.path.join(os.path.dirname(__file__), "resources/icons/cutout.svg")

    def doubleClicked(self, vobj):
        open_cutout_task_panel(vobj.Object)
        return True

    def setupContextMenu(self, vobj, menu):
        from command.export_shaper_svg import export
        edit_action = QtGui.QAction("Edit Shaper Cutout", menu)
        edit_action.triggered.connect(lambda: open_cutout_task_panel(vobj.Object))
        menu.addAction(edit_action)

        export_action = QtGui.QAction("Export Shaper SVG (Front)", menu)
        export_action.triggered.connect(lambda: export(vobj.Object, True))
        menu.addAction(export_action)

        export_action = QtGui.QAction("Export Shaper SVG (Back)", menu)
        export_action.triggered.connect(lambda: export(vobj.Object, False))
        menu.addAction(export_action)

    def updateData(self, fp, prop):
        pass

    def getDisplayModes(self, obj):
        return []

    def getDefaultDisplayMode(self):
        return "Flat Lines"

    def setDisplayMode(self, mode):
        return mode

    def onChanged(self, vp, prop):
        pass

    def dumps(self):
        return None

    def loads(self, state):
        return None
