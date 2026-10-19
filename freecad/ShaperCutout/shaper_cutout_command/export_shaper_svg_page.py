# SPDX-License-Identifier: GPL-3.0-or-later

import os

import FreeCAD as App
from PySide import QtWidgets

from shaper_cutout_util import _ICON_ROOT, selection, ShaperCutoutType


def export(obj):
    """Write the page SVG to disk. Export MUST NOT include the orange
    selection highlight -- that is a GUI affordance, not a cut path."""
    path, _ = QtWidgets.QFileDialog.getSaveFileName(
        None,
        "Export SVG Page",
        obj.Label + ".svg",
        "SVG Files (*.svg)",
    )
    if not path:
        return

    with open(path, 'w', encoding='utf-8') as f:
        f.write(obj.Proxy.compute_svg(obj, for_export=True))

    App.Console.PrintMessage(f"export_shaper_svg_page: wrote '{path}'\n")


class ExportShaperSvgPageCmd:
    def GetResources(self):
        # FIXME add a dedicated export icon instead of riding on the "create" icon
        icon_path = os.path.join(_ICON_ROOT, "svg-page.svg")
        return {
            "MenuText": "Export SVG Page",
            "ToolTip": "Export selected ShaperSvgPage to an SVG file",
            "Pixmap": icon_path,
            "CmdType": "",
        }

    def IsActive(self):
        return selection().is_nonempty_exclusive(ShaperCutoutType.SVG_PAGE)

    def Activated(self):
        for obj in selection().dict[ShaperCutoutType.SVG_PAGE]:
            export(obj)
