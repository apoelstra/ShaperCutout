# SPDX-License-Identifier: GPL-3.0-or-later

import FreeCAD as App
import FreeCADGui as Gui

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

    def setExpression(self, prop, expr):
        """Passthrough to the setExpression method on the underlying engine."""
        self._template.setExpression(prop, expr)

    def clearExpression(self, prop):
        """Passthrough to the clearExpression method on the underlying engine."""
        self._template.clearExpression(prop)

    def set_from_object(self, obj, prop, default=None):
        if obj is None:
            if default is not None:
                setattr(self._template, prop, default)
            return

        setattr(self._template, prop, getattr(obj, prop))
        for obj_prop, obj_expr in obj.ExpressionEngine:
            if obj_prop == prop:
                self._template.setExpression(prop, obj_expr)
                return
        self._template.clearExpression(prop)

    def update_object(self, obj, prop):
        widget = self._widgets.get(prop)
        if widget is None:
            setattr(obj, prop, getattr(self._template, prop))
        else:
            setattr(obj, prop, widget.text())

        for name, e in self._template.ExpressionEngine:
            if name == prop:
                setattr(obj, prop, obj.evalExpression(e))
                obj.setExpression(prop, e)
                return
        obj.clearExpression(prop)

    def bind(self, widget, prop):
        self._widgets[prop] = widget
        Gui.ExpressionBinding(widget).bind(self._template, prop)

        for name, e in self._template.ExpressionEngine:
            if name == prop:
                evaluated = self._template.evalExpression(e)
                widget.lineEdit().setText(f'{evaluated}')
                return
        widget.lineEdit().setText(f'{getattr(self._template, prop)}')

    def widget_value(self, prop):
        for name, e in self._template.ExpressionEngine:
            if name == prop:
                return self._template.evalExpression(e)

        widget = self._widgets.get(prop)
        if widget is not None:
            return widget.text()
        else:
            return getattr(self._template, prop)

    def destroyTemplate(self):
        self._template.Document.removeObject(self._template)


def make_expr_template(prop_dict):
    obj = App.ActiveDocument.addObject('App::FeaturePython', '_ExprTemplate')
    return _ExprTemplate(obj, prop_dict)


def template_expr(template):
    """Return expr_string or None from a template object."""
    return None
