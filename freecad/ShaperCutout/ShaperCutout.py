# SPDX-License-Identifier: GPL-3.0-or-later

import os
import FreeCAD as App
import Part
from PySide import QtGui

from ShaperMiter import miter_edges
from command import open_cutout_task_panel
from shaper_cutout_util import move_to_root as _move_to_root, insert_if_missing


def _remove_from_group(obj):
    for parent in obj.InList:
        if hasattr(parent, 'Group') and obj in parent.Group:
            App.Console.PrintLog(
                f"ShaperCutout: moving '{obj.Label}' out of current group '{parent.Label}'")
            parent.removeObject(obj)


def create_uninitialized(name):
    doc = App.ActiveDocument
    obj_name = 'ShaperCutout' if name == '' else name
    obj = doc.addObject('Part::FeaturePython', obj_name)
    # App::GroupExtensionPython gets us the .Group property
    obj.addExtension('App::GroupExtensionPython')
    ShaperCutout(obj)
    if App.GuiUp:
        ViewProviderShaperCutout(obj.ViewObject)
        # Gui::ViewProviderGroupExtensionPython gets us group-like behavior in the Tree View
        obj.ViewObject.addExtension('Gui::ViewProviderGroupExtensionPython')
    return obj


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
        if not obj.CenterPlane or not obj.Thickness:
            return

        # Create faces if they don't exist, re-place them, and mark them as updated.
        self.ensure_front_face(obj).purgeTouched()
        self.ensure_back_face(obj).purgeTouched()

        if not obj.OutlineSketch:
            obj.Shape = Part.Shape()
            return

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

        # Add/subtract miters
        for member in obj.Group:
            if (member is not None and
                    getattr(member, 'Type', None) == 'ShaperMiter'):
                if not member.Edges or member.Angle is None:
                    # Skip uninitialized/null/broken miters
                    continue
                shape = miter_edges(shape, member, obj.CenterPlane, obj.Thickness.Value)

        # Subtract dado pockets
        for member in obj.Group:
            if (member is not None and
                    getattr(member, 'Type', None) == 'ShaperDados'):
                pocket = member.PocketShape
                if pocket is not None and pocket.Solids:
                    shape = shape.cut(pocket)

        obj.Shape = shape

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

    def dumps(self):
        return None

    def loads(self, state):
        return None

    def ensure_back_face(self, obj):
        """Recreate front face if missing or link broken."""
        if obj.CenterPlane is None or obj.Thickness is None:
            return None

        if obj.BackFace is None:
            obj.BackFace = obj.Document.addObject('App::Plane', 'Back')
            insert_if_missing(obj, obj.BackFace)

        placement = obj.CenterPlane.Placement
        half = obj.Thickness.Value / 2.0
        obj.BackFace.Placement = placement.copy()
        obj.BackFace.Placement.translate(placement.Rotation.multVec(App.Vector(0, 0, -half)))

        return obj.BackFace

    def ensure_front_face(self, obj):
        """Recreate front face if missing or link broken."""
        if obj.CenterPlane is None or obj.Thickness is None:
            return None

        if obj.FrontFace is None:
            obj.FrontFace = obj.Document.addObject('App::Plane', 'Front')
            insert_if_missing(obj, obj.FrontFace)

        placement = obj.CenterPlane.Placement
        half = obj.Thickness.Value / 2.0
        obj.FrontFace.Placement = placement.copy()
        obj.FrontFace.Placement.translate(placement.Rotation.multVec(App.Vector(0, 0, half)))

        return obj.FrontFace


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
