# SPDX-License-Identifier: GPL-3.0-or-later

import os
import math
from typing import List, Tuple

import FreeCAD as App
import FreeCADGui as Gui
import Part
from PySide import QtCore, QtGui, QtWidgets, QtSvg

from shaper_cutout_svg import SvgAnchorFrame, SvgAnchorPlacerAction, SvgAnchorPlacerMode, \
        SvgAnchorPlacer
from shaper_cutout_util import _ICON_ROOT
import ShaperSvgImage
import ShaperSvgShape


# Object types that can live in a ShaperSvgPage's Group.
_PAGE_CHILD_TYPES = ('ShaperSvgImage', 'ShaperSvgShape')


def _is_page_child(obj) -> bool:
    return getattr(obj, 'Type', '') in _PAGE_CHILD_TYPES


def _same_segment(s1, s2, tol: float = 1e-6) -> bool:
    """True if the two (p0, p1) segments have the same endpoints (either direction)."""
    return (((s1[0] - s2[0]).Length < tol and (s1[1] - s2[1]).Length < tol)
            or ((s1[0] - s2[1]).Length < tol and (s1[1] - s2[0]).Length < tol))


def _clip_line_to_rect(p: App.Vector, d: App.Vector, w: float, h: float):
    """Clip the infinite line p + t*d to the rectangle [0, w] x [0, h].
    Returns two App.Vectors, or None if the line misses the rectangle."""
    tmin, tmax = -1e18, 1e18
    for lo, hi, o, dd in ((0, w, p.x, d.x), (0, h, p.y, d.y)):
        if abs(dd) < 1e-12:
            if o < lo or o > hi:
                return None
            continue
        t1, t2 = (lo - o) / dd, (hi - o) / dd
        if t1 > t2:
            t1, t2 = t2, t1
        tmin, tmax = max(tmin, t1), min(tmax, t2)
        if tmin > tmax:
            return None
    if tmin >= tmax or tmin <= -1e17 and tmax >= 1e17:
        return None
    return (p + d * tmin, p + d * tmax)


def create(name="ShaperSvgPage"):
    doc = App.ActiveDocument
    doc.openTransaction("create Shaper SVG page")
    obj = doc.addObject('App::DocumentObjectGroupPython', name)
    obj.Label = name
    ShaperSvgPage(obj)
    if App.GuiUp:
        ViewProviderShaperSvgPage(obj.ViewObject)
    doc.recompute()
    doc.commitTransaction()
    return obj


def page_view_metrics(widget_w, widget_h, page_w_mm, page_h_mm, grid_mm):
    # Minimum padding so the viewport has a GUI border. One of the `pad_x`/`pad_y` padding
    # values will be equal to this; the other may be larger.
    min_pad = 2
    if page_w_mm <= 0 or page_h_mm <= 0 or grid_mm <= 0 \
            or widget_w < 2 * min_pad or widget_h < 2 * min_pad:
        # grid_mm == 0 is reachable (the property accepts it, e.g. via the
        # property editor) and makes grid_px -- the px/mm scale for every
        # mouse mapping -- zero, so treat it as degenerate like the others.
        return None

    # Determine padding, available viewport space, and grid size, all in pixels
    page_ar = page_w_mm / page_h_mm
    view_ar = widget_w / widget_h
    if page_ar > view_ar:
        # Page is width-limited
        avail_w = widget_w - 2 * min_pad
        avail_h = avail_w / page_ar
        pad_x = min_pad
        pad_y = (widget_h - avail_h) / 2.0
        grid_px = grid_mm * avail_w / page_w_mm
    else:
        # Page is height-limited
        avail_h = widget_h - 2 * min_pad
        avail_w = avail_h * page_ar
        pad_y = min_pad
        pad_x = (widget_w - avail_w) / 2.0
        grid_px = grid_mm * avail_h / page_h_mm

    return pad_x, pad_y, grid_px, avail_w, avail_h


