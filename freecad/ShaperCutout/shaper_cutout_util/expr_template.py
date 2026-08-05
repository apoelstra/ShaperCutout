# SPDX-License-Identifier: GPL-3.0-or-later

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore

from .misc import copy_property


class _ExprTemplate:
    def __init__(self, obj):
        obj.Proxy = self
        obj.ViewObject.Proxy = 0
        obj.ViewObject.ShowInTree = False

        self._template = obj

    def dumps(self): return None
    def loads(self, state): return None

    def update_object(self, obj, prop):
        copy_property(self._template, obj, prop)

    def bind(self, widget, prop, initial_value):
        setattr(self._template, prop, initial_value)
        Gui.ExpressionBinding(widget).bind(self._template, prop)
        widget.setProperty('value', getattr(self._template, prop))
        QtCore.QObject.connect(
            widget,
            QtCore.SIGNAL("valueChanged(Base::Quantity)"),
            lambda value, p=prop: self._on_quantity_changed(p, value),
        )

    def _on_quantity_changed(self, prop_name, value):
        setattr(self._template, prop_name, value)

    def destroyTemplate(self):
        self._template.Document.removeObject(self._template)


def make_expr_template(prop_dict):
    obj = App.ActiveDocument.addObject('App::FeaturePython', '_ExprTemplate')
    for key in prop_dict:
        obj.addProperty(prop_dict[key], key)
    return _ExprTemplate(obj)
