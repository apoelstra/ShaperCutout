# SPDX-License-Identifier: GPL-3.0-or-later

from typing import Optional

import FreeCAD as App
import FreeCADGui as Gui


def force_combo_to_value(combo_widget, val):
    """Selects an object from a combo box, adding it at the top if it does not exist."""
    idx = combo_widget.findData(val)
    if idx < 0:
        combo_widget.insertItem(0, val.Label, val)
        idx = 0
    combo_widget.setCurrentIndex(idx)


def parent_cutout(obj: App.DocumentObject, list_prop: str) -> Optional[App.DocumentObject]:
    for o in obj.InList:
        if (getattr(o, 'Type', None) == 'ShaperCutout' and obj in getattr(o, list_prop, [])):
            return o
    return None


def copy_property(
    source: App.DocumentObject,
    target: App.DocumentObject,
    name: str,
    target_name: Optional[str] = None,
):
    """Copies a property, including potentially copying an expression, from source to target.

    This method is used to synchronize the thickness values of cutouts that share a center
    plane. It is a bit weird and un-FreeCAD-like. The correct way to synchronize objects
    like this is to use setExpression("source.Property"). I'm not doing this because with
    cutouts that share center planes none of them are individually the "parent", so instead
    we present to the user the illusion that "editing one edits all of them".

    In general this can lead to wrong behavior, e.g. if the user adds an expression that refers
    to some other property of the current cutout, when we copy the expression the reference
    might refer to something else. Because Cutouts have almost no properties (and no other Length
    properties at all) I think this is fairly unlikely to happen. The expected usage here is that
    all thicknesses will be set to simple values that come from a VarSet or something, and not be
    derived from downstream properties.

    Anyway don't use this method unless you've thought carefully about it.
    """
    target_name = target_name or name
    expression = None
    for ee_name, ee_value in source.ExpressionEngine:
        if ee_name == name:
            expression = ee_value
            break

    # None removes any existing expression (despite mypy complaining that None is not allowed)
    target.setExpression(target_name, expression)
    # Even if we set an expression, we have to copy the value (or we
    # could recompute the object, but this is cheaper).
    setattr(target, target_name, getattr(source, name))