class ShaperSvgPage:
    def __init__(self, obj):
        obj.Proxy = self

        obj.addProperty('App::PropertyString', 'Type', 'Internal',
                        'Type ID used to identify instances')
        obj.addProperty('App::PropertyLength', 'Width', 'Base',
                        'Page width')
        obj.addProperty('App::PropertyLength', 'Height', 'Base',
                        'Page height')
        obj.addProperty('App::PropertyLength', 'GridSpacing', 'Base',
                        'Grid spacing for the page view')
        obj.addProperty('App::PropertyBool', 'HasAnchor', 'Base',
                        'Whether to include a custom anchor in the page SVG.')
        obj.addProperty('App::PropertyDistance', 'AnchorX', 'Anchor',
                        'X position of the custom anchor origin, mm from the '
                        'page left edge.')
        obj.addProperty('App::PropertyDistance', 'AnchorY', 'Anchor',
                        'Y position of the custom anchor origin, mm from the '
                        'page top edge (SVG coordinates).')
        obj.addProperty('App::PropertyAngle', 'AnchorRotation', 'Anchor',
                        'Angle of the anchor long leg in degrees (same sense '
                        'as SVG rotate: clockwise on the page).')
        obj.addProperty('App::PropertyBool', 'AnchorMirror', 'Anchor',
                        'Mirror the anchor short leg to the other side of the long leg.')

        self.addDisplayProperties(obj)

        obj.Type = 'ShaperSvgPage'
        obj.Width = '8 ft'
        obj.Height = '4 ft'
        obj.GridSpacing = '1 in'
        obj.HasAnchor = False
        obj.ShowOverlaps = True
        obj.ShowMinDistances = True

    def addDisplayProperties(self, obj):
        if not hasattr(obj, 'ShowOverlaps'):
            obj.addProperty('App::PropertyBool', 'ShowOverlaps', 'View',
                            'Whether to show overlap highlights between images. '
                            'May be slow on complex pages.')
            obj.ShowOverlaps = True
        if not hasattr(obj, 'ShowMinDistances'):
            obj.addProperty('App::PropertyBool', 'ShowMinDistances', 'View',
                            'Whether to show minimum distance lines between images. '
                            'May be slow on complex pages.')
            obj.ShowMinDistances = True

    def onChanged(self, obj, prop):
        if prop == 'Group':
            for child in list(obj.Group):
                if getattr(child, 'Type', None) not in _PAGE_CHILD_TYPES:
                    obj.removeObject(child)

        if obj.ViewObject and obj.ViewObject.Proxy:
            obj.ViewObject.Proxy.update_widget_svg()

    def execute(self, obj):
        if obj.ViewObject and obj.ViewObject.Proxy:
            obj.ViewObject.Proxy.update_widget_svg()
        pass

    def dumps(self):
        return None

    def loads(self, state):
        return None

    def onDocumentRestored(self, obj):
        if hasattr(obj, 'zzSvg'):
            obj.removeProperty('zzSvg')
        if hasattr(obj, 'Svg'):
            obj.removeProperty('Svg')

        # The old "IncludeAnchor" and "Svg_Anchor" properties of images should just be dropped.
        # They were booleans that would trigger a complicated since-deleted auto-placement
        # algorithm, and had complicated logic to prevent multiple anchors in one page. Now
        # the anchor is placed in the Page (not Image) and the user has to choose where.
        for child in obj.Group:
            for prop in ('IncludeAnchor', 'Svg_Anchor'):
                if hasattr(child, prop):
                    child.removeProperty(prop)
        if not hasattr(obj, 'HasAnchor'):
            obj.addProperty('App::PropertyBool', 'HasAnchor', 'Base',
                            'Whether to include a custom anchor in the page SVG.')
            obj.HasAnchor = False
        for prop, ptype, group, doc in (
                ('AnchorX', 'App::PropertyDistance', 'Anchor',
                 'X position of the custom anchor origin, mm from the '
                 'page left edge.'),
                ('AnchorY', 'App::PropertyDistance', 'Anchor',
                 'Y position of the custom anchor origin, mm from the '
                 'page top edge (SVG coordinates).'),
                ('AnchorRotation', 'App::PropertyAngle', 'Anchor',
                 'Angle of the anchor long leg in degrees (same sense '
                 'as SVG rotate: clockwise on the page).'),
                ('AnchorMirror', 'App::PropertyBool', 'Anchor',
                 'Mirror the anchor short leg to the other side of the long leg.')):
            if not hasattr(obj, prop):
                obj.addProperty(ptype, prop, group, doc)
                setattr(obj, prop, False if ptype == 'App::PropertyBool' else 0.0)

        self.addDisplayProperties(obj)

    def _svg_to_page_matrix(self, obj: App.DocumentObject, child) -> App.Matrix:
        """The matrix mapping a child's local Svg space into page space."""
        cx, cy = child.Proxy.centerXY(child)
        tx, ty = child.Proxy.translateXY(child, obj.Height.Value)
        return App.Placement(App.Vector(tx, ty, 0),
                             App.Rotation(App.Vector(0, 0, 1), child.Rotation.Value + 180),
                             App.Vector(cx, cy, 0)).toMatrix()

    # ------------------------------------------------------------------
    # Anchor support
    # ------------------------------------------------------------------
    def _collect_snap_wires(self, obj: App.DocumentObject) -> List[Part.Wire]:
        """All wires (open ones included) of all page children, in page space,
        for interactive anchor-placement snapping."""
        wires: List[Part.Wire] = []
        for c in obj.Group:
            if hasattr(c.Proxy, 'snap_wires'):
                child_wires = c.Proxy.snap_wires(c)
            elif hasattr(c.Proxy, 'anchor_wires'):
                child_wires = sum(c.Proxy.anchor_wires(c), [])
            else:
                continue
            m = self._svg_to_page_matrix(obj, c)
            wires.extend(w.transformed(m) for w in child_wires)
        return wires

    def set_anchor_frame(self, obj: App.DocumentObject, frame: SvgAnchorFrame):
        """Store an anchor in page space."""
        obj.AnchorX = frame.vertex.x
        obj.AnchorY = frame.vertex.y
        long_dir = frame.long_dir()
        short_dir = frame.short_dir()
        obj.AnchorRotation = math.degrees(math.atan2(long_dir.y, long_dir.x))
        ccw = App.Vector(-long_dir.y, long_dir.x, 0)
        obj.AnchorMirror = short_dir.dot(ccw) < 0
        obj.HasAnchor = True

    def anchor_triangle(self, obj: App.DocumentObject):
        """The anchor triangle wire in page space, per the stored properties."""
        r = math.radians(obj.AnchorRotation.Value)
        long_dir = App.Vector(math.cos(r), math.sin(r), 0)
        if getattr(obj, 'AnchorMirror', False):
            short_dir = App.Vector(long_dir.y, -long_dir.x, 0)
        else:
            short_dir = App.Vector(-long_dir.y, long_dir.x, 0)
        return SvgAnchorFrame(
            App.Vector(obj.AnchorX.Value, obj.AnchorY.Value, 0),
            long_dir,
            short_dir
        ).triangle_wire()

    def compute_svg(self, obj):
        page_w = obj.Width.Value
        page_h = obj.Height.Value

        svg = f'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg"
     xmlns:shaper="http://www.shapertools.com/namespaces/shaper"
     viewBox="0 0 {page_w:.4f} {page_h:.4f}"
     width="{page_w:.4f}mm" height="{page_h:.4f}mm">
  <rect x="0" y="0"
        width="{page_w:.4f}" height="{page_h:.4f}"
        fill="none" stroke="blue" stroke-width="2"
        shaper:cutType="guide" />
