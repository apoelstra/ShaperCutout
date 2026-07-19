# SPDX-License-Identifier: GPL-3.0-or-later

import os
import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtWidgets

from shaper_cutout_util import are_exclusively_selected, is_single_selected


class CreateShaperSvgImageCmd:
    def GetResources(self):
        icon_path = os.path.join(os.path.dirname(__file__),
                                 "../resources/icons/svg-image.svg")
        return {
            "MenuText": "Add Cutout to Page",
            "ToolTip": "Add a ShaperCutout as an image on the selected ShaperSvgPage",
            "Pixmap": icon_path,
        }

    def IsActive(self):
        if App.ActiveDocument is None:
            return False

        return is_single_selected('ShaperSvgPage') or are_exclusively_selected('ShaperCutout')

    def Activated(self):
        import ShaperSvgImage

        sel = Gui.Selection.getSelection()
        if not sel:
            return
        # We have two modes.
        if sel[0].Type == 'ShaperSvgPage':
            # 1. The user has selected exactly one Page and is going to add Images to it.
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

            ShaperSvgImage.create(page, cutout, label + "_svg")
        else:
            # 2. The user has selected some number of Images and will add them to a Page.
            pages = [o for o in App.ActiveDocument.Objects
                     if getattr(o, 'Type', None) == 'ShaperSvgPage']
            if not pages:
                QtWidgets.QMessageBox.warning(
                    None, "No SVG Pages",
                    "No ShaperSvgPage objects found in the document.")
                return

            labels = [o.Label for o in pages]
            label, ok = QtWidgets.QInputDialog.getItem(
                None,
                "Add Cutouts to Page",
                "Select a Page:",
                labels,
                0,
                False,
            )
            if not ok:
                return

            page = pages[labels.index(label)]
            for cutout in sel:
                ShaperSvgImage.create(page, cutout, cutout.Label + "_svg")
