# SPDX-License-Identifier: GPL-3.0-or-later

import os
import math

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore, QtGui, QtWidgets, QtSvg

from shaper_cutout_util import _ICON_ROOT
import ShaperSvgImage


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

        self.addDisplayProperties(obj)

        obj.Type = 'ShaperSvgPage'
        obj.Width = '8 ft'
        obj.Height = '4 ft'
        obj.GridSpacing = '1 in'
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
                if getattr(child, 'Type', None) != 'ShaperSvgImage':
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

        self.addDisplayProperties(obj)

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
                        if getattr(s, 'Type', '') == 'ShaperSvgImage' and s in obj.Group]
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
            if hasattr(child, 'Svg_Anchor') and child.IncludeAnchor:
                svg += f'{g}{child.Svg_Anchor}</g>'

        for child in selected:
            if not hasattr(child, 'Svg_BBCenter'):
                continue

            cx, cy = child.Proxy.centerXY(child)
            tx, ty = child.Proxy.translateXY(child, page_h)
            rot = child.Rotation.Value + 180

            g = f'<g transform="translate({tx:.4f},{ty:.4f}) rotate({rot:.4f},{cx:.4f},{cy:.4f})">'
            if hasattr(child, 'Svg_Full'):
                svg += f'{g}{child.Svg_Full}</g>'
            if hasattr(child, 'Svg_Anchor') and child.IncludeAnchor:
                svg += f'{g}{child.Svg_Anchor}</g>'
            if hasattr(child, 'Svg_Outline'):
                svg += f'{g}{child.Svg_Outline}</g>'

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

        page_h = obj.Height.Value
        for i, img1 in enumerate(images):
            for img2 in images[i+1:]:
                cx1, cy1 = img1.Proxy.centerXY(img1)
                tx1, ty1 = img1.Proxy.translateXY(img1, page_h)
                cx2, cy2 = img2.Proxy.centerXY(img2)
                tx2, ty2 = img2.Proxy.translateXY(img2, page_h)
                zvec = App.Vector(0, 0, 1)

                face1 = img1.Svg_TranslatedFace \
                    .rotated(App.Vector(cx1, cy1, 0), zvec, img1.Rotation.Value + 180) \
                    .translated(App.Vector(tx1, ty1, 0))
                face2 = img2.Svg_TranslatedFace \
                    .rotated(App.Vector(cx2, cy2, 0), zvec, img2.Rotation.Value + 180) \
                    .translated(App.Vector(tx2, ty2, 0))

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
                # (Vector, Vector) pairs where the two vectors are endpoints of min-dist lines.
                dist, pairs, _ = face1.distToShape(face2)
                if dist < 50.0 and len(pairs) > 1:  # 50mm threshold
                    pt1 = pairs[0][0]
                    pt2 = pairs[0][1]
                    dist = App.Units.Quantity(f"{dist} mm")
                    close_pairs.append((img1, img2, dist, pt1, pt2))

        return overlaps, close_pairs


