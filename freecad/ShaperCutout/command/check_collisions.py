# SPDX-License-Identifier: GPL-3.0-or-later

import os
import FreeCAD as App

from shaper_cutout_util import _ICON_ROOT


def check_collisions():
    """Check all pairs of ShaperCutouts for collisions."""
    cutouts = [obj for obj in App.ActiveDocument.Objects
               if getattr(obj, 'Type', '') == 'ShaperCutout']

    if len(cutouts) < 2:
        App.Console.PrintMessage("Fewer than 2 ShaperCutouts; nothing to check.\n")
        return

    found = False
    for i in range(len(cutouts)):
        for j in range(i + 1, len(cutouts)):
            a, b = cutouts[i], cutouts[j]
            if not a.Shape or not b.Shape:
                continue

            # Bounding box pre-check
            bb_a = a.Shape.BoundBox
            bb_b = b.Shape.BoundBox
            if not bb_a.intersect(bb_b):
                continue

            # Compute actual intersection
            try:
                common = a.Shape.common(b.Shape)
                if common and common.Volume > 1e-4:
                    App.Console.PrintWarning(
                        f"Collision: '{a.Label}' and '{b.Label}' "
                        f"intersect (volume {common.Volume:.3f})\n")
                    found = True
            except Exception as e:
                App.Console.PrintWarning(
                    f"Error checking '{a.Label}' vs '{b.Label}': {e}\n")

    if not found:
        App.Console.PrintMessage("No collisions found.\n")


class CheckCollisionsCmd:
    def GetResources(self):
        icon_path = os.path.join(_ICON_ROOT, "collision.svg")
        return {
            'MenuText': 'Check Collisions',
            'ToolTip': 'Check for collisions between ShaperCutouts',
            "Pixmap": icon_path,
        }

    def Activated(self):
        check_collisions()

    def IsActive(self):
        return App.ActiveDocument is not None
