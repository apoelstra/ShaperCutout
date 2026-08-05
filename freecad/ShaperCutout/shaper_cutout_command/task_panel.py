# SPDX-License-Identifier: GPL-3.0-or-later

from typing import Optional
from PySide import QtCore, QtWidgets

import FreeCAD as App
import FreeCADGui as Gui


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
        self._doc = App.ActiveDocument
        self._edit_mode = doc_object is not None
        self._initialized = False

        action = "Edit" if self._edit_mode else "Create"
        self._doc.openTransaction(f"{action} {name}")

        if self._edit_mode:
            self._object = doc_object
        else:
            self._object = self.create_uninitialized_object()

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

    def accept(self):
        self._doc.commitTransaction()
        Gui.Control.closeDialog()

    def reject(self):
        self._doc.abortTransaction()
        Gui.Control.closeDialog()
