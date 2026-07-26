# SPDX-License-Identifier: GPL-3.0-or-later

import os
import FreeCAD as App
from PySide import QtGui

from shaper_cutout_util import _ICON_ROOT


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

        obj.addProperty('App::PropertyString', 'Type', 'Internal',
                        'Type ID used to identify instances')
        obj.addProperty('App::PropertyLink', 'Cutout1Front', 'Base',
                        'Front face plane of first ShaperCutout')
        obj.addProperty('App::PropertyLink', 'Cutout1Back', 'Base',
                        'Back face plane of first ShaperCutout')
        obj.addProperty('App::PropertyLink', 'Cutout2Front', 'Base',
                        'Front face plane of second ShaperCutout')
        obj.addProperty('App::PropertyLink', 'Cutout2Back', 'Base',
                        'Back face plane of second ShaperCutout')
        obj.addProperty('App::PropertyLink', 'InterfacePlane', 'Base',
                        'Plane defining the slot interface')
        obj.addProperty('App::PropertyBool', 'Invert', 'Base',
                        'Invert the slot direction')

        obj.Type = 'ShaperSlot'
        obj.Invert = False

        obj.setEditorMode('Type', 2)

    def execute(self, obj):
        pass

    def dumps(self):
        return None

    def loads(self, state):
        return None

    def find_cutout1(self, obj):
        for parent in obj.Cutout1Back.InList:
            if getattr(parent, 'Type', '') != 'ShaperCutout':
                continue
            if obj in getattr(parent, 'Slots', []):
                return parent

    def find_cutout2(self, obj):
        for parent in obj.Cutout2Back.InList:
            if getattr(parent, 'Type', '') != 'ShaperCutout':
                continue
            if obj in getattr(parent, 'Slots', []):
                return parent


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
