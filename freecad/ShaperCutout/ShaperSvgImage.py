# SPDX-License-Identifier: GPL-3.0-or-later

import FreeCAD as App
import FreeCADGui as Gui


def create(page, cutout, name="ShaperSvgImage"):
    doc = page.Document
    obj = doc.addObject('App::DocumentObjectGroupPython', name)
    obj.Label = name
    ShaperSvgImage(obj)
    if App.GuiUp:
        ViewProviderShaperSvgImage(obj.ViewObject)
    page.addObject(obj)
    obj.Cutout = cutout
    doc.recompute()
    return obj


class ShaperSvgImage:
    def __init__(self, obj):
        obj.Proxy = self

        obj.addProperty('App::PropertyString', 'Type', 'Internal',
                        'Type ID used to identify instances')
        obj.addProperty('App::PropertyLink', 'Cutout', 'Base',
                        'The ShaperCutout this image represents.')
        obj.addProperty('App::PropertyBool', 'Flip', 'Base',
                        'False = front face, True = back face.')
        obj.addProperty('App::PropertyBool', 'Invert', 'Base',
                        'Mirror the image over its Y axis.')
        obj.addProperty('App::PropertyAngle', 'Rotation', 'Base',
                        'Rotation about the image bounding box center (degrees).')
        obj.addProperty('App::PropertyLength', 'OffsetX', 'Base',
                        'X offset from page bottom-left to image bottom-left (mm).')
        obj.addProperty('App::PropertyLength', 'OffsetY', 'Base',
                        'Y offset from page bottom-left to image bottom-left (mm).')

        obj.Type = 'ShaperSvgImage'
        obj.Flip = False
        obj.Invert = False
        obj.Rotation = 0.0
        obj.OffsetX = 0.0
        obj.OffsetY = 0.0

    def execute(self, obj):
        pass

    def dumps(self):
        return None

    def loads(self, state):
        return None


class ViewProviderShaperSvgImage:
    def __init__(self, vobj):
        vobj.Proxy = self

    def attach(self, vobj):
        self._vobj = vobj

    def getIcon(self):
        import os
        return os.path.join(os.path.dirname(__file__),
                            'resources/icons/export-svg-front.svg')

    def dumps(self):
        return None

    def loads(self, state):
        return None
