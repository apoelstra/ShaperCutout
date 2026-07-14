# SPDX-License-Identifier: GPL-3.0-or-later

import os
import FreeCAD as App
import FreeCADGui as Gui


class CreateShaperSvgPageCmd:
    def GetResources(self):
        icon_path = os.path.join(os.path.dirname(__file__),
                                 "../resources/icons/export-svg-front.svg")
        return {
            "MenuText": "Create SVG Page",
            "ToolTip": "Create a ShaperSvgPage layout object",
            "Pixmap": icon_path,
        }

    def IsActive(self):
        return App.ActiveDocument is not None

    def Activated(self):
        import ShaperSvgPage as _mod
        _mod.create()
        App.ActiveDocument.recompute()
        Gui.SendMsgToActiveView("ViewFit")


Gui.addCommand('ShaperCutout_createSvgPage', CreateShaperSvgPageCmd())
