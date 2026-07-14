# SPDX-License-Identifier: GPL-3.0-or-later

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore, QtGui, QtWidgets, QtSvg


def create(name="ShaperSvgPage"):
    doc = App.ActiveDocument
    obj = doc.addObject('App::DocumentObjectGroupPython', name)
    obj.Label = name
    ShaperSvgPage(obj)
    if App.GuiUp:
        ViewProviderShaperSvgPage(obj.ViewObject)
    doc.recompute()
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
        obj.addProperty('App::PropertyString', 'Svg', 'Base',
                        'SVG code of the whole page')

        obj.Type = 'ShaperSvgPage'
        obj.Width = '8 ft'
        obj.Height = '4 ft'
        self._recompute_svg(obj)

    def onChanged(self, obj, prop):
        if prop == 'Group':
            for child in list(obj.Group):
                if getattr(child, 'Type', None) != 'ShaperSvgImage':
                    obj.removeObject(child)

        self._recompute_svg(obj)

    def execute(self, obj):
        pass

    def dumps(self):
        return None

    def loads(self, state):
        return None

    def _recompute_svg(self, obj):
        from command.export_shaper_svg import _collect_paths, _collect_dado_groups

        if not hasattr(obj, 'Width') or not hasattr(obj, 'Height'):
            return

        page_w = obj.Width.Value
        page_h = obj.Height.Value

        svg = f'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg"
     xmlns:shaper="http://www.shapertools.com/namespaces/shaper"
     viewBox="0 0 {page_w:.4f} {page_h:.4f}"
     width="{page_w:.4f}mm" height="{page_h:.4f}mm">
  <rect x="0" y="0"
        width="{page_w:.4f}" height="{page_h:.4f}"
        fill="none" stroke="blue" stroke-width="1"
        shaper:cutType="guide" />
'''

        # Render each ShaperSvgImage child
        for child in obj.Group:
            if getattr(child, 'Type', None) != 'ShaperSvgImage':
                continue
            cutout = child.Cutout
            if cutout is None:
                continue
            try:
                # See comment in export_shaper_svg.py; because SVG interprets Y in the opposite
                # direction as FreeCAD, need to interpret Flip in the opposite way that you'd
                # expect, for mirroring purposes.
                mirror = (not child.Flip) ^ child.Invert
                dados = _collect_dado_groups(cutout, child.Flip)
                path_elements, _ = _collect_paths(cutout, dados, mirror=mirror)
                for path in path_elements:
                    svg += f'{path}\n'
            except Exception as e:
                App.Console.PrintWarning(f"ShaperSvgPage render: {e}\n")
                return

        # Initially we just have a blue "guide" rectangle and nothing else.
        obj.Svg = svg + "</svg>\n"


class _PageWidget(QtWidgets.QWidget):
    def __init__(self, page_obj, parent=None):
        super().__init__(parent)
        self._page_obj = page_obj
        self.setMinimumSize(200, 100)

    def paintEvent(self, event):
        # Scale the SVG to fit into the window with 20px of padding on all four sides.
        pad = 20
        page_w_mm = self._page_obj.Width.Value
        page_h_mm = self._page_obj.Height.Value
        avail_w = self.width() - 2 * pad
        avail_h = self.height() - 2 * pad

        if page_w_mm <= 0 or page_h_mm <= 0 or avail_w <= 0 or avail_h <= 0:
            return

        # Render the SVG
        renderer = QtSvg.QSvgRenderer()
        renderer.load(QtCore.QByteArray(self._page_obj.Svg.encode('utf-8')))
        if not renderer.isValid():
            return

        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        renderer.render(painter, QtCore.QRectF(pad, pad, avail_w, avail_h))
        painter.end()


# This ViewProvider, which creates a new MDI window similar to what TechView and Spreadsheet
# do, is due to Claude. It's a bit hacky -- we call Gui.getMainWindow().centralWidget() to
# get the MDI area and then directly futz with Qt stuff. So there is no integration with the
# undo system, etc.
class ViewProviderShaperSvgPage:
    def __init__(self, vobj):
        vobj.Proxy = self
        self._subwindow = None

    def attach(self, vobj):
        self._vobj = vobj
        # Cache document name so we can check it in slotDeletedDocument, even though
        # self._vobj will have been deleted
        self._doc_name = self._vobj.Object.Document.Name
        # Arguably I should have a dummy object which only implements slotDeletedDocument,
        # so that I don't accidentally observe other events, but meh.
        App.addDocumentObserver(self)

    def slotDeletedDocument(self, doc):
        """Method to allow this ViewProviderShaperSvgPage to act as a document observer"""
        try:
            if doc.Name == self._doc_name:
                if self._subwindow_alive():
                    self._subwindow.close()
        except RuntimeError:
            pass

    def getIcon(self):
        import os
        return os.path.join(os.path.dirname(__file__),
                            'resources/icons/export-svg-front.svg')

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
        widget = _PageWidget(obj)
        sub = QtWidgets.QMdiSubWindow()
        sub.setWidget(widget)
        sub.setWindowTitle(obj.Label)
        sub.setAttribute(QtCore.Qt.WA_DeleteOnClose)
        mdi_area.addSubWindow(sub)
        sub.show()
        self._subwindow = sub

    def updateData(self, fp, prop):
        if prop in ('Width', 'Height', 'Group') and self._subwindow_alive():
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
        action = menu.addAction("Add Cutout to Page")
        action.triggered.connect(lambda: self._add_image(vobj.Object))

    def _add_image(self, obj):
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(obj)
        Gui.runCommand('ShaperCutout_createSvgImage')

    def dumps(self):
        return None

    def loads(self, state):
        return None
