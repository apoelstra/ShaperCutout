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

        obj.Type = 'ShaperSvgPage'
        obj.Width = '8 ft'
        obj.Height = '4 ft'
        obj.GridSpacing = '1 in'

    def onChanged(self, obj, prop):
        if prop == 'Group':
            for child in list(obj.Group):
                if getattr(child, 'Type', None) != 'ShaperSvgImage':
                    obj.removeObject(child)

        if obj.ViewObject and obj.ViewObject.Proxy:
            obj.ViewObject.Proxy._page_widget.update_svg(obj)

    def execute(self, obj):
        if obj.ViewObject and obj.ViewObject.Proxy:
            obj.ViewObject.Proxy._page_widget.update_svg(obj)
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


class _PageWidget(QtWidgets.QWidget):
    def __init__(self, page_obj, parent=None):
        super().__init__(parent)
        self._page_obj = page_obj
        self._svg = ''
        self.setMinimumSize(200, 100)
        self.setMouseTracking(True)
        self._dragging = None
        self._drag_start = None
        self._drag_orig_offset = None

    def update_svg(self, obj=None):
        if obj is None:
            obj = self._page_obj
        page_w = obj.Width.Value
        page_h = obj.Height.Value

        self._svg = f'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg"
     xmlns:shaper="http://www.shapertools.com/namespaces/shaper"
     viewBox="0 0 {page_w:.4f} {page_h:.4f}"
     width="{page_w:.4f}mm" height="{page_h:.4f}mm">
  <rect x="0" y="0"
        width="{page_w:.4f}" height="{page_h:.4f}"
        fill="none" stroke="blue" stroke-width="2"
        shaper:cutType="guide" />
