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
        if not hasattr(obj, 'Cutout1_DadoDepth'):
            obj.addProperty('App::PropertyLength', 'Cutout1_DadoDepth', 'Cutout1',
                            'Depth of the dado cut into cutout 1 (0 to disable)')
        if not hasattr(obj, 'Cutout2_DadoDepth'):
            obj.addProperty('App::PropertyLength', 'Cutout2_DadoDepth', 'Cutout2',
                            'Depth of the dado cut into cutout 2 (0 to disable)')

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
