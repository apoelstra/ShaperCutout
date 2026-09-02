# SPDX-License-Identifier: GPL-3.0-or-later

import os

import FreeCAD as App
import Part

from shaper_cutout_util import _ICON_ROOT

# The user-facing enum labels, and their mapping to Shaper `cutType` attribute values.
# (The Shaper SVG spec spells the "on line" value `onLine`.)
OPEN_WIRE_TYPES = ['guide', 'on line']
CLOSED_WIRE_TYPES = ['guide', 'on line', 'inside', 'outside']
_CUT_TYPE_SVG = {
    'guide': 'guide',
    'on line': 'onLine',
    'inside': 'inside',
    'outside': 'outside',
}


def create(page, source, name):
    doc = page.Document
    obj = doc.addObject('App::FeaturePython', name)
    obj.Label = name
    ShaperSvgShape(obj)
    if App.GuiUp:
        ViewProviderShaperSvgShape(obj.ViewObject)
    page.addObject(obj)
    obj.Source = source
    doc.recompute()
    return obj


class ShaperSvgShape:
    """A ShaperSvgPage child which renders an arbitrary shape (a sketch, a Draft
    object, or any object with a 2D Shape) directly on the page.

    Unlike ShaperSvgImage, which renders a ShaperCutout's face, this simply
    projects the Source object's wires onto its own local plane (the "attachment
    plane"). At default Rotation the object appears on the page in the same
    orientation as it appears on that plane, with (0, 0) at the page's bottom
    left corner.
    """

    def __init__(self, obj):
        obj.Proxy = self

        obj.addProperty('App::PropertyString', 'Type', 'Internal',
                        'Type ID used to identify instances')
        obj.addProperty('App::PropertyLink', 'Source', 'Base',
                        'The sketch / Draft object (or anything with a 2D shape) to render.')
        obj.addProperty('App::PropertyAngle', 'Rotation', 'Base',
                        'Rotation about the shape bounding box center (degrees).')
        obj.addProperty('App::PropertyDistance', 'OffsetX', 'Base',
                        'X offset from page bottom-left to shape bottom-left (mm).')
        obj.addProperty('App::PropertyDistance', 'OffsetY', 'Base',
                        'Y offset from page bottom-left to shape bottom-left (mm).')

        obj.addProperty('App::PropertyBool', 'CutDepthEnabled', 'Cut',
                        'Whether to include a cut depth in the exported SVG.')
        obj.addProperty('App::PropertyLength', 'CutDepth', 'Cut',
                        'The cut depth used when Cut Depth is enabled.')
        obj.addProperty('App::PropertyEnumeration', 'OpenWireType', 'Cut',
                        'How to treat open wires: guide lines, or cut on the line.')
        obj.addProperty('App::PropertyEnumeration', 'ClosedWireType', 'Cut',
                        'How to treat closed wires: guide, on line, inside, or outside.')

        obj.addProperty('App::PropertyString', 'Svg_Full', 'Svg',
                        'The SVG paths of this shape as rendered on the page.')
        obj.addProperty('App::PropertyVector', 'Svg_BBCenter', 'Svg',
                        'The center of the bounding box of the SVG.')
        obj.addProperty('App::PropertyVector', 'Svg_BBLength', 'Svg',
                        'A vector representing the size of the bounding box of the SVG.')
        obj.setPropertyStatus('Svg_Full', 2)
        obj.setPropertyStatus('Svg_BBCenter', 2)
        obj.setPropertyStatus('Svg_BBLength', 2)

        obj.Type = 'ShaperSvgShape'
        obj.Rotation = 0.0
        obj.OffsetX = 0.0
        obj.OffsetY = 0.0
        obj.CutDepthEnabled = False
        obj.CutDepth = '1/4 in'
        obj.OpenWireType = OPEN_WIRE_TYPES
        obj.OpenWireType = 'guide'
        obj.ClosedWireType = CLOSED_WIRE_TYPES
        obj.ClosedWireType = 'outside'

    def onChanged(self, obj, prop):
        if prop == 'Type' or prop.startswith('Svg_'):
            return

        if prop in ('OffsetX', 'OffsetY', 'Rotation'):
            # Like ShaperSvgImage, touch the page so property-editor changes
            # repaint the page view; the SVG paths themselves don't change
            # (and dragging the page widget never touches this object).
            for parent in obj.InList:
                if getattr(parent, 'Type', None) == 'ShaperSvgPage':
                    parent.touch()

    def execute(self, obj):
        # We get recomputed when any of our own properties change and, via the
        # Source link dependency, whenever the source object recomputes; in the
        # latter case we must re-project even though none of our properties
        # changed. This is cheap (projection + path string formatting; no
        # booleans like a full SvgData run), and dragging never reaches here.
        if not obj.Source:
            return

        self._recompute_svg(obj)

        # Our paths changed; refresh any open page widgets. (The page may have
        # already been recomputed before us this pass, so touching it isn't
        # enough.)
        if App.GuiUp:
            for parent in obj.InList:
                if (getattr(parent, 'Type', None) == 'ShaperSvgPage'
                        and parent.ViewObject and parent.ViewObject.Proxy):
                    parent.ViewObject.Proxy.update_widget_svg()

    def _recompute_svg(self, obj):
        from shaper_cutout_svg.misc import wire_to_svg

        shape = getattr(obj.Source, 'Shape', None)
        if shape is None or shape.isNull():
            obj.Svg_Full = ''
            return

        # Map the shape onto its local plane (z ~= 0), then rotate 180 degrees
        # around the Y axis. That rotation is equivalent to mirroring x, which
        # undoes the mirroring caused by SVG's y-axis pointing down, so the
        # shape appears on the page (and in exported SVGs) in the same
        # orientation as viewed normally from the front of its attachment plane
        # (matching how SvgData renders ShaperSvgImages).
        m = shape.Placement.toMatrix().inverse()
        local = shape.transformed(m)
        flip_180_y = App.Matrix(-1, 0, 0, 0,
                                0, 1, 0, 0,
                                0, 0, -1, 0,
                                0, 0, 0, 1)
        local = local.transformed(flip_180_y)

        depth_attr = ''
        if obj.CutDepthEnabled:
            depth_attr = f' shaper:cutDepth="{obj.CutDepth.Value:.4f}mm"'

        paths = []
        for w in local.Wires:
            if w.isClosed():
                cut_type = obj.ClosedWireType
            else:
                cut_type = obj.OpenWireType

            cut_type_svg = _CUT_TYPE_SVG[cut_type]
            if cut_type == 'guide':
                fill, stroke = 'none', 'blue'
            elif cut_type == 'on line':
                fill, stroke = 'none', 'black'
            else:  # inside / outside
                fill, stroke = 'white', 'black'

            elem = wire_to_svg(w, fill, stroke, cut_type_svg, depth_attr)
            if elem:
                paths.append(elem)

        obj.Svg_Full = "\n".join(paths)
        bb = local.BoundBox
        obj.Svg_BBCenter = bb.Center
        obj.Svg_BBLength = App.Vector(bb.XLength, bb.YLength, bb.ZLength)

    def dumps(self):
        return None

    def loads(self, state):
        return None

    def centerXY(self, obj: App.DocumentObject) -> (float, float):
        return (obj.Svg_BBCenter.x, obj.Svg_BBCenter.y)

    def translateXY(self, obj, page_h: float) -> (float, float):
        return (
            obj.OffsetX.Value - obj.Svg_BBCenter.x + obj.Svg_BBLength.x / 2,
            page_h - obj.Svg_BBCenter.y - obj.Svg_BBLength.y / 2 - obj.OffsetY.Value,
        )


class ViewProviderShaperSvgShape:
    def __init__(self, vobj):
        vobj.Proxy = self

    def attach(self, vobj):
        self._vobj = vobj

    def getIcon(self):
        return os.path.join(_ICON_ROOT, "svg-shape.svg")

    def claimChildren(self):
        return [self._vobj.Object.Source]

    def doubleClicked(self, vobj):
        from shaper_cutout_command.edit_shaper_svg_shape import open_shape_task_panel
        open_shape_task_panel(vobj.Object)
        return True

    def setupContextMenu(self, vobj, menu):
        from shaper_cutout_command.edit_shaper_svg_shape import open_shape_task_panel
        action = menu.addAction("Edit SVG Shape")
        action.triggered.connect(lambda: open_shape_task_panel(vobj.Object))

    def getDisplayModes(self, obj):
        return []

    def getDefaultDisplayMode(self):
        return "Shaded"

    def setDisplayMode(self, mode):
        return mode

    def onChanged(self, vp, prop):
        pass

    def dumps(self):
        return None

    def loads(self, state):
        return None
