# SPDX-License-Identifier: GPL-3.0-or-later

import os
import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtWidgets


class CreateShaperSvgImageCmd:
    def GetResources(self):
        icon_path = os.path.join(os.path.dirname(__file__),
                                 "../resources/icons/export-svg-front.svg")
        return {
            "MenuText": "Add Cutout to Page",
            "ToolTip": "Add a ShaperCutout as an image on the selected ShaperSvgPage",
            "Pixmap": icon_path,
        }

    def IsActive(self):
        if App.ActiveDocument is None:
            return False
        sel = Gui.Selection.getSelection()
        return (len(sel) == 1 and
                getattr(sel[0], 'Type', None) == 'ShaperSvgPage')

    def Activated(self):
        sel = Gui.Selection.getSelection()
        if not sel:
            return
        page = sel[0]

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

        import ShaperSvgImage
        ShaperSvgImage.create(page, cutout)
