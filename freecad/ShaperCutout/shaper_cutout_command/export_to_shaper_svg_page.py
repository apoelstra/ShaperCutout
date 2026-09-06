# SPDX-License-Identifier: GPL-3.0-or-later

import os

import FreeCAD as App
import FreeCADGui as Gui

from shaper_cutout_util import _ICON_ROOT, are_exclusively_selected


def create_page(cutout):
    """Create a ShaperSvgPage sized exactly to the given cutout, containing only
    that cutout as a single ShaperSvgImage.

    The cutout is placed at the page's bottom-left corner at its default
    (front) orientation. The user can then use the page editor to flip the
    cutout, adjust its position, set the anchor, etc., before exporting the
    page itself.
    """
    import ShaperSvgPage
    import ShaperSvgImage

    doc = cutout.Document
    page = ShaperSvgPage.create(cutout.Label + "_page")
    image = ShaperSvgImage.create(page, cutout, cutout.Label + "_svg")
    image.OffsetX = 0.0
    image.OffsetY = 0.0

    # Constrain the page size to the cutout's bounding box so the piece
    # exactly fills the page.
    doc.recompute()
    page.Width = image.Svg_BBLength.x
    page.Height = image.Svg_BBLength.y
    doc.recompute()
    return page


# ---------------------------------------------------------------------------
# FreeCAD command
# ---------------------------------------------------------------------------

class ExportToShaperSvgPageCmd:
    def GetResources(self):
        icon_path = os.path.join(_ICON_ROOT, "svg-page.svg")
        return {
            "MenuText": "Export to ShaperSvgPage",
            "ToolTip": "Create a ShaperSvgPage sized to the selected ShaperCutout(s) "
                       "for layout, flipping, and export",
            "Pixmap": icon_path,
            "CmdType": "AlterDoc",
        }

    def IsActive(self):
        return App.ActiveDocument and are_exclusively_selected('ShaperCutout')

    def Activated(self):
        for obj in Gui.Selection.getSelection():
            if getattr(obj, 'Type', None) == 'ShaperCutout':
                create_page(obj)
