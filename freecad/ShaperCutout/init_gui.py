# SPDX-License-Identifier: GPL-3.0-or-later

import os

import FreeCAD as App
import FreeCADGui as Gui

import ShaperCutout
import ShaperDados
import ShaperMiter

module_path = os.path.dirname(ShaperCutout.__file__)  # lol


class ShaperCutoutWorkbench(Gui.Workbench):
    MenuText = "ShaperCutout"
    ToolTip = "Andrew's Shaper Origin plywood workbench"
    Icon = os.path.join(module_path, "resources/icons/ShaperCutoutWorkbench.svg")

    def __init__(self):
        "This function is executed when FreeCAD starts"

    def Activated(self):
        "This function is executed when the workbench is activated"

    def Deactivated(self):
        "This function is executed when the workbench is deactivated"

    def GetClassName(self):
        # this function is mandatory if this is a full python workbench
        return "Gui::PythonWorkbench"

    def Initialize(self):
        # Read metadata from FreeCAD (will throw an exception prior to 0.21)
        packageFile = os.path.join(module_path, '../../package.xml')
        metadata = App.Metadata(packageFile)
        App.Console.PrintMessage(
                "Initializing Andrew's Shaper workbench" +
                ' (' + metadata.Version + ', ' + metadata.Date + ') .'
        )

        # Import everything
        from command.create_shaper_cutout import createShaperCutoutCmd
        Gui.addCommand('ShaperCutout_createCutout', createShaperCutoutCmd())

        from command.create_shaper_dados import createShaperDadosCmd
        Gui.addCommand('ShaperCutout_createDados', createShaperDadosCmd())

        from command.create_shaper_miter import createShaperMiterCmd
        Gui.addCommand('ShaperCutout_createMiter', createShaperMiterCmd())

        from command.export_shaper_svg import ExportShaperSVGCmd
        Gui.addCommand('ShaperCutout_exportSVG', ExportShaperSVGCmd())

        self.appendMenu(
            "&Shaper",
            [
                "ShaperCutout_createCutout",
                "ShaperCutout_createDados",
                "ShaperCutout_createMiter",
                "ShaperCutout_exportSVG",
                "Sketcher_NewSketch",
                "Part_CoordinateSystem",
                "Part_DatumPlane",
            ],
        )
        self.appendToolbar(
            "Shaper",
            [
                "ShaperCutout_createCutout",
                "ShaperCutout_createDados",
                "ShaperCutout_createMiter",
                "ShaperCutout_exportSVG",
                "Sketcher_NewSketch",
                "Part_CoordinateSystem",
                "Part_DatumPlane",
            ],
        )


# Don't forget this line!!
Gui.addWorkbench(ShaperCutoutWorkbench())
