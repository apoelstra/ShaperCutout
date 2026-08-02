# SPDX-License-Identifier: GPL-3.0-or-later

# This "report view" was significantly modeled after femguiutils/selection_widgets.py
# in the FEM workbench.

import os
import FreeCAD as App
import FreeCADGui as Gui

from command.report_view.report import ReportViewReport
from command.report_view.cutouts import ReportViewCutouts
from command.report_view.dados import ReportViewDados
from command.report_view.miters import ReportViewMiter
from command.report_view.slots import ReportViewSlots
from shaper_cutout_util import _ICON_ROOT


class ReportViewTaskPanel:
    def __init__(self):
        self._doc = App.ActiveDocument
        self._doc.openTransaction("ShaperCutout Report Panel")

        self._report_section = ReportViewReport()
        self._cutouts_section = ReportViewCutouts(self._report_section)
        self._dados_section = ReportViewDados(self._report_section)
        self._slots_section = ReportViewSlots(self._report_section)
        self._miter_section = ReportViewMiter(self._report_section)

        self.form = [
            self._report_section,
            self._cutouts_section,
            self._dados_section,
            self._slots_section,
            self._miter_section,
        ]

    def accept(self):
        self._cutouts_section.run_cleanup()
        self._dados_section.run_cleanup()
        self._slots_section.run_cleanup()
        self._miter_section.run_cleanup()
        self._doc.commitTransaction()
        Gui.Control.closeDialog()

    def reject(self):
        self._cutouts_section.run_cleanup()
        self._dados_section.run_cleanup()
        self._slots_section.run_cleanup()
        self._doc.abortTransaction()
        Gui.Control.closeDialog()


class ReportViewCmd:
    def GetResources(self):
        icon_path = os.path.join(_ICON_ROOT, "report-view.svg")
        return {
            "MenuText": "Report View",
            "ToolTip": "Open the Shaper Cutout report view task panel.",
            "Pixmap": icon_path,
        }

    def IsActive(self):
        return App.ActiveDocument is not None

    def Activated(self):
        if Gui.Control.activeDialog():
            Gui.Control.closeDialog()
        panel = ReportViewTaskPanel()
        Gui.Control.showDialog(panel)
