# SPDX-License-Identifier: GPL-3.0-or-later

"""Task panel "watchers" for the ShaperCutout workbench.

Mirrors how the Draft workbench shows its "Create Objects" task panel:
while the workbench is active and no other task panel is open, the
Task Panel shows boxes of commonly-used actions. Each watcher is a
plain Python object with a `title`, an optional `icon`, a `commands`
list of FreeCAD command names, and a `shouldShow()` method that
decides whether the box is visible. FreeCAD shows a watcher's box
only while `shouldShow()` returns true (and no task dialog is open),
and keeps each button's enabled state in sync with the command's
`IsActive()` as the selection changes.

So:

* "Create Objects" shows when a document is open and nothing is
  selected -- it offers the actions that work from scratch (new LCS,
  datum plane, sketch, ...).
* "Modify Objects" shows when something is selected -- it offers the
  actions that operate on the selection; the ones that don't apply to
  the current selection are simply greyed out.
"""

import FreeCAD as App
import FreeCADGui as Gui


def _selection_is_empty():
    """Single source of truth for the Create/Modify split.

    Both watchers are polled by FreeCAD on every selection change;
    deriving both from this one helper guarantees they stay exact
    complements (never both shown, never both hidden while a document
    is open) and queries the selection once per watcher call instead
    of each watcher owning its own copy of the predicate.
    """
    return not Gui.Selection.getSelection()


class CreateObjectsWatcher:
    """Shown when a document is open and the selection is empty."""

    def __init__(self):
        self.title = "Create Objects"
        self.commands = [
            "Part_CoordinateSystem",
            "Part_DatumPlane",
            "Sketcher_NewSketch",
            "ShaperCutout_createSvgPage",
            "ShaperCutout_reportView",
        ]

    def shouldShow(self):
        return App.ActiveDocument is not None and _selection_is_empty()


class ModifyObjectsWatcher:
    """Shown when a document is open and something is selected.

    Commands that do not apply to the current selection are greyed
    out by FreeCAD (via each command's IsActive); only the ones that
    do apply are clickable.
    """

    def __init__(self):
        self.title = "Modify Objects"
        self.commands = [
            "ShaperCutout_createCutout",
            "ShaperCutout_createDados",
            "ShaperCutout_createMiter",
            "ShaperCutout_createSlot",
            "ShaperCutout_exportToSvgPage",
            "ShaperCutout_exportSvgPage",
            "ShaperCutout_reportView",
        ]

    def shouldShow(self):
        return App.ActiveDocument is not None and not _selection_is_empty()


def set_watchers():
    """Register the workbench's task panel watchers (Draft style)."""
    Gui.Control.addTaskWatcher([CreateObjectsWatcher(), ModifyObjectsWatcher()])


def clear_watchers():
    """Remove the workbench's task panel watchers.

    Note: `Gui.Control.clearTaskWatcher()` clears the task panel's
    *entire* watcher set, not just the ones we registered -- including
    any installed by third-party addons. This is deliberate and matches
    what the Draft workbench's Deactivated() does. It is safe for
    built-in workbenches because FreeCAD calls the outgoing workbench's
    Deactivated() *before* the incoming workbench's Activated() (see
    Gui::Application::activateWorkbench in src/Gui/Application.cpp), so our
    clear() can never wipe the successor workbench's watchers.
    """
    Gui.Control.clearTaskWatcher()