'''

        if App.GuiUp:
            selected = [s for s in Gui.Selection.getSelection()
                        if _is_page_child(s) and s in obj.Group]
        else:
            selected = []

        # Render each ShaperSvgImage child
        for child in obj.Group:
            if not hasattr(child, 'Svg_BBCenter'):
                continue
            if child in selected:
                # We will draw selected children below, so they're on top
                continue

            cx, cy = child.Proxy.centerXY(child)
            tx, ty = child.Proxy.translateXY(child, page_h)
            rot = child.Rotation.Value + 180

            g = f'<g transform="translate({tx:.4f},{ty:.4f}) rotate({rot:.4f},{cx:.4f},{cy:.4f})">'
            if hasattr(child, 'Svg_Full'):
                svg += f'{g}{child.Svg_Full}</g>'

        for child in selected:
            if not hasattr(child, 'Svg_BBCenter'):
                continue

            cx, cy = child.Proxy.centerXY(child)
            tx, ty = child.Proxy.translateXY(child, page_h)
            rot = child.Rotation.Value + 180

            g = f'<g transform="translate({tx:.4f},{ty:.4f}) rotate({rot:.4f},{cx:.4f},{cy:.4f})">'
            if hasattr(child, 'Svg_Full'):
                svg += f'{g}{child.Svg_Full}</g>'
            if hasattr(child, 'Svg_Outline'):
                svg += f'{g}{child.Svg_Outline}</g>'

        if getattr(obj, 'HasAnchor', False):
            from shaper_cutout_svg import wire_to_svg
            svg += wire_to_svg(self.anchor_triangle(obj),
                               fill="red", stroke="none", stroke_width=None)

        svg += "</svg>"
        return svg

    def compute_overlaps(self, obj: App.DocumentObject):
        """Compute overlaps and close distances between images. Returns list of overlap data."""
        if getattr(self, '_is_dragging', False):
            return [], []

        if not getattr(obj, 'ShowOverlaps', True) \
                and not getattr(obj, 'ShowMinDistances', True):
            return [], []

        images = [child for child in obj.Group
                  if getattr(child, 'Type', '') == 'ShaperSvgImage'
                  and hasattr(child, 'Svg_TranslatedFace')
                  and not child.Svg_TranslatedFace.isNull()]

        overlaps = []
        close_pairs = []

        for i, img1 in enumerate(images):
            for img2 in images[i+1:]:
                face1 = img1.Svg_TranslatedFace.transformed(self._svg_to_page_matrix(obj, img1))
                face2 = img2.Svg_TranslatedFace.transformed(self._svg_to_page_matrix(obj, img2))

                # Check for overlap
                bb1 = face1.BoundBox
                bb2 = face2.BoundBox
                if bb2.intersect(bb1):
                    common = face1.common(face2)
                    if not common.isNull() and common.Area > 0:
                        overlaps.append((img1, img2, common))
                        continue

                # If no overlap, check for close distance
                # distToShape returns three objects -- a minimum distance then a list of
                # (Vector, Vector) pairs where the two vectors are endpoints of min-dist
                # lines. Note the list only has more than one entry when the closest
                # features happen to be parallel on both ends of the gap (axis-aligned
                # placements); a rotated shape has a single unique closest pair, so we
                # must accept len(pairs) >= 1 here.
                dist, pairs, _ = face1.distToShape(face2)
                if dist < 50.0 and len(pairs) >= 1:  # 50mm threshold
                    pt1 = pairs[0][0]
                    pt2 = pairs[0][1]
                    dist = App.Units.Quantity(f"{dist} mm")
                    close_pairs.append((img1, img2, dist, pt1, pt2))

        return overlaps, close_pairs


class _PageWidget(QtWidgets.QWidget):
    closed = QtCore.Signal()

    def __init__(self, page_obj, parent=None):
        super().__init__(parent)
        self._page_obj = page_obj
        self._svg = ''
        self._overlaps = []
        self._close_pairs = []
        self.setMinimumSize(200, 100)
        self.setMouseTracking(True)
        self.setFocusPolicy(QtCore.Qt.ClickFocus)
        self._dragging = []
        self._drag_start = None
        self._drag_orig_offset = None
        self._anchor_placement = None

        # Setup timer to handle expensive overlap checks.
        self._compute_overlap_timer = QtCore.QTimer()
        self._compute_overlap_timer.setSingleShot(True)
        self._compute_overlap_timer.timeout.connect(self._compute_overlap_timeout)
        self._compute_overlap_timer.setInterval(1000)
        # Manually trigger 'compute overlaps'. Later in self.update_svg it will be triggered by
        # self._compute_overlap_timer.start() (which will reset the timer if it's already in
        # progress, preventing updates from stalling the GUI while the user is moving stuff).
        self._compute_overlap_timeout()

    # ------------------------------------------------------------------
    # Custom anchor interactive placement
    # ------------------------------------------------------------------
    def start_anchor_placement(self, obj: App.DocumentObject, mode: SvgAnchorPlacerMode):
        """Enter interactive anchor placement mode ('vertex' or 'intersection')."""
        self._anchor_placement = SvgAnchorPlacer(mode)
        self.setCursor(QtCore.Qt.CrossCursor)
        self.update()

    def _cancel_anchor_placement(self):
        self._anchor_placement = None
        self.unsetCursor()
        self.update()

    def _mm_pos(self, pos):
        """Convert a widget position to page (SVG) coordinates in mm."""
        metrics = self._get_page_metrics()
        if not metrics:
            return None
        pad_x, pad_y, grid_px, _, _ = metrics
        grid_mm = self._page_obj.GridSpacing.Value
        return App.Vector((pos.x() - pad_x) / grid_px * grid_mm,
                          (pos.y() - pad_y) / grid_px * grid_mm, 0)

    def _update_anchor_preview(self, mm_pt):
        """Recompute hover-dependent anchor placement state for a page-space point."""
        st = self._anchor_placement
        if st is None:
            return
        obj = self._page_obj
        tol_px = 8.0
        metrics = self._get_page_metrics()
        if metrics:
            tol_mm = tol_px * obj.GridSpacing.Value / metrics[2]
        else:
            tol_mm = 8.0

        st.set_page_data(obj.Width, obj.Height, self._page_obj.Proxy._collect_snap_wires(obj))
        st.update_anchor_preview(mm_pt, tol_mm)

    def _apply_anchor(self):
        """Store the placed anchor in the document (undoable) and leave the mode."""
        frame = self._anchor_placement.frame()
        self._anchor_placement = None
        self.unsetCursor()
        self.update_svg()

        self._page_obj.Document.openTransaction("Place custom anchor")
        try:
            self._page_obj.Proxy.set_anchor_frame(self._page_obj, frame)
        except Exception:
            self._page_obj.Document.abortTransaction()
            raise

    def _draw_anchor_placement(self, painter, metrics):
        """Overlay for the interactive anchor placement mode."""
        pad_x, pad_y, grid_px, avail_w, avail_h = metrics
        obj = self._page_obj
        ratio = grid_px / obj.GridSpacing.Value
        page_w, page_h = obj.Width.Value, obj.Height.Value
        st = self._anchor_placement

        def to_px(p):
            return QtCore.QPointF(pad_x + p.x * ratio, pad_y + p.y * ratio)

        def draw_extended(p, d, color, dash):
            """Draw the infinite line through p along d, clipped to the page."""
            pts = _clip_line_to_rect(p, d, page_w, page_h)
            if not pts:
                return
            pen = QtGui.QPen(color, 1.5)
            pen.setStyle(QtCore.Qt.DashLine if dash else QtCore.Qt.SolidLine)
            painter.setPen(pen)
            painter.drawLine(to_px(pts[0]), to_px(pts[1]))

        if st.seg1() is not None:
            p0, p1 = st.seg1()
            draw_extended(p0, p1 - p0, QtGui.QColor('blue'), True)
        if st.hover_seg() is not None:
            p0, p1 = st.hover_seg()
            if st.mode == SvgAnchorPlacerMode.INTERSECTION and st.seg1() is not None:
                color = QtGui.QColor('green') if st.ortho() else QtGui.QColor('red')
            else:
                color = QtGui.QColor('blue')
            draw_extended(p0, p1 - p0, color, True)

        frame = self._anchor_placement.frame()
        if frame is not None:
            long_dir = frame.long_dir()
            short_dir = frame.short_dir()
            grey = QtGui.QColor(128, 128, 128, 160)
            draw_extended(frame.vertex, long_dir, grey, True)
            draw_extended(frame.vertex, short_dir, grey, True)

            tri = frame.triangle_wire(scale=3.0)
            self._draw_shape(painter, tri, pad_x, pad_y, ratio,
                             QtGui.QColor(255, 0, 0, 128))

        if st.mode == SvgAnchorPlacerMode.VERTEX and st.hover_pt() is not None:
            p = st.hover_pt()
            painter.setPen(QtGui.QPen(QtGui.QColor('blue'), 1.5))
            painter.setBrush(QtCore.Qt.NoBrush)
            painter.drawEllipse(to_px(p), 5, 5)

    def update_svg(self):
        obj = self._page_obj
        self._svg = obj.Proxy.compute_svg(obj)
        self.update()

        self._compute_overlap_timer.start()

    def _compute_overlap_timeout(self):
        self._overlaps, self._close_pairs = self._page_obj.Proxy.compute_overlaps(self._page_obj)
        self._svg = self._page_obj.Proxy.compute_svg(self._page_obj)
        self.update()

    def _get_page_metrics(self) -> Tuple[float, float, float, float, float, float, float]:
        """Computes various properties of the display window for the SVG.

        Returns `pad_x`, `pad_y`, `grid_px`, `avail_w`, `avail_h`.

        With `grid_mm` equal to `self._page_obj.GridSpacing.Value`, this returns viewport dimensions
        (`avail_w`, `avail_h`) and padding (`pad_x`, `pad_y`) such that:

        * The actual viewport size is `avail_w + 2 * pad_x` by `avail_h + 2 * pad_y`
        * The grid squares are `grid_px` by `grid_px` (this value *will* be an integer); the aspect
          ratio `avail_w` / `avail_h` will match `self._page_obj.Width / self._page_obj.Height`.
        * The "pixel ratio" `grid_px / grid_mm` equals both `avail_w` / `self._page_obj.Width.Value`
          and `avail_h` / `self._page_obj.Height.Value`
        """
        return page_view_metrics(self.width(), self.height(),
                                 self._page_obj.Width.Value, self._page_obj.Height.Value,
                                 self._page_obj.GridSpacing.Value)

    def paintEvent(self, event):
        metrics = self._get_page_metrics()
        if not metrics:
            return
        pad_x, pad_y, grid_px, avail_w, avail_h = metrics

        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)

        # White page background
        painter.fillRect(QtCore.QRectF(pad_x, pad_y, avail_w, avail_h),
                         QtGui.QColor('white'))

        # Light grey grid
        if grid_px > 1:
            grid_w = math.floor(avail_w / grid_px)
            for x in range(grid_w):
                if x % 10 == 0:
                    painter.setPen(QtGui.QPen(QtGui.QColor(220, 120, 120), 0.5))
                else:
                    painter.setPen(QtGui.QPen(QtGui.QColor(220, 220, 220), 0.5))

                px = pad_x + x * grid_px
                painter.drawLine(QtCore.QPointF(px, pad_y),
                                 QtCore.QPointF(px, pad_y + avail_h))

            grid_h = math.floor(avail_h / grid_px)
            for y in range(grid_h):
                if y % 10 == 0:
                    painter.setPen(QtGui.QPen(QtGui.QColor(220, 120, 120), 0.5))
                else:
                    painter.setPen(QtGui.QPen(QtGui.QColor(220, 220, 220), 0.5))

                py = pad_y + y * grid_px
                painter.drawLine(QtCore.QPointF(pad_x, py),
                                 QtCore.QPointF(pad_x + avail_w, py))

        # SVG content
        main_renderer = QtSvg.QSvgRenderer()
        main_renderer.load(QtCore.QByteArray(self._svg.encode('utf-8')))
        if main_renderer.isValid():
            main_renderer.render(painter, QtCore.QRectF(pad_x, pad_y, avail_w, avail_h))

        # Draw overlap highlights in bright red (if enabled)
        grid_mm = self._page_obj.GridSpacing.Value
        grid_ratio = grid_px / grid_mm
        if getattr(self._page_obj, 'ShowOverlaps', True):
            for img1, _, common in self._overlaps:
                self._draw_shape(painter, common, pad_x, pad_y, grid_ratio,
                                 QtGui.QColor(255, 0, 0, 192))

        # Draw distance lines for close pairs (if enabled)
        if getattr(self._page_obj, 'ShowMinDistances', True):
            for img1, img2, dist, pt1, pt2 in self._close_pairs:
                self._draw_distance_line(painter, pt1, pt2, dist, pad_x, pad_y, grid_ratio)

        # Interactive anchor placement overlay
        if self._anchor_placement is not None:
            self._draw_anchor_placement(painter, metrics)

        painter.end()

    def _draw_shape(self, painter, shape, pad_x, pad_y, grid_ratio, color):
        """Draw a shape using QPainter."""
        for wire in shape.Wires:
            path = QtGui.QPainterPath()
            pts = wire.discretize(Deflection=0.5)  # Approximate with line segments
            if pts:
                path.moveTo(pad_x + pts[0].x * grid_ratio, pad_y + pts[0].y * grid_ratio)
                for pt in pts[1:]:
                    path.lineTo(pad_x + pt.x * grid_ratio, pad_y + pt.y * grid_ratio)

            painter.fillPath(path, QtGui.QBrush(color))

    def _draw_distance_line(
        self,
        painter: QtGui.QPainter,
        pt1: App.Vector,
        pt2: App.Vector,
        dist: App.Units.Quantity,
        pad_x: float,
        pad_y: float,
        grid_ratio: float,
    ):
        """Draw red line between closest points with distance label."""
        # Convert to widget coordinates
        x1 = pad_x + pt1.x * grid_ratio
        y1 = pad_y + pt1.y * grid_ratio
        x2 = pad_x + pt2.x * grid_ratio
        y2 = pad_y + pt2.y * grid_ratio

        pen = QtGui.QPen(QtGui.QColor('red'), 2)
        painter.setPen(pen)
        painter.drawLine(QtCore.QPointF(x1, y1), QtCore.QPointF(x2, y2))

        schema = App.Units.getSchema()
        dist = App.Units.schemaTranslate(dist, schema)[0]

        # Draw distance label at midpoint
        mid_x = (x1 + x2) / 2 + 2
        mid_y = (y1 + y2) / 2 + 2
        font = QtGui.QFont()
        font.setStyleHint(QtGui.QFont.SansSerif)
        font.setPixelSize(16)

        painter.setPen(QtGui.QColor('red'))
        painter.setFont(font)
        painter.drawText(QtCore.QPointF(mid_x, mid_y), f"{dist}")

    def _hit_test(self, pos):
        metrics = self._get_page_metrics()
        if not metrics:
            return None
        pad_x, pad_y, grid_px, _, _ = metrics

        grid_mm = self._page_obj.GridSpacing.Value
        page_h = self._page_obj.Height.Value
        pos_x_mm = (pos.x() - pad_x) / grid_px * grid_mm
        pos_y_mm = (pos.y() - pad_y) / grid_px * grid_mm

        selected = {s for s in Gui.Selection.getSelection()
                    if _is_page_child(s) and s in self._page_obj.Group}

        ordered = list(reversed(self._page_obj.Group))
        swap_idx = 0
        for i in range(len(ordered)):
            if i > swap_idx and ordered[i] in selected:
                ordered[swap_idx], ordered[i] = ordered[i], ordered[swap_idx]

        for child in ordered:
            if not _is_page_child(child):
                continue

            cx, cy = child.Proxy.centerXY(child)
            tx, ty = child.Proxy.translateXY(child, page_h)
            length = child.Svg_BBLength

            rot_rad = math.radians(child.Rotation.Value)
            cos_r = math.cos(rot_rad)
            sin_r = math.sin(rot_rad)

            xdist = tx + cx - pos_x_mm
            ydist = ty + cy - pos_y_mm
            xdist, ydist = (
                abs(xdist * cos_r + ydist * sin_r),
                abs(xdist * sin_r + ydist * cos_r),
            )

            if xdist < length.x / 2 and ydist < length.y / 2:
                return child

        return None

    def mousePressEvent(self, event):
        if self._anchor_placement is not None:
            if event.button() == QtCore.Qt.LeftButton:
                mm_pt = self._mm_pos(event.pos())
                if mm_pt is not None:
                    self._update_anchor_preview(mm_pt)
                    action = self._anchor_placement.on_click(mm_pt)
                    if action == SvgAnchorPlacerAction.CANCEL:
                        self._cancel_anchor_placement()
                        event.accept()
                        return
                    elif action == SvgAnchorPlacerAction.CONTINUE:
                        pass
                    elif action == SvgAnchorPlacerAction.APPLY:
                        self._apply_anchor()
                        event.accept()
                        return
                    else:
                        assert False
            elif event.button() == QtCore.Qt.RightButton:
                self._cancel_anchor_placement()
                event.accept()
            return

        if event.button() == QtCore.Qt.LeftButton:
            key_mods = QtWidgets.QApplication.keyboardModifiers()

            child = self._hit_test(event.pos())
            if child:
                if key_mods & QtCore.Qt.ShiftModifier == QtCore.Qt.ShiftModifier:
                    Gui.Selection.addSelection(child)
                elif key_mods & QtCore.Qt.ControlModifier == QtCore.Qt.ControlModifier:
                    if Gui.Selection.isSelected(child):
                        Gui.Selection.removeSelection(child)
                    else:
                        Gui.Selection.addSelection(child)
                else:
                    Gui.Selection.clearSelection()
                    Gui.Selection.addSelection(child)

                self._drag_start = event.pos()
                self._dragging = [(s, s.OffsetX.Value, s.OffsetY.Value)
                                  for s in Gui.Selection.getSelection()
                                  if _is_page_child(s) and s in self._page_obj.Group]
                self._page_obj.Proxy._is_dragging = True
                self._page_obj.Document.openTransaction("Move ShaperSvgImage")
                self.setCursor(QtCore.Qt.ClosedHandCursor)
            else:
                self._dragging = []
                if key_mods & (QtCore.Qt.ShiftModifier | QtCore.Qt.ControlModifier) \
                        == QtCore.Qt.NoModifier:
                    Gui.Selection.clearSelection()

    def mouseMoveEvent(self, event):
        if self._anchor_placement is not None:
            mm_pt = self._mm_pos(event.pos())
            if mm_pt is not None:
                self._update_anchor_preview(mm_pt)
                self.update()
            return

        if self._dragging:
            metrics = self._get_page_metrics()
            if not metrics:
                return
            _, _, grid_px, _, _ = metrics
            grid_mm = self._page_obj.GridSpacing.Value
            page_h = self._page_obj.Height.Value
            page_w = self._page_obj.Width.Value

            dx_px = event.pos().x() - self._drag_start.x()
            dy_px = event.pos().y() - self._drag_start.y()
            dx_mm = dx_px / grid_px * grid_mm
            dy_mm = -dy_px / grid_px * grid_mm

        for dragging, orig_offset_x, orig_offset_y in self._dragging:
            rot_rad = math.radians(dragging.Rotation.Value)
            cos_r = abs(math.cos(rot_rad))
            sin_r = abs(math.sin(rot_rad))
            w_rot = dragging.Svg_BBLength.x * cos_r + dragging.Svg_BBLength.y * sin_r
            h_rot = dragging.Svg_BBLength.x * sin_r + dragging.Svg_BBLength.y * cos_r

            min_x = w_rot / 2 - dragging.Svg_BBLength.x / 2
            max_x = page_w - w_rot / 2 - dragging.Svg_BBLength.x / 2
            min_y = h_rot / 2 - dragging.Svg_BBLength.y / 2
            max_y = page_h - h_rot / 2 - dragging.Svg_BBLength.y / 2

            new_x = orig_offset_x + dx_mm
            new_y = orig_offset_y + dy_mm

            if min_x > max_x:
                # Image too small, nothing we can do
                dx_mm = 0
            elif new_x < min_x:
                dx_mm = max(dx_mm, min_x - orig_offset_x)
            elif new_x > max_x:
                dx_mm = min(dx_mm, max_x - orig_offset_x)

            if min_y > max_y:
                dy_mm = 0
            elif new_y < min_y:
                dy_mm = max(dy_mm, min_y - orig_offset_y)
            elif new_y > max_y:
                dy_mm = min(dy_mm, max_y - orig_offset_y)

        for dragging, orig_offset_x, orig_offset_y in self._dragging:
            dragging.OffsetX = orig_offset_x + dx_mm
            dragging.OffsetY = orig_offset_y + dy_mm

        if self._dragging:
            self.update_svg()
        else:
            child = self._hit_test(event.pos())
            if child:
                self.setCursor(QtCore.Qt.OpenHandCursor)
            else:
                self.unsetCursor()

    def mouseReleaseEvent(self, event):
        if self._dragging:
            dx_px = event.pos().x() - self._drag_start.x()
            dy_px = event.pos().y() - self._drag_start.y()

            self._dragging = []
            self._drag_start = None
            self._drag_orig_offset = None
            self._page_obj.Proxy._is_dragging = False

            self.update_svg()
            if dx_px == 0 and dy_px == 0:
                self._page_obj.Document.abortTransaction()
            else:
                self._page_obj.Document.commitTransaction()
            self.setCursor(QtCore.Qt.OpenHandCursor)

    def wheelEvent(self, event):
        if self._anchor_placement is not None:
            delta_y = event.angleDelta().y()
            if delta_y == 0:
                event.ignore()
                return
            mods = QtWidgets.QApplication.keyboardModifiers()
            step = 1.0 if mods & QtCore.Qt.ShiftModifier else 15.0
            self._anchor_placement.step_rotation(-step if delta_y > 0 else step)
            self.update()
            event.accept()
            return

        child = self._hit_test(event.position())
        if not child:
            event.ignore()
            return

        selected = {s for s in Gui.Selection.getSelection()
                    if _is_page_child(s) and s in self._page_obj.Group}
        if child not in selected:
            event.ignore()
            return

        delta_y = event.angleDelta().y()
        if delta_y == 0:
            event.ignore()
            return

        delta = -1 if delta_y > 0 else 1
        step = 0.25
        current_rot = child.Rotation.Value
        new_rot = round(current_rot / step + delta) * step

        self._page_obj.Document.openTransaction("Rotate ShaperSvgImage")
        child.Rotation = new_rot
        self._page_obj.Document.commitTransaction()
        self.update_svg()
        event.accept()

    def keyPressEvent(self, event):
        if self._anchor_placement is not None and event.key() == QtCore.Qt.Key_Escape:
            self._cancel_anchor_placement()
            event.accept()
            return
        super().keyPressEvent(event)

    def closeEvent(self, event):
        self.closed.emit()
        super().closeEvent(event)


# This ViewProvider, which creates a new MDI window similar to what TechView and Spreadsheet
# do, is due to Claude. It's a bit hacky -- we call Gui.getMainWindow().centralWidget() to
# get the MDI area and then directly futz with Qt stuff. So there is no integration with the
# undo system, etc.
class ViewProviderShaperSvgPage:
    def __init__(self, vobj):
        vobj.Proxy = self

    def attach(self, vobj):
        self._vobj = vobj
        self._subwindow = None
        # Cache document name so we can check it in slotDeletedDocument, even though
        # self._vobj will have been deleted
        self._doc_name = self._vobj.Object.Document.Name
        # Arguably I should have a dummy object which only implements slotDeletedDocument,
        # so that I don't accidentally observe other events, but meh.
        App.addDocumentObserver(self)
        # Observe selection changes to track which images are selected
        Gui.Selection.addObserver(self)

    def slotUndoDocument(self, doc):
        # Updating the SVG is quite cheap (the actual SVG paths are computed elsewhere;
        # this function just puts them in <g> blocks to translate and rotate them) so
        # just redo it on every single undo/redo action.
        self.update_widget_svg()

    def slotRedoDocument(self, doc):
        self.update_widget_svg()

    def slotDeletedDocument(self, doc):
        """Method to allow this ViewProviderShaperSvgPage to act as a document observer"""
        try:
            if doc.Name == self._doc_name:
                if self._subwindow_alive():
                    self._subwindow.close()
        except RuntimeError:
            pass

    def addSelection(self, doc_name, obj_name, sub_name, pnt):
        """Called when selection changes in the document."""
        self.clearSelection(doc_name)

    def removeSelection(self, doc_name, obj_name, sub_name):
        """Called when selection changes in the document."""
        self.clearSelection(doc_name)

    def setSelection(self, doc_name, obj_name, sub_name, pnt):
        """Called when selection changes in the document."""
        self.clearSelection(doc_name)

    def clearSelection(self, doc_name):
        """Called when selection changes in the document."""
        if self._subwindow_alive():
            self.update_widget_svg()

    def getIcon(self):
        return os.path.join(_ICON_ROOT, "svg-page.svg")

    def doubleClicked(self, vobj):
        self._open_view(vobj.Object)
        self._open_edit_dialog(vobj.Object)
        return True

    def _open_edit_dialog(self, obj):
        from shaper_cutout_command.edit_shaper_svg_page import open_page_task_panel
        open_page_task_panel(obj)

    def _subwindow_alive(self):
        if not hasattr(self, '_subwindow') or self._subwindow is None:
            return False
        return True

    def _open_view(self, obj):
        if self._subwindow_alive():
            mdi_area = Gui.getMainWindow().centralWidget()
            mdi_area.setActiveSubWindow(self._subwindow)
            return

        mdi_area = Gui.getMainWindow().centralWidget()
        sub = QtWidgets.QMdiSubWindow()
        widget = _PageWidget(obj)
        widget.closed.connect(self._on_view_closed)
        sub.setWidget(widget)
        sub.setWindowTitle(obj.Label)
        sub.setAttribute(QtCore.Qt.WA_DeleteOnClose)
        mdi_area.addSubWindow(sub)
        sub.show()
        self._subwindow = sub
        self.update_widget_svg()

    def _on_view_closed(self):
        self._subwindow = None

    def update_widget_svg(self):
        if self._subwindow_alive():
            self._subwindow.widget().update_svg()

    def updateData(self, fp, prop):
        if prop in ('Width', 'Height', 'Group', 'GridSpacing',
                    'ShowOverlaps', 'ShowMinDistances',
                    'HasAnchor', 'AnchorX', 'AnchorY',
                    'AnchorRotation', 'AnchorMirror') \
                and self._subwindow_alive():
            self._subwindow.widget().update()

    def getDisplayModes(self, obj):
        return []

    def getDefaultDisplayMode(self):
        return "Shaded"

    def setDisplayMode(self, mode):
        return mode

    def onChanged(self, vp, prop):
        pass

    def setupContextMenu(self, vobj, menu):
        from shaper_cutout_command.export_shaper_svg_page import export
        from shaper_cutout_command.edit_shaper_svg_page import open_page_task_panel

        action = menu.addAction("Edit SVG Page")
        action.triggered.connect(lambda: open_page_task_panel(vobj.Object))

        action = menu.addAction("Export SVG Page")
        action.triggered.connect(lambda: export(vobj.Object))

        action = menu.addAction("Add Cutout to Page")
        action.triggered.connect(lambda: self._add_cutout_to(vobj.Object))

        action = menu.addAction("Add Sketch/Draft to Page")
        action.triggered.connect(lambda: self._add_shape_to(vobj.Object))

    def _add_shape_to(self, page):
        # Collect available objects with a shape which aren't already on a page.
        candidates = [o for o in App.ActiveDocument.Objects
                      if getattr(o, 'Type', None) not in _PAGE_CHILD_TYPES
                      and getattr(o, 'Type', None) != 'ShaperCutout'
                      and hasattr(o, 'Shape') and not o.Shape.isNull()]
        if not candidates:
            QtWidgets.QMessageBox.warning(
                None, "No Shapes",
                "No sketches or Draft objects found in the document.")
            return

        labels = [o.Label for o in candidates]
        label, ok = QtWidgets.QInputDialog.getItem(
            None,
            "Add Sketch/Draft to Page",
            "Select an object with a 2D shape:",
            labels,
            0,
            False,
        )
        if not ok:
            return

        source = candidates[labels.index(label)]
        ShaperSvgShape.create(page, source, source.Label + "_shape")

    def _add_cutout_to(self, page):
        # Collect available ShaperCutout objects
        cutouts = [o for o in App.ActiveDocument.Objects
                   if getattr(o, 'Type', None) == 'ShaperCutout']
        if not cutouts:
            QtWidgets.QMessageBox.warning(
                None, "No Cutouts",
                "No ShaperCutout objects found in the document.")
            return

        labels = [o.Label for o in cutouts]
        label, ok = QtWidgets.QInputDialog.getItem(
            None,
            "Add Cutout to Page",
            "Select a ShaperCutout:",
            labels,
            0,
            False,
        )
        if not ok:
            return

        cutout = cutouts[labels.index(label)]
        ShaperSvgImage.create(page, cutout, label + "_svg")

    def dumps(self):
        return None

    def loads(self, state):
        return None

    def canDragObject(self, child):
        return True

    def canDropObject(self, child):
        if getattr(child, 'Type', '') in ('ShaperCutout', 'ShaperSvgImage', 'ShaperSvgShape'):
            return True
        # Any object with a shape (sketches, Draft objects, ...) can be added to
        # the page as a ShaperSvgShape.
        return hasattr(child, 'Shape') and not child.Shape.isNull()

    def dropObject(self, vobj, child):
        if getattr(child, 'Type', '') == 'ShaperCutout':
            ShaperSvgImage.create(vobj.Object, child, child.Label + "_svg")
        elif getattr(child, 'Type', '') in ('ShaperSvgImage', 'ShaperSvgShape'):
            grp = list(vobj.Object.Group)
            grp.append(child)
            vobj.Object.Group = grp
        elif hasattr(child, 'Shape') and not child.Shape.isNull():
            ShaperSvgShape.create(vobj.Object, child, child.Label + "_shape")
