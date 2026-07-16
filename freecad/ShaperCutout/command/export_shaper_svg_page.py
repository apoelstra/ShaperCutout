# SPDX-License-Identifier: GPL-3.0-or-later

import os

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtWidgets


def export(obj):
    obj.Proxy._recompute_svg(obj)

    path, _ = QtWidgets.QFileDialog.getSaveFileName(
        None,
        "Export SVG Page",
        obj.Label + ".svg",
        "SVG Files (*.svg)",
    )
    if not path:
        return

    with open(path, 'w', encoding='utf-8') as f:
        f.write(obj.Svg)

    App.Console.PrintMessage(f"export_shaper_svg_page: wrote '{path}'\n")


class ExportShaperSvgPageCmd:
    def GetResources(self):
        return {
            "MenuText": "Export SVG Page",
            "ToolTip": "Export selected ShaperSvgPage to an SVG file",
        }

    def IsActive(self):
        if App.ActiveDocument is None:
            return False
        sel = Gui.Selection.getSelection()
        return (len(sel) >= 1 and
                all(getattr(o, 'Type', None) == 'ShaperSvgPage' for o in sel))

    def Activated(self):
        for obj in Gui.Selection.getSelection():
            if getattr(obj, 'Type', None) == 'ShaperSvgPage':
                export(obj)
