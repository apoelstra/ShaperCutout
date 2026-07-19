# SPDX-License-Identifier: GPL-3.0-or-later

import FreeCAD as App
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
        self._template.Document.removeObject(self._template.Name)


def make_expr_template(prop_dict):
    obj = App.ActiveDocument.addObject('App::FeaturePython', '_ExprTemplate')
    return _ExprTemplate(obj, prop_dict)


def template_expr(template):
    """Return expr_string or None from a template object."""
    return None
