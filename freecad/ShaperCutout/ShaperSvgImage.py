# SPDX-License-Identifier: GPL-3.0-or-later

import os

import FreeCAD as App
import Part

from shaper_cutout_svg import HIGHLIGHT_COLOR
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
        obj.Rotation = 0.0
        obj.OffsetX = 0.0
        obj.OffsetY = 0.0

        # Cache a "needs recompute" flag which should let us update width/height/rotation
        # using mouse dragging without triggering an expensive SVG recomputation. The SVG
        # only needs to be recomputed when a "real" change happens; the transformations
        # are applied by the parent SvgPage.
        self.needsRecompute = False

    def _clear_svg(self, obj):
        """Reset all rendered-SVG outputs (used when the cutout is gone)."""
        obj.Svg_Full = ''
        if hasattr(obj, 'Svg_Outline'):
            obj.Svg_Outline = ''
        obj.Svg_BBCenter = App.Vector(0, 0, 0)
        obj.Svg_BBLength = App.Vector(0, 0, 0)
        if hasattr(obj, 'Svg_TranslatedFace'):
            obj.Svg_TranslatedFace = Part.Shape()

    def execute(self, obj):
        if not obj.Cutout:
            # The cutout was deleted; don't keep rendering (and exporting)
            # the stale face geometry from before the deletion.
            self._clear_svg(obj)
            return
        if not self.needsRecompute:
            return

        from shaper_cutout_svg import SvgData
        svg_data = SvgData(obj.Cutout, not obj.Flip, obj.Invert)
        bb = svg_data.bounding_box

        obj.Svg_Full = f"{svg_data.svg_paths()}"
        obj.Svg_Outline = f"{svg_data.outline_svg_path(HIGHLIGHT_COLOR)}"
        obj.Svg_BBCenter = bb.Center
        obj.Svg_BBLength = App.Vector(bb.XLength, bb.YLength, bb.ZLength)

        # Cache translated face for overlap detection
        if svg_data.translated_face:
            obj.Svg_TranslatedFace = svg_data.translated_face

        self.needsRecompute = False

    def onChanged(self, obj, prop):
        if prop == 'Type':
            return
        if prop in ('OffsetX', 'OffsetY', 'Rotation'):
            for parent in obj.InList:
                if getattr(parent, 'Type', None) == 'ShaperSvgPage':
                    parent.touch()
        else:
            self.needsRecompute = True

    def addSvgProperties(self, obj):
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
        if not hasattr(obj, 'Svg_TranslatedFace'):
            obj.addProperty('Part::PropertyPartShape', 'Svg_TranslatedFace', 'Svg',
                            'Translated cutout face for overlap detection.')
            obj.setPropertyStatus('Svg_TranslatedFace', 2)

    def onDocumentRestored(self, obj):
        missing_face = (not hasattr(obj, 'Svg_TranslatedFace')
                        or obj.Svg_TranslatedFace.isNull())
        self.addSvgProperties(obj)
        if missing_face and obj.Cutout:
            # Svg_TranslatedFace (used for overlap detection and the page's
            # anchor algorithm) was added after this document was saved;
            # recompute once to populate it.
            self.needsRecompute = True
            obj.touch()

    def dumps(self):
        return None

    def loads(self, state):
        return None

    def centerXY(self, obj: App.DocumentObject) -> (float, float):
        return (obj.Svg_BBCenter.x, obj.Svg_BBCenter.y)

    def anchor_wires(self, obj: App.DocumentObject) -> ([Part.Wire], [Part.Wire]):
        """Return (outer_wires, inner_wires) of the cutout face in this image's
        local Svg space, for the page's custom-anchor algorithm."""
        from shaper_cutout_svg import classify_wires

        if not hasattr(obj, 'Svg_TranslatedFace') or obj.Svg_TranslatedFace.isNull():
            return [], []
        return classify_wires(obj.Svg_TranslatedFace)

    def snap_wires(self, obj: App.DocumentObject) -> [Part.Wire]:
        """All wires in this image's local Svg space, for the page's
        interactive anchor-placement snapping."""
        if not hasattr(obj, 'Svg_TranslatedFace') or obj.Svg_TranslatedFace.isNull():
            return []
        return list(obj.Svg_TranslatedFace.Wires)

    def translateXY(self, obj, page_h: float) -> (float, float):
        return (
            obj.OffsetX.Value - obj.Svg_BBCenter.x + obj.Svg_BBLength.x / 2,
            page_h - obj.Svg_BBCenter.y - obj.Svg_BBLength.y / 2 - obj.OffsetY.Value,
        )


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
