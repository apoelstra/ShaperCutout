# SPDX-License-Identifier: GPL-3.0-or-later

from typing import Callable, List, Optional, Tuple
from PySide import QtCore, QtWidgets

import FreeCAD as App
import FreeCADGui as Gui

import shaper_cutout_util
from shaper_cutout_util import Objects, ShaperCutoutType, force_combo_to_value


class TaskPanelRejected(Exception):
    """Raised by ShaperTaskPanel when the create flow declines to proceed
    (e.g. an invalid selection). The subclass has already informed the user
    why; the open_* helper should swallow this and not show the dialog."""


class LinkWidget:
    """A combo-box widget which controls a PropertyLink property."""

    def __init__(
        self,
        ty: ShaperCutoutType,
        none_item: Optional[str],
        all_doc_objects: Objects,
        labelfn: Callable[[App.DocumentObject], Optional[str]],
    ):
        self._ty = ty
        self._none_item = none_item
        self._labelfn = labelfn

        self._widget = QtWidgets.QComboBox()
        self._refresh(all_doc_objects)

    def _refresh(self, all_doc_objects: Objects):
        previous = self._widget.currentData()

        self._widget.clear()
        if self._none_item is not None:
            self._widget.addItem(self._none_item, None)

        idx = 1
        for obj in all_doc_objects.dict[self._ty]:
            label = self._labelfn(obj)
            if label is not None:
                self._widget.addItem(label, obj)
                if previous == obj:
                    self._widget.setCurrentIndex(idx)
                idx += 1


class ShaperTaskPanel:
    """A Task Panel used to create or edit a ShaperCutout object.

    Task panels should subclass this and must provide the following methods:

    def create_uninitialized_object(self) -> App.DocumentObject
       - when creating a new object, looks at the GUI selection or
         whatever and creates an empty object

    def recompute_objects(self, updated_prop_name: str)
       - recomputes relevant document objects to show a live display of changes
    """
    def __init__(self, name: str, doc_object: Optional[App.DocumentObject] = None):
        assert App.ActiveDocument is not None

        self._doc = App.ActiveDocument
        self._edit_mode = doc_object is not None
        self._initialized = False

        action = "Edit" if self._edit_mode else "Create"
        self._doc.openTransaction(f"{action} {name}")

        if self._edit_mode:
            assert doc_object is not None
            self._object = doc_object
        else:
            obj = self.create_uninitialized_object()
            if obj is None:
                # The create flow declined to proceed (e.g. invalid selection);
                # the subclass has already told the user why. Undo the
                # transaction we just opened and unwind, instead of crashing
                # below on self._object.Label with the transaction leaked open.
                self._doc.abortTransaction()
                raise TaskPanelRejected()
            self._object = obj

        # Build UI
        self.form = QtWidgets.QWidget()
        self.form.setWindowTitle(f"{action} {name}")

        # Label
        self._main_layout = QtWidgets.QFormLayout(self.form)
        self.label_edit = QtWidgets.QLineEdit()
        self.label_edit.setText(self._object.Label)
        self.label_edit.setEnabled(not self._edit_mode)
        self.label_edit.textChanged.connect(self._on_label_changed)
        self._main_layout.addRow("Label:", self.label_edit)

    def create_uninitialized_object(self) -> Optional[App.DocumentObject]:
        raise NotImplementedError

    def _on_label_changed(self):
        if not self._edit_mode:
            label = self.label_edit.text().strip()
            self._object.Label = label

    def _quantity_widget(self, prop_name, minimum=None, maximum=None):
        widget = Gui.UiLoader().createWidget('Gui::QuantitySpinBox')
        if minimum is not None:
            widget.setProperty('minimum', minimum)
        if maximum is not None:
            widget.setProperty('maximum', maximum)

        Gui.ExpressionBinding(widget).bind(self._object, prop_name)
        widget.setProperty('value', getattr(self._object, prop_name))
        QtCore.QObject.connect(
            widget,
            QtCore.SIGNAL("valueChanged(Base::Quantity)"),
            lambda value, p=prop_name: self._on_quantity_changed(p, value),
        )
        return widget

    def _on_quantity_changed(self, prop_name, value):
        setattr(self._object, prop_name, value)
        self.recompute_objects(prop_name)

    def _link_widget(
        self,
        prop_name: str,
        ty: ShaperCutoutType,
        none_item: Optional[str] = None,
        all_doc_objects: Optional[Objects] = None,
        selected_value: Optional[App.DocumentObject] = None,
        labelfn: Callable[[App.DocumentObject], Optional[str]] = lambda x: x.Label,
    ) -> LinkWidget:
        initial_value = None
        if getattr(self._object, prop_name, None) is not None:
            initial_value = getattr(self._object, prop_name)
        else:
            initial_value = selected_value

        widget = LinkWidget(ty, none_item, all_doc_objects, labelfn)
        if initial_value is not None:
            force_combo_to_value(widget._widget, initial_value)
            self._on_link_changed(prop_name, widget)

        widget._widget.currentIndexChanged.connect(lambda: self._on_link_changed(prop_name, widget))
        return widget

    def _on_link_changed(self, prop_name, link_widget):
        setattr(self._object, prop_name, link_widget._widget.currentData())
        self.recompute_objects(prop_name)

    def accept(self):
        self._doc.commitTransaction()
        Gui.Control.closeDialog()

    def reject(self):
        self._doc.abortTransaction()
        Gui.Control.closeDialog()
