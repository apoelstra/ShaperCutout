# SPDX-License-Identifier: GPL-3.0-or-later

import os
import FreeCAD as App
import Part
from PySide import QtGui, QtWidgets, QtCore

from ShaperMiter import miter_edges
from command import open_cutout_task_panel
from shaper_cutout_util import global_normal, is_sketch, objects_are_parallel


def create_uninitialized(name=None):
    doc = App.ActiveDocument
    obj_name = 'ShaperCutout' if name is None else name
    obj = doc.addObject('Part::FeaturePython', obj_name)
    ShaperCutout(obj)
    if App.GuiUp:
        ViewProviderShaperCutout(obj.ViewObject)

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

    def onChanged(self, obj, prop):
        if getattr(obj, 'CenterPlane', None) is None:
            return
        if getattr(obj, 'Thickness', None) is None:
            return

        # Create faces if they don't exist, re-place them, and mark them as updated.
        if prop in ('CenterPlane', 'Thickness'):
            self.ensure_front_face(obj)
            self.ensure_back_face(obj)
        elif obj.FrontFace is None:
            self.ensure_front_face(obj)
        elif obj.BackFace is None:
            self.ensure_back_face(obj)

    def execute(self, obj):
        if not obj.CenterPlane or not obj.Thickness:
            return

        if not obj.OutlineSketch:
            obj.Shape = Part.Shape()
            return

        # Compute data
        plane_origin = obj.CenterPlane.Placement.Base
        thickness = obj.Thickness.Value
        normal = global_normal(obj.CenterPlane)
        half = thickness / 2.0
        extrude_vec = (half * 2) * normal

        sketch_origin = obj.OutlineSketch.Shape.CenterOfGravity
        dist = (plane_origin - sketch_origin).dot(normal)
        offset_vec = (-half + dist) * normal

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
            shape = miter_edges(shape, member, obj.CenterPlane, thickness)

        # Subtract dado pockets
        for member in obj.Dados:
            if member.Depth.Value > thickness:
                App.Console.PrintWarning(
                    f"Warning: ShaperDados '{member.Label}': Depth ({member.Depth}) exceeds "
                    f"parent sheet `{obj.Label}'  Thickness ({obj.Thickness}).\n")
                # Try to do it anyway, just warn.

            pocket = member.PocketShape
            if pocket is not None and pocket.Solids:
                shape = shape.cut(pocket)

            # These faces all sit on the dado's reference face, not its plane, so the cut depth
            # for holes will be the full thickness.
            faces = member.AutodrillFaces
            if faces is not None and faces.Faces:
                drill_vec = thickness * (-normal if member.Invert else normal)
                pocket = faces.extrude(drill_vec)
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

        # We need the group extension for drag/drop to work, but we leave the actual Group empty.
        # Old versions of the extension put stuff in Group, so empty it out here and put stuff
        # in their right places.
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

        if hasattr(obj, 'Group'):
            obj.Group = []
        else:
            obj.addExtension("App::GroupExtensionPython")

        # Install faces
        self.ensure_front_face(obj)

    def ensure_back_face(self, obj):
        """Recreate front face if missing or link broken."""

        if obj.BackFace is None:
            obj.BackFace = obj.Document.addObject('Part::DatumPlane', 'Back')

        half = obj.Thickness.Value / 2.0
        obj.BackFace.AttachmentSupport = [(obj.CenterPlane)]
        obj.BackFace.MapMode = 'FlatFace'
        obj.BackFace.AttachmentOffset = App.Placement(
            App.Vector(0, 0, -half),
            App.Rotation(0, 0, 0),
        )

        return obj.BackFace

    def ensure_front_face(self, obj):
        """Recreate front face if missing or link broken."""
        if obj.FrontFace is None:
            obj.FrontFace = obj.Document.addObject('Part::DatumPlane', 'Front')

        half = obj.Thickness.Value / 2.0
        obj.FrontFace.AttachmentSupport = [(obj.CenterPlane)]
        obj.FrontFace.MapMode = 'FlatFace'
        obj.FrontFace.AttachmentOffset = App.Placement(
            App.Vector(0, 0, half),
            App.Rotation(0, 0, 0),
        )

        return obj.FrontFace


class _DropChoiceDialog(QtWidgets.QDialog):
    def __init__(self, old_label, new_label, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Drop Sketch")
        self.result = 'cancel'

        layout = QtWidgets.QVBoxLayout(self)
        layout.setAlignment(QtCore.Qt.AlignCenter)

        label = QtWidgets.QLabel(
            f"Drop '{new_label}' onto cutout with existing outline '{old_label}':")
        label.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(label)

        for text, value in [
            ("Create Dado Set", 'dado'),
            ("Replace Outline Sketch", 'replace'),
            ("Cancel", 'cancel'),
        ]:
            btn = QtWidgets.QPushButton(text)
            btn.clicked.connect(lambda checked=False, v=value: self._choose(v))
            layout.addWidget(btn, alignment=QtCore.Qt.AlignCenter)

    def _choose(self, value):
        self.result = value
        self.accept()


class ViewProviderShaperCutout:
    def __init__(self, vobj):
        vobj.addExtension("Gui::ViewProviderGroupExtensionPython")
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

    def canDragObjects(self):
        return True

    # Whether it is allowed to drag objects out of the container.
    #
    # We allow the outline sketch to be "dragged out". This will not actually remove the
    # sketch from the container -- we only enable it so that you can drag outlines onto
    # other cutouts.
    def canDragObject(self, child):
        # We also need to give permission to drag stuff out of our dado sets, even
        # though they do their own filtering. We just blanket-allow it.
        for dado in self.Object.Dados:
            if child in dado.Sketches:
                return True
        return child == self.Object.OutlineSketch

    def dragObject(self, vobj, child):
        # Dragging out doesn't actually do anything. If you want to remove the outline sketch
        # you need to edit the Cutout and remove it.
        pass

    def canDropObjects(self):
        return True

    def canDropObject(self, child):
        # Whether it's allowed to drop stuff in the child -- we allow only sketches. (Actually
        # we have further restrictions but we defer them to when the user actually does the
        # drop, since then we can output warnings and be sure they'll only be printed once.)
        return is_sketch(child)

    # The only thing permissible to drop on a ShaperCutout is a sketch, which can be used
    # to set the outline.
    def dropObject(self, vobj, child):
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
            dlg = _DropChoiceDialog(self.Object.OutlineSketch.Label, child.Label)
            dlg.exec_()
            choice = dlg.result

            if choice == 'replace':
                self.Object.Document.openTransaction("Replace outline sketch")
                self.Object.OutlineSketch = child
                self.Object.recompute()
                self.Object.Document.commitTransaction()
            elif choice == 'dado':
                from command.create_shaper_dados import open_dados_task_panel
                open_dados_task_panel(self.Object, initial_sketches=[child])
            # 'cancel' — do nothing

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
