# SPDX-License-Identifier: GPL-3.0-or-later

import FreeCADGui as Gui


def move_to_root(obj):
    """Remove obj from any group, placing it at document root."""
    for o in obj.InList:
        if hasattr(o, 'Group') and obj in o.Group:
            grp = list(o.Group)
            grp.remove(obj)
            o.Group = grp


def insert_if_missing(container, obj):
    if obj is not None and obj not in container.Group:
        move_to_root(obj)
        grp = list(container.Group)
        grp.insert(0, obj)
        container.Group = grp


def __check_selection(sel, type_attr):
    if isinstance(type_attr, str):
        return getattr(sel, 'TypeId', None) == type_attr or getattr(sel, 'Type', None) == type_attr
    elif isinstance(type_attr, list):
        return getattr(sel, 'TypeId', None) in type_attr or getattr(sel, 'Type', None) in type_attr
    else:
        raise TypeError(f'cannot check selection against object of type {type(type_attr)}')


def force_combo_to_value(combo_widget, val):
    """Selects an object from a combo box, adding it at the top if it does not exist."""
    idx = combo_widget.findData(val)
    if idx < 0:
        combo_widget.insertItem(0, val.Label, val)
        idx = 0
    combo_widget.setCurrentIndex(idx)


def is_single_selected(type_attr):
    sel = Gui.Selection.getSelection()
    return len(sel) == 1 and __check_selection(sel[0], type_attr)


def are_exclusively_selected(type_attr):
    sel = Gui.Selection.getSelection()
    return len(sel) > 0 and all(__check_selection(sel, type_attr) for sel in sel)
