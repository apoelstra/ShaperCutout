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
    def __init__(self, obj, prop_type):
        obj.Proxy = self
        obj.ViewObject.Proxy = 0
        obj.ViewObject.ShowInTree = False
        obj.addProperty(prop_type, 'Dummy')

        self._template = obj

    def dumps(self): return None
    def loads(self, state): return None

    def set_from_object(self, obj, prop, default=None):
        if obj is None:
            if default is not None:
                self._template.Dummy = default
            return

        for obj_prop, obj_expr in obj.ExpressionEngine:
            if obj_prop == prop:
                self._template.setExpression('Dummy', obj_expr)
                return

        self._template.Dummy = getattr(obj, prop)

    def update_object(self, obj, prop):
        for name, e in self._template.ExpressionEngine:
            if name == 'Dummy':
                obj.setExpression(prop, e)
                obj.recompute()
                return

        obj.clearExpression(prop)
        if self._widget is None:
            setattr(obj, prop, self._template.Dummy)
        else:
            setattr(obj, prop, self._widget.text())

    def bind(self, widget):
        self._widget = widget
        Gui.ExpressionBinding(widget).bind(self._template, 'Dummy')

        for name, e in self._template.ExpressionEngine:
            if name == 'Dummy':
                evaluated = self._template.evalExpression(e)
                widget.lineEdit().setText(f'{evaluated}')
                return
        widget.lineEdit().setText(f'{self._template.Dummy}')

    def widget_value(self):
        for name, e in self._template.ExpressionEngine:
            if name == 'Dummy':
                return self._template.evalExpression(e)

        if self._widget is not None:
            return self._widget.text()
        else:
            return self._template.Dummy

    def destroyTemplate(self):
        self._template.Document.removeObject(self._template.Name)



def make_expr_template(prop_type='App::PropertyLength'):
    obj = App.ActiveDocument.addObject('App::FeaturePython', '_ExprTemplate')
    return _ExprTemplate(obj, prop_type)


def template_expr(template):
    """Return expr_string or None from a template object."""
    return None
