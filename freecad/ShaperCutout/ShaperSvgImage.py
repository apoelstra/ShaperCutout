# SPDX-License-Identifier: GPL-3.0-or-later

import os

import FreeCAD as App

from shaper_cutout_util import _ICON_ROOT


def create(page, cutout, name):
    doc = page.Document
    obj = doc.addObject('App::FeaturePython', name)
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
        obj.addProperty('App::PropertyDistance', 'OffsetX', 'Base',
                        'X offset from page bottom-left to image bottom-left (mm).')
        obj.addProperty('App::PropertyDistance', 'OffsetY', 'Base',
                        'Y offset from page bottom-left to image bottom-left (mm).')

        self.addSvgProperties(obj)

        obj.Type = 'ShaperSvgImage'
        obj.Flip = False
        obj.Invert = False
        obj.IncludeAnchor = False
        obj.Rotation = 0.0
        obj.OffsetX = 0.0
        obj.OffsetY = 0.0

        # Cache a "needs recompute" flag which should let us update width/height/rotation
        # using mouse dragging without triggering an expensive SVG recomputation. The SVG
        # only needs to be recomputed when a "real" change happens; the transformations
        # are applied by the parent SvgPage.
        self.needsRecompute = False

    def execute(self, obj):
        if not self.needsRecompute or not obj.Cutout:
            return

        from shaper_cutout_svg import SvgData
        svg_data = SvgData(obj.Cutout, not obj.Flip, obj.Invert)
        bb = svg_data.bounding_box

        obj.Svg_Anchor = f"{svg_data.anchor_path}"
        obj.Svg_Full = f"{svg_data.svg_paths()}"
        obj.Svg_Outline = f"{svg_data.outline_svg_path("#FA0")}"
        obj.Svg_BBCenter = bb.Center
        obj.Svg_BBLength = App.Vector(bb.XLength, bb.YLength, bb.ZLength)
        self.needsRecompute = False

    def onChanged(self, obj, prop):
        if prop == 'Type':
            return
        if prop == 'IncludeAnchor' and obj.IncludeAnchor:
            # Find parent ShaperSvgPage(s) and disable anchor on other images
            for parent in obj.InList:
                if getattr(parent, 'Type', None) == 'ShaperSvgPage':
                    for child in parent.Group:
                        if (getattr(child, 'Type', None) == 'ShaperSvgImage'
                                and child != obj):
                            child.IncludeAnchor = False

        if prop in ('OffsetX', 'OffsetY', 'Rotation'):
            for parent in obj.InList:
                if getattr(parent, 'Type', None) == 'ShaperSvgPage':
                    parent.touch()
        else:
            self.needsRecompute = True

    def addSvgProperties(self, obj):
        if not hasattr(obj, 'IncludeAnchor'):
            obj.addProperty('App::PropertyBool', 'IncludeAnchor', 'Base',
                            'Include the anchor point in the SVG rendering.')
            obj.IncludeAnchor = False

        if not hasattr(obj, 'Svg_Anchor'):
            obj.addProperty('App::PropertyString', 'Svg_Anchor', 'Svg',
                            'The SVG of the custom anchor added to the face.')
            obj.setPropertyStatus('Svg_Anchor', 2)
            obj.Svg_Anchor = ''
        if not hasattr(obj, 'Svg_Full'):
            obj.addProperty('App::PropertyString', 'Svg_Full', 'Svg',
                            'The SVG of the face as it would be export, excluding its anchor.')
            obj.setPropertyStatus('Svg_Full', 2)
            obj.Svg_Full = ''
        if not hasattr(obj, 'Svg_Outline'):
            obj.addProperty('App::PropertyString', 'Svg_Outline', 'Svg',
                            'The SVG of the outline of face.')
            obj.setPropertyStatus('Svg_Outline', 2)
            obj.Svg_Outline = ''
        if not hasattr(obj, 'Svg_BBCenter'):
            obj.addProperty('App::PropertyVector', 'Svg_BBCenter', 'Svg',
                            'The center of the bounding box of the SVG.')
            obj.setPropertyStatus('Svg_BBCenter', 2)
        if not hasattr(obj, 'Svg_BBLength'):
            obj.addProperty('App::PropertyVector', 'Svg_BBLength', 'Svg',
                            'A vector representing the size of the bounding box of the SVG.')
            obj.setPropertyStatus('Svg_BBLength', 2)

    def onDocumentRestored(self, obj):
        self.addSvgProperties(obj)

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
        return os.path.join(_ICON_ROOT, "svg-image.svg")

    def dumps(self):
        return None

    def loads(self, state):
        return None
