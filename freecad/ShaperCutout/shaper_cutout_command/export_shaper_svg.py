# SPDX-License-Identifier: GPL-3.0-or-later

import os

import FreeCAD as App
import FreeCADGui as Gui

from PySide import QtWidgets

from shaper_cutout_svg import SvgData
from shaper_cutout_util import _ICON_ROOT, are_exclusively_selected


def export(cutout, exportFront):
    """Main export entry point. Shows file dialog(s) and writes SVG(s)."""
    path, _ = QtWidgets.QFileDialog.getSaveFileName(
        None,
        "Export Shaper SVG",
        cutout.Label + ("_front" if exportFront else "_back") + ".svg",
        "SVG Files (*.svg)",
    )
    if not path:
        return

    svg = SvgData(cutout, exportFront).extract_complete_svg()
    with open(path, 'w', encoding='utf-8') as f:
        f.write(svg)

    App.Console.PrintMessage(f"export_shaper_svg: wrote '{path}'\n")


# ---------------------------------------------------------------------------
# FreeCAD command
# ---------------------------------------------------------------------------

class ExportShaperSVGCmd:
    def __init__(self, exportFront):
        self.exportFront = exportFront

    def GetResources(self):
        if self.exportFront:
            icon_path = os.path.join(_ICON_ROOT, "export-svg-front.svg")
            menu_text = "Export Shaper SVG (Front)"
        else:
            icon_path = os.path.join(_ICON_ROOT, "export-svg-back.svg")
            menu_text = "Export Shaper SVG (Back)"

        return {
            "MenuText": menu_text,
            "ToolTip": "Export selected ShaperCutout to Shaper-compatible SVG file(s)",
            "Pixmap": icon_path,
            "CmdType": "",
        }

    def IsActive(self):
        return App.ActiveDocument and are_exclusively_selected('ShaperCutout')

    def Activated(self):
        for obj in Gui.Selection.getSelection():
            if getattr(obj, 'Type', None) == 'ShaperCutout':
                export(obj, self.exportFront)
