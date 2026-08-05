# SPDX-License-Identifier: GPL-3.0-or-later

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore

from .misc import copy_property


class _ExprTemplate:
    def __init__(self, obj, prop_dict):
        obj.Proxy = self
        obj.ViewObject.Proxy = 0
        obj.ViewObject.ShowInTree = False

        for key in prop_dict:
            obj.addProperty(prop_dict[key], key)

        self._template = obj
        self._widgets = {}

    def dumps(self): return None
    def loads(self, state): return None

    def update_object(self, obj, prop):
        copy_property(self._template, obj, prop)

    def bind(self, widget, prop):
        self._widgets[prop] = widget
        Gui.ExpressionBinding(widget).bind(self._template, prop)
        widget.setProperty('value', getattr(self._template, prop))
        QtCore.QObject.connect(
            widget,
            QtCore.SIGNAL("valueChanged(Base::Quantity)"),
            lambda value, p=prop: self._on_quantity_changed(p, value),
        )

    def _on_quantity_changed(self, prop_name, value):
        setattr(self._template, prop_name, value)

    def widget_value(self, prop: str) -> App.Units.Quantity:
        for name, e in self._template.ExpressionEngine:
            if name == prop:
                return self._template.evalExpression(e)

        widget = self._widgets.get(prop)
        if widget is not None:
            return App.Units.Quantity(widget.text())
        else:
            return getattr(self._template, prop)

    def destroyTemplate(self):
        self._template.Document.removeObject(self._template)


def make_expr_template(prop_dict):
    obj = App.ActiveDocument.addObject('App::FeaturePython', '_ExprTemplate')
    return _ExprTemplate(obj, prop_dict)
