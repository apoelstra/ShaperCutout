# SPDX-License-Identifier: GPL-3.0-or-later

import os
import FreeCAD as App
import Part
from PySide import QtGui

from command.create_shaper_dados import open_dados_task_panel
from util import move_to_root, insert_if_missing


def create(cutout, face, invert, depth, name="ShaperDados"):
    doc = App.ActiveDocument
    obj = doc.addObject('App::DocumentObjectGroupPython', name)
    obj.Label = name
    ShaperDados(obj)
    if App.GuiUp:
        ViewProviderShaperDados(obj.ViewObject)

    obj.Face = face
    obj.Invert = invert

    # Nest inside the ShaperCutout group
    grp = list(cutout.Group)
    grp.append(obj)
    cutout.Group = grp

    _ensure_dado_plane(obj)

    doc.recompute()
    return obj


def _parent_cutout(dados):
    for o in dados.Document.Objects:
        if (getattr(o, 'Type', None) == 'ShaperCutout' and dados in o.Group):
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
    insert_if_missing(collection, plane)
    return plane


class ShaperDados:
    def __init__(self, obj):
        obj.Proxy = self

        obj.addProperty('App::PropertyString', 'Type', 'Internal',
                        'Type ID used to identify instances')
        obj.addProperty('App::PropertyLink', 'Face', 'Base',
                        'Front or back face this dado cuts into.')
        obj.addProperty('App::PropertyBool', 'Invert', 'Base',
                        'Direction to cut dado pockets into the face')
        obj.addProperty('App::PropertyLength', 'Depth', 'Base',
                        'Depth of the dado pocket.')
        obj.addProperty('App::PropertyLinkList', 'Sketches', 'Base',
                        'Sketches describing the dado pocket outlines.')
        obj.addProperty('App::PropertyLink', 'DadoPlane', 'Internal',
                        'Datum plane at the dado depth.')
        obj.addProperty('Part::PropertyPartShape', 'PocketShape', 'Internal',
                        'Computed pocket solid for subtraction.')

        obj.Type = "ShaperDados"
        obj.setEditorMode('Type', 2)
        obj.setEditorMode('DadoPlane', 2)
        obj.setEditorMode('PocketShape', 2)
        obj.setPropertyStatus('Face', 2)

    def onChanged(self, obj, prop):
        if prop == 'Group':
            keep = set(obj.Sketches or []) | {obj.DadoPlane}
            for member in list(obj.Group):
                if member is None:
                    continue
                if member not in keep:
                    App.Console.PrintWarning(
                        f"ShaperDados: removing unlinked member '{member.Label}'\n")
                    move_to_root(member)

    def execute(self, obj):
        if not obj.Face or not obj.Depth:
            return

        parent = _parent_cutout(obj)
        if parent is not None and parent.Thickness:
            if obj.Depth.Value > parent.Thickness.Value:
                App.Console.PrintWarning(
                    f"ShaperDados '{obj.Label}': Depth ({obj.Depth}) "
                    f"exceeds sheet Thickness ({parent.Thickness})\n")

        normal = obj.Face.Placement.Rotation.multVec(App.Vector(0, 0, 1))

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
            face_origin = obj.Face.Placement.Base
            for wire in wires:
                try:
                    wire_normal = wire.findPlane().Axis
                    if wire_normal.cross(normal).Length >= 1e-6:
                        App.Console.PrintWarning(
                            f"ShaperDados '{obj.Label}': wire from "
                            f"'{member.Label}' is not parallel to face; "
                            f"projecting anyway\n")
                except Exception:
                    pass
                dist = (face_origin - wire.CenterOfGravity).dot(normal)
                translated_wire = wire.copy()
                translated_wire.translate(App.Vector(
                    normal.x * dist,
                    normal.y * dist,
                    normal.z * dist,
                ))
                try:
                    face = Part.Face(translated_wire)
                    solids.append(face.extrude(extrude_vec))
                except Exception as e:
                    App.Console.PrintWarning(
                        f"ShaperDados '{obj.Label}': extrude failed for "
                        f"'{member.Label}': {e}\n")

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


class ViewProviderShaperDados:
    def __init__(self, vobj):
        vobj.Proxy = self

    def attach(self, vobj):
        pass

    def getIcon(self):
        return os.path.join(os.path.dirname(__file__), "resources/icons/dados.svg")

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