class _PageWidget(QtWidgets.QWidget):
    def __init__(self, page_obj, parent=None):
        super().__init__(parent)
        self._page_obj = page_obj
        self._svg = ''
        self._overlaps = []
        self._close_pairs = []
        self.setMinimumSize(200, 100)
        self.setMouseTracking(True)
        self._dragging = None
        self._drag_start = None
        self._drag_orig_offset = None

        self._compute_overlap_timeout(page_obj)

    def update_svg(self):
        obj = self._page_obj
        self._svg = obj.Proxy.compute_svg(obj)
        self.update()

        self._compute_overlap_timer.setInterval(100)
        self._compute_overlap_timer.start()

    def _compute_overlap_timeout(self, obj):
        self._compute_overlap_timer = QtCore.QTimer()
        self._compute_overlap_timer.setSingleShot(True)
        self._compute_overlap_timer.timeout.connect(lambda: self._compute_overlap_timeout(obj))

        self._overlaps, self._close_pairs = obj.Proxy.compute_overlaps(obj)
        self._svg = obj.Proxy.compute_svg(obj)
        self.update()

    def _get_page_metrics(self) -> (float, float, float, float, float, float, float):
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
        # Minimum padding so the viewport has a GUI border. One of the `pad_x`/`pad_y` padding
        # values will be equal to this; the other may be larger.
        min_pad = 2
        # Page properties set by user, in mm
        page_w_mm = self._page_obj.Width.Value
        page_h_mm = self._page_obj.Height.Value
        grid_mm = self._page_obj.GridSpacing.Value
        if page_w_mm <= 0 or page_h_mm <= 0 \
                or self.width() < 2 * min_pad or self.height() < 2 * min_pad:
            return None

        # Determine padding, available viewport space, and grid size, all in pixels
        page_ar = page_w_mm / page_h_mm
        view_ar = self.width() / self.height()
        if page_ar > view_ar:
            # Page is width-limited
            avail_w = self.width() - 2 * min_pad
            avail_h = avail_w * page_ar
            pad_x = min_pad
            pad_y = (self.height() - avail_h) / 2.0
            grid_px = grid_mm * avail_w / page_w_mm
        else:
            # Page is height-limited
            avail_h = self.height() - 2 * min_pad
            avail_w = avail_h * page_ar
            pad_y = min_pad
            pad_x = (self.width() - avail_w) / 2.0
            grid_px = grid_mm * avail_h / page_h_mm

        return pad_x, pad_y, grid_px, avail_w, avail_h

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
                    if getattr(s, 'Type', '') == 'ShaperSvgImage' and s in self._page_obj.Group}

        ordered = list(reversed(self._page_obj.Group))
        swap_idx = 0
        for i in range(len(ordered)):
            if i > swap_idx and ordered[i] in selected:
                ordered[swap_idx], ordered[i] = ordered[i], ordered[swap_idx]

        for child in ordered:
            if getattr(child, 'Type', '') != 'ShaperSvgImage':
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
        if event.button() == QtCore.Qt.LeftButton:
            child = self._hit_test(event.pos())
            if child:
                # FIXME depending on Ctrl / Shift be better about selecting
                Gui.Selection.clearSelection()
                Gui.Selection.addSelection(child.Document.Name, child.Name)
                self._dragging = child
                self._drag_start = event.pos()
                self._drag_orig_offset = (child.OffsetX.Value, child.OffsetY.Value)
                self._page_obj.Proxy._is_dragging = True
                self._page_obj.Document.openTransaction("Move ShaperSvgImage")
                self.setCursor(QtCore.Qt.ClosedHandCursor)
            else:
                Gui.Selection.clearSelection()

    def mouseMoveEvent(self, event):
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

            rot_rad = math.radians(self._dragging.Rotation.Value)
            cos_r = abs(math.cos(rot_rad))
            sin_r = abs(math.sin(rot_rad))
            w_rot = self._dragging.Svg_BBLength.x * cos_r + self._dragging.Svg_BBLength.y * sin_r
            h_rot = self._dragging.Svg_BBLength.x * sin_r + self._dragging.Svg_BBLength.y * cos_r

            min_x = w_rot / 2 - self._dragging.Svg_BBLength.x / 2
            max_x = page_w - w_rot / 2 - self._dragging.Svg_BBLength.x / 2
            min_y = h_rot / 2 - self._dragging.Svg_BBLength.y / 2
            max_y = page_h - h_rot / 2 - self._dragging.Svg_BBLength.y / 2

            new_x = self._drag_orig_offset[0] + dx_mm
            new_y = self._drag_orig_offset[1] + dy_mm

            if min_x > max_x:
                self._dragging.OffsetX = (min_x + max_x) / 2
            else:
                self._dragging.OffsetX = max(min_x, min(new_x, max_x))

            if min_y > max_y:
                self._dragging.OffsetY = (min_y + max_y) / 2
            else:
                self._dragging.OffsetY = max(min_y, min(new_y, max_y))

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

            self._dragging = None
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
        child = self._hit_test(event.position())
        if not child:
            event.ignore()
            return

        selected = {s for s in Gui.Selection.getSelection()
                    if getattr(s, 'Type', '') == 'ShaperSvgImage' and s in self._page_obj.Group}
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

    def closeEvent(self, event):
        try:
            self._page_obj.ViewObject.Proxy._subwindow = None
        except NameError:
            # When closing the document, we'll fail to access self._page_obj.
            pass


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

    def removeSelection(self, doc_name, obj_name, sub_name, pnt):
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
        sub.setWidget(_PageWidget(self._vobj.Object))
        sub.setWindowTitle(obj.Label)
        sub.setAttribute(QtCore.Qt.WA_DeleteOnClose)
        mdi_area.addSubWindow(sub)
        sub.show()
        self._subwindow = sub
        self.update_widget_svg()

    def update_widget_svg(self):
        if self._subwindow_alive():
            self._subwindow.widget().update_svg()

    def updateData(self, fp, prop):
        if prop in ('Width', 'Height', 'Group', 'GridSpacing',
                    'ShowOverlaps', 'ShowMinDistances') and self._subwindow_alive():
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
        return getattr(child, 'Type', '') in ('ShaperCutout', 'ShaperSvgImage')

    def dropObject(self, vobj, child):
        if getattr(child, 'Type', '') == 'ShaperCutout':
            ShaperSvgImage.create(vobj.Object, child, child.Label + "_svg")
        else:
            grp = list(vobj.Object.Group)
            grp.append(child)
            vobj.Object.Group = grp
