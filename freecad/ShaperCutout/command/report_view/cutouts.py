# SPDX-License-Identifier: GPL-3.0-or-later

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore, QtGui, QtWidgets

from command.report_view.model import ReportTableModel, ReportTableWidget
from shaper_cutout_util import make_expr_template


class CutoutsModel(ReportTableModel):
    def __init__(self):
        def extent_str(cutout: App.DocumentObject) -> str:
            schema = App.Units.getSchema()
            w, h = cutout.Proxy.xyBoundBox(cutout)
            w = App.Units.schemaTranslate(w, schema)[0]
            h = App.Units.schemaTranslate(h, schema)[0]
            return f"{w} × {h}"

        super().__init__([
            ("Name", lambda cutout: cutout.Label),
            ("Thickness", lambda cutout: cutout.Thickness),
            ("Cutout Area", lambda cutout: cutout.Proxy.faceSurfaceArea(cutout)),
            ("Extents", extent_str)
        ])

    def sort(self, column, order=QtCore.Qt.AscendingOrder):
        if column == 4:
            # Override sort order on extents
            def sort_key(cutout):
                shape = getattr(cutout, 'Shape', None)
                if shape and shape.BoundBox:
                    bb = shape.BoundBox
                    return bb.XLength * bb.YLength * bb.ZLength
                return 0

            self.layoutAboutToBeChanged.emit()
            self._doc_objs.sort(key=sort_key, reverse=(order == QtCore.Qt.DescendingOrder))
            self.layoutChanged.emit()
        else:
            super().sort(column, order)


class ReportViewCutouts(QtGui.QWidget):
    def __init__(self, report_section):
        self._doc = App.ActiveDocument
        self._report_section = report_section

        super().__init__()
        self.initUi()

    def initUi(self):
        self.setWindowTitle("Cutouts")
        layout = QtWidgets.QVBoxLayout(self)

        # Cutouts section
        self._table = ReportTableWidget(CutoutsModel())

        # Collision/recompute row
        button_layout = QtWidgets.QVBoxLayout()
        buttons_row_layout = QtWidgets.QHBoxLayout()
        self.check_collisions_btn = QtWidgets.QPushButton("Collision Check")
        self.check_collisions_btn.clicked.connect(self._on_check_collisions)
        self.check_collisions_btn.setEnabled(False)
        buttons_row_layout.addWidget(self.check_collisions_btn)

        self.recompute_btn = QtWidgets.QPushButton("Recompute")
        self.recompute_btn.clicked.connect(self._on_recompute)
        self.recompute_btn.setEnabled(False)
        buttons_row_layout.addWidget(self.recompute_btn)
        button_layout.addLayout(buttons_row_layout)

        # Thickness row
        self.thickness_widget = Gui.UiLoader().createWidget('Gui::QuantitySpinBox')
        self.thickness_widget.setProperty('unit', 'mm')
        self.thickness_widget.setEnabled(False)
        self._template = make_expr_template({'Thickness': 'App::PropertyLength'})
        self._template.bind(self.thickness_widget, 'Thickness')

        self.apply_btn = QtWidgets.QPushButton("Update Thickness")
        self.apply_btn.clicked.connect(self._on_apply_thickness)
        self.apply_btn.setEnabled(False)
        update_data_layout = QtWidgets.QFormLayout()
        update_data_layout.setFormAlignment(QtCore.Qt.AlignCenter)
        update_data_layout.setLabelAlignment(
            QtCore.Qt.AlignRight | QtCore.Qt.AlignTrailing | QtCore.Qt.AlignVCenter)

        input_btn_layout = QtWidgets.QVBoxLayout()
        input_btn_layout.addWidget(self.thickness_widget)
        input_btn_layout.addWidget(self.apply_btn)
        update_data_layout.addRow("Thickness:", input_btn_layout)
        button_layout.addLayout(update_data_layout)

        # Populate table
        cutouts = [obj for obj in self._doc.Objects
                   if getattr(obj, 'Type', '') == 'ShaperCutout']
        self._table.populate(cutouts)

        layout.addWidget(self._table)
        layout.addLayout(button_layout)

        # Connect signals
        self._table.checkedStateChanged.connect(self._on_table_checked_state_changed)
        self.thickness_widget.valueChanged.connect(self._on_thickness_changed)

    def run_cleanup(self):
        self._template.destroyTemplate()

    def _on_table_checked_state_changed(self, checked: [App.DocumentObject]):
        has_selection = len(checked) > 0
        self.check_collisions_btn.setEnabled(has_selection)
        self.recompute_btn.setEnabled(has_selection)
        self.thickness_widget.setEnabled(has_selection)
        if has_selection:
            self._on_thickness_changed()

    def _on_check_collisions(self):
        checked = self._table.get_checked_objects()
        n = len(checked)
        report_lines = []
        found = False
        self._report_section.replace_text(f"Checking for collisions among {n} checked cutouts...")
        for i in range(n):
            for j in range(i + 1, n):
                a, b = checked[i], checked[j]
                if not a.Shape or not b.Shape:
                    continue

                bb_a = a.Shape.BoundBox
                bb_b = b.Shape.BoundBox
                if not bb_a.intersect(bb_b):
                    continue

                try:
                    common = a.Shape.common(b.Shape)
                    if common and common.Volume > 1e-4:
                        report_lines.append(
                            f"Collision: '{a.Label}' and '{b.Label}' "
                            f"intersect (volume {common.Volume:.3f})"
                        )
                        found = True
                except Exception as e:
                    report_lines.append(
                        f"Error checking '{a.Label}' vs '{b.Label}': {e}"
                    )

        if found:
            self._report_section.replace_text("\n".join(report_lines))
        else:
            self._report_section.replace_text(f"No collisions found among {n} checked cutouts.")

    def _on_thickness_changed(self):
        current_qty = self._template.widget_value('Thickness')
        if current_qty.Value < 0.0:
            self.thickness_widget.lineEdit().setText("0.0")
        self.apply_btn.setEnabled(current_qty.Value > 0.0)

    def _on_recompute(self):
        checked = self._table.get_checked_objects()
        for cutout in checked:
            cutout.recompute()
        self._table.refresh_display()
        self._report_section.replace_text(f"Recomputed {len(checked)} checked cutouts.")

    def _on_apply_thickness(self):
        checked = self._table.get_checked_objects()
        n = len(checked)
        for cutout in checked:
            self._template.update_object(cutout, 'Thickness')
            cutout.recompute()
        self._table.refresh_display()
        self._report_section.replace_text(f"Updated thickness on {n} checked cutouts."
                                          "\n(Clicking 'Cancel' will undo this.)")
