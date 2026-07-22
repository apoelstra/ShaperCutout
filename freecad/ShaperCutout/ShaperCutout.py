# SPDX-License-Identifier: GPL-3.0-or-later

import os
import FreeCAD as App
import Part
from PySide import QtGui

from ShaperMiter import miter_edges
from command import open_cutout_task_panel
from shaper_cutout_util import global_normal, is_sketch, objects_are_parallel


def create_uninitialized(name):
    doc = App.ActiveDocument
    obj_name = 'ShaperCutout' if name == '' else name
    obj = doc.addObject('Part::FeaturePython', obj_name)
    # App::GroupExtensionPython gets us the .Group property
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
        obj.addProperty('App::PropertyLinkList', 'Dados', 'Internal',
                        'The dado sets associated with this cutout.')
        obj.addProperty('App::PropertyLinkList', 'Miters', 'Internal',
                        'The miters associated with this cutout.')

        obj.Type = "ShaperCutout"
        obj.setPropertyStatus('OutlineSketch', 2)
        obj.setPropertyStatus('CenterPlane', 2)
        obj.setEditorMode('Type', 2)
        obj.setEditorMode('FrontFace', 2)
        obj.setEditorMode('BackFace', 2)
        obj.setEditorMode('Dados', 2)
        obj.setEditorMode('Miters', 2)

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
        normal = global_normal(obj.CenterPlane)
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
        sketch_normal = global_normal(obj.OutlineSketch)
        wires = obj.OutlineSketch.Shape.Wires
        if not wires:
            return

        try:
            if sketch_normal.cross(normal).Length >= 1e-6:
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
        for member in obj.Miters:
            if not member.Edges or member.Angle is None:
                # Skip uninitialized/null/broken miters
                continue
            shape = miter_edges(shape, member, obj.CenterPlane, obj.Thickness.Value)

        # Subtract dado pockets
        for member in obj.Dados:
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

    def onDocumentRestored(self, obj):
        # Add missing lists
        if not hasattr(obj, 'Dados'):
            obj.addProperty('App::PropertyLinkList', 'Dados', 'Internal',
                            'The dado sets associated with this cutout.')
            obj.setEditorMode('Dados', 2)

        if not hasattr(obj, 'Miters'):
            obj.addProperty('App::PropertyLinkList', 'Miters', 'Internal',
                            'The miters associated with this cutout.')
            obj.setEditorMode('Miters', 2)

        # Empty out old Group list
        newdados = list(obj.Dados)
        newmiters = list(obj.Miters)
        for gchild in getattr(obj, 'Group', []):
            # Pull the dados and miters out, drop everything else (which should just be planes and
            # the outline sketch, already redundantly covered by existing links).
            if getattr(gchild, 'Type', '') == 'ShaperDados':
                newdados.append(gchild)
            elif getattr(gchild, 'Type', '') == 'ShaperMiter':
                newmiters.append(gchild)
        obj.Dados = newdados
        obj.Miters = newmiters

        obj.Group = []

    def ensure_back_face(self, obj):
        """Recreate front face if missing or link broken."""
        if obj.CenterPlane is None or obj.Thickness is None:
            return None

        if obj.BackFace is None:
            obj.BackFace = obj.Document.addObject('App::Plane', 'Back')

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

        placement = obj.CenterPlane.Placement
        half = obj.Thickness.Value / 2.0
        obj.FrontFace.Placement = placement.copy()
        obj.FrontFace.Placement.translate(placement.Rotation.multVec(App.Vector(0, 0, half)))

        return obj.FrontFace


class ViewProviderShaperCutout:
    def __init__(self, vobj):
        vobj.Proxy = self

    def attach(self, vobj):
        self.ViewObject = vobj
        self.Object = vobj.Object
        pass

    def getIcon(self):
        return os.path.join(os.path.dirname(__file__), "resources/icons/cutout.svg")

    # Which "children" show up in the Tree View. Curiously there is no requirement that
    # the parent relationship be unique, so many cutouts can claim the same sketches
    # or planes.
    def claimChildren(self):
        return [
            self.Object.OutlineSketch,
            self.Object.CenterPlane,
            self.Object.FrontFace,
            self.Object.BackFace,
        ] + self.Object.Dados + self.Object.Miters

    # Whether it is allowed to drag objects out of the container.
    #
    # We allow the outline sketch to be "dragged out". This will not actually remove the
    # sketch from the container -- we only enable it so that you can drag outlines onto
    # other cutouts.
    def canDragObject(self, child):
        # We also need to give permission to drag stuff out of our dado sets, even
        # though they do their own filtering. We just blanket-allow it.
        for dado in self.Object.Dados:
            if child in dado.Group:
                return True
        return child == self.Object.OutlineSketch

    def dragObject(self, vobj, child):
        # Dragging out doesn't actually do anything. If you want to remove the outline sketch
        # you need to edit the Cutout and remove it.
        pass

    # The only thing permissible to drop on a ShaperCutout is a sketch, which can be used
    # to set the outline.
    def dropObject(self, vobj, child):
        print(f"drop in Cutout {child.Label}")
        if not is_sketch(child):
            return

        if not objects_are_parallel(self.Object.CenterPlane, child):
            # Annoyingly, this does not cancel the removal from the source, so we drop the item
            # in the document root. But you can Ctrl+Z this so I guess it's okay. The alternative
            # is to reject in canDragObject, but we can't print warnings there because it's called
            # too often during mouse hovering.
            App.Console.PrintWarning(
                f"Sketch '{child.Label}': outline sketch is not parallel to Cutout; rejecting.\n")
            return

        if self.Object.OutlineSketch is None:
            self.Object.Document.openTransaction("Replace outline sketch")
            self.Object.OutlineSketch = child
            self.Object.Document.commitTransaction()
        else:
            msg_box = QtGui.QMessageBox()
            msg_box.setText(
                f"Replace existing outline sketch ({self.Object.OutlineSketch.Label}) "
                f"with {child.Label}?"
            )
            replace_btn = msg_box.addButton(QtGui.QMessageBox.Yes)
            msg_box.addButton(QtGui.QMessageBox.Cancel)
            msg_box.setDefaultButton(QtGui.QMessageBox.Cancel)
            print(msg_box.exec_())

            self.Object.Document.openTransaction("Replace outline sketch")
            if msg_box.clickedButton() == replace_btn:
                self.Object.OutlineSketch = child
                self.Object.recompute()  # recompute inside Undo transaction
                self.Object.Document.commitTransaction()
            else:
                self.Object.Document.abortTransaction()

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