'''

        selected = [s for s in Gui.Selection.getSelection()
                    if getattr(s, 'Type', '') == 'ShaperSvgImage' and s in obj.Group]
        # Render each ShaperSvgImage child
        for child in obj.Group:
            if not hasattr(child, 'Svg_BBCenter'):
                continue
            if child in selected:
                # We will draw selected children below, so they're on top
                continue

            cx = child.Svg_BBCenter.x
            cy = child.Svg_BBCenter.y
            rot = child.Rotation.Value + 180
            tx = child.OffsetX.Value - child.Svg_BBCenter.x + child.Svg_BBLength.x / 2
            ty = page_h - child.Svg_BBCenter.y - child.Svg_BBLength.y / 2 - child.OffsetY.Value

            g = f'<g transform="translate({tx:.4f},{ty:.4f}) rotate({rot:.4f},{cx:.4f},{cy:.4f})">'
            if hasattr(child, 'Svg_Full'):
                self._svg += f'{g}{child.Svg_Full}</g>'
            if hasattr(child, 'Svg_Anchor') and child.IncludeAnchor:
                self._svg += f'{g}{child.Svg_Anchor}</g>'

        for child in selected:
            if not hasattr(child, 'Svg_BBCenter'):
                continue

            cx = child.Svg_BBCenter.x
            cy = child.Svg_BBCenter.y
            rot = child.Rotation.Value + 180
            tx = child.OffsetX.Value - child.Svg_BBCenter.x + child.Svg_BBLength.x / 2
            ty = page_h - child.Svg_BBCenter.y - child.Svg_BBLength.y / 2 - child.OffsetY.Value

            g = f'<g transform="translate({tx:.4f},{ty:.4f}) rotate({rot:.4f},{cx:.4f},{cy:.4f})">'
            if hasattr(child, 'Svg_Full'):
                self._svg += f'{g}{child.Svg_Full}</g>'
            if hasattr(child, 'Svg_Anchor') and child.IncludeAnchor:
                self._svg += f'{g}{child.Svg_Anchor}</g>'
            if hasattr(child, 'Svg_Outline'):
                self._svg += f'{g}{child.Svg_Outline}</g>'

        self._svg += "</svg>"
        self.update()

    def _get_page_metrics(self):
        min_pad = 5
        page_w_mm = self._page_obj.Width.Value
        page_h_mm = self._page_obj.Height.Value
        grid_mm = self._page_obj.GridSpacing.Value

        avail_w = self.width() - 2 * min_pad
        avail_h = self.height() - 2 * min_pad
        if page_w_mm <= 0 or page_h_mm <= 0 or avail_w <= 0 or avail_h <= 0:
            return None

        grid_w = math.ceil(page_w_mm / grid_mm)
        grid_h = math.ceil(page_h_mm / grid_mm)
        grid_px = min(avail_w / grid_w, avail_h / grid_h)

        pad_x = (self.width() - grid_w * grid_px) / 2.0
        pad_y = (self.height() - grid_h * grid_px) / 2.0
        avail_w = self.width() - 2 * pad_x
        avail_h = self.height() - 2 * pad_y

        return pad_x, pad_y, grid_px, grid_w, grid_h, avail_w, avail_h

    def paintEvent(self, event):
        metrics = self._get_page_metrics()
        if not metrics:
            return
        pad_x, pad_y, grid_px, grid_w, grid_h, avail_w, avail_h = metrics

        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)

        # White page background
        painter.fillRect(QtCore.QRectF(pad_x, pad_y, avail_w, avail_h),
                         QtGui.QColor('white'))

        # Light grey grid
        if grid_px > 1:
            for x in range(grid_w):
                if x % 10 == 0:
                    painter.setPen(QtGui.QPen(QtGui.QColor(220, 120, 120), 0.5))
                else:
                    painter.setPen(QtGui.QPen(QtGui.QColor(220, 220, 220), 0.5))

                px = pad_x + x * grid_px
                painter.drawLine(QtCore.QPointF(px, pad_y),
                                 QtCore.QPointF(px, pad_y + avail_h))
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

        painter.end()

    def _hit_test(self, pos):
        metrics = self._get_page_metrics()
        if not metrics:
            return None
        pad_x, pad_y, grid_px, _, _, _, _ = metrics

        grid_mm = self._page_obj.GridSpacing.Value
        page_h = self._page_obj.Height.Value
        pos_x_mm = (pos.x() - pad_x) / grid_px * grid_mm
        pos_y_mm = (pos.y() - pad_y) / grid_px * grid_mm

        for child in reversed(self._page_obj.Group):
            if getattr(child, 'Type', '') != 'ShaperSvgImage':
                continue

            cx = child.OffsetX.Value + child.Svg_BBLength.x / 2
            cy = page_h - child.Svg_BBLength.y / 2 - child.OffsetY.Value
            length = child.Svg_BBLength

            xdist = abs(cx - pos_x_mm)
            ydist = abs(cy - pos_y_mm)

            if xdist < length.x / 2 and ydist < length.y / 2:
                return child

        return None

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            child = self._hit_test(event.pos())
            if child:
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
            _, _, grid_px, _, _, _, _ = metrics
            grid_mm = self._page_obj.GridSpacing.Value
            page_h = self._page_obj.Height.Value
            page_w = self._page_obj.Width.Value

            dx_px = event.pos().x() - self._drag_start.x()
            dy_px = event.pos().y() - self._drag_start.y()
            dx_mm = dx_px / grid_px * grid_mm
            dy_mm = -dy_px / grid_px * grid_mm

            self._dragging.OffsetX = min(
                self._drag_orig_offset[0] + dx_mm,
                page_w - self._dragging.Svg_BBLength.x,
            )
            self._dragging.OffsetY = min(
                self._drag_orig_offset[1] + dy_mm,
                page_h - self._dragging.Svg_BBLength.y,
            )

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


# This ViewProvider, which creates a new MDI window similar to what TechView and Spreadsheet
# do, is due to Claude. It's a bit hacky -- we call Gui.getMainWindow().centralWidget() to
# get the MDI area and then directly futz with Qt stuff. So there is no integration with the
# undo system, etc.
class ViewProviderShaperSvgPage:
    def __init__(self, vobj):
        self._page_widget = None
        vobj.Proxy = self

    def attach(self, vobj):
        self._vobj = vobj
        self._page_widget = _PageWidget(self._vobj.Object)
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
        self._page_widget.update_svg(self._vobj.Object)

    def slotRedoDocument(self, doc):
        self._page_widget.update_svg(self._vobj.Object)

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
        self._page_widget.update_svg(self._vobj.Object)

    def removeSelection(self, doc_name, obj_name, sub_name, pnt):
        """Called when selection changes in the document."""
        self.addSelection(doc_name, obj_name, sub_name, pnt)

    def clearSelection(self, doc_name):
        """Called when selection changes in the document."""
        self._page_widget.update_svg(self._vobj.Object)

    def onDelete(self, vobj, subelements):
        """Clean up selection observer when view provider is deleted."""
        try:
            Gui.Selection.removeSelectionObserver(self)
        except (RuntimeError, ValueError):
            pass
        return True

    def getIcon(self):
        return os.path.join(_ICON_ROOT, "svg-page.svg")

    def doubleClicked(self, vobj):
        self._open_view(vobj.Object)
        return True

    def _subwindow_alive(self):
        try:
            if not hasattr(self, '_subwindow') or self._subwindow is None:
                return False
            # PySide raises RuntimeError when accessing a deleted C++ object
            self._subwindow.isVisible()
            return True
        except RuntimeError:
            self._subwindow = None
            return False

    def _open_view(self, obj):
        if self._subwindow_alive():
            mdi_area = Gui.getMainWindow().centralWidget()
            mdi_area.setActiveSubWindow(self._subwindow)
            return

        mdi_area = Gui.getMainWindow().centralWidget()
        sub = QtWidgets.QMdiSubWindow()
        sub.setWidget(self._page_widget)
        sub.setWindowTitle(obj.Label)
        sub.setAttribute(QtCore.Qt.WA_DeleteOnClose)
        mdi_area.addSubWindow(sub)
        sub.show()
        self._subwindow = sub

    def updateData(self, fp, prop):
        if prop in ('Width', 'Height', 'Group', 'GridSpacing') and self._subwindow_alive():
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
