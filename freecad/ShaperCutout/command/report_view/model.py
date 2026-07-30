# SPDX-License-Identifier: GPL-3.0-or-later

from typing import Callable

import FreeCAD as App
from PySide import QtCore, QtWidgets


class ReportTableModel(QtCore.QAbstractTableModel):
    def __init__(
        self,
        data_columns: [(
            str,
            Callable[[App.DocumentObject], str | App.Units.Quantity],
        )] = []
    ):
        super().__init__()
        self._doc_objs = []
        self._data_columns = data_columns
        self._check_states = {}
        self._sort_column = 0
        self._sort_order = QtCore.Qt.AscendingOrder

    def rowCount(self, parent=QtCore.QModelIndex()):
        return len(self._doc_objs)

    def columnCount(self, parent=QtCore.QModelIndex()):
        # +1 we because we add a checkbox column
        return 1 + len(self._data_columns)

    def data(self, index, role=QtCore.Qt.DisplayRole):
        if not index.isValid():
            return None

        row = index.row()
        col = index.column()
        obj = self._doc_objs[row]

        if role == QtCore.Qt.DisplayRole:
            if col == 0:
                pass
            else:
                _, computefn = self._data_columns[col - 1]
                data = computefn(obj)
                if isinstance(data, str):
                    return data
                else:
                    schema = App.Units.getSchema()
                    return App.Units.schemaTranslate(data, schema)[0]
        elif role == QtCore.Qt.CheckStateRole:
            if col == 0:
                return self._check_states.get(obj, QtCore.Qt.Unchecked)
        elif role == QtCore.Qt.TextAlignmentRole:
            return QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter

        return None

    def headerData(self, section, orientation, role=QtCore.Qt.DisplayRole):
        if role == QtCore.Qt.DisplayRole and orientation == QtCore.Qt.Horizontal:
            if section == 0:
                return ""
            else:
                title, _ = self._data_columns[section - 1]
                return title
        return None

    def flags(self, index):
        if not index.isValid():
            return QtCore.Qt.NoItemFlags
        flags = QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable
        if index.column() == 0:
            flags |= QtCore.Qt.ItemIsUserCheckable
        return flags

    def setData(self, index, value, role=QtCore.Qt.EditRole):
        if role == QtCore.Qt.CheckStateRole and index.column() == 0:
            obj = self._doc_objs[index.row()]
            self._check_states[obj] = QtCore.Qt.CheckState(value)
            self._emit_data_changed([QtCore.Qt.CheckStateRole])
            return True
        return False

    def sort(self, column, order=QtCore.Qt.AscendingOrder):
        self._sort_column = column
        self._sort_order = order

        def get_sort_key(obj):
            if column == 0:  # Checkbox column - sort by check state
                return self._check_states.get(obj, QtCore.Qt.Unchecked)
            else:
                _, computefn = self._data_columns[column - 1]
                data = computefn(obj)
                if isinstance(data, str):
                    return data.lower()
                else:
                    return data.Value
            return ""

        reverse = (order == QtCore.Qt.DescendingOrder)
        self.layoutAboutToBeChanged.emit()
        self._doc_objs.sort(key=get_sort_key, reverse=reverse)
        self.layoutChanged.emit()

    def _emit_data_changed(self, roles: [QtCore.Qt.ItemDataRole]):
        if self._doc_objs:
            top_left = self.index(0, 0)
            bottom_right = self.index(self.rowCount() - 1, self.columnCount() - 1)
            self.dataChanged.emit(top_left, bottom_right, roles)

    def setDocumentObjects(self, doc_objs):
        self.beginResetModel()
        self._doc_objs = doc_objs
        self._check_states = {}
        self.endResetModel()

    def getCheckedObjects(self) -> [App.DocumentObject]:
        return [obj for obj in self._doc_objs
                if self._check_states.get(obj, QtCore.Qt.Unchecked) == QtCore.Qt.Checked]

    def setAllCheckStates(self, state: QtCore.Qt.CheckState):
        for obj in self._doc_objs:
            self._check_states[obj] = state
        self._emit_data_changed([QtCore.Qt.CheckStateRole])


class ReportTableWidget(QtWidgets.QGroupBox):
    checkedStateChanged = QtCore.Signal(list)

    def __init__(self, model: QtCore.QAbstractTableModel):
        super().__init__("")
        self.setFlat(True)
        layout = QtWidgets.QVBoxLayout(self)

        # Check all checkbox
        self.check_all_checkbox = QtWidgets.QCheckBox("Check All Boxes")
        self.check_all_checkbox.checkStateChanged.connect(self._on_check_all)
        layout.addWidget(self.check_all_checkbox)

        # Table
        self._table_widget = QtWidgets.QTableView()
        self._table_widget.horizontalHeader().setSectionsClickable(True)
        self._table_widget.horizontalHeader().setSortIndicatorShown(True)
        self._table_widget.horizontalHeader().sortIndicatorChanged.connect(
            self._on_sort_indicator_changed
        )
        self._table_widget.setSortingEnabled(True)
        self._table_widget.verticalHeader().setVisible(False)
        self._table_widget.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self._table_widget.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self._table_widget.setShowGrid(False)
        self._table_widget.setAlternatingRowColors(True)

        # Set up model
        self._model = model
        self._table_widget.setModel(self._model)
        self._model.dataChanged.connect(self._on_model_data_changed)

        # Configure header
        header = self._table_widget.horizontalHeader()
        for col in range(self._model.columnCount()):
            if col == 1:
                # Treat the "name" column specially for resizing.
                header.setSectionResizeMode(col, QtWidgets.QHeaderView.Stretch)
            else:
                header.setSectionResizeMode(col, QtWidgets.QHeaderView.ResizeToContents)

        layout.addWidget(self._table_widget)

    def populate(self, objs):
        self._model.setDocumentObjects(objs)
        self._update_checked_state()

    def refresh_display(self):
        self._model._emit_data_changed([QtCore.Qt.DisplayRole])

    def get_checked_objects(self) -> [App.DocumentObject]:
        return self._model.getCheckedObjects()

    def _on_check_all(self, state):
        if state == QtCore.Qt.Checked or state == QtCore.Qt.Unchecked:
            self._model.setAllCheckStates(state)
            self._update_checked_state()

    def _on_sort_indicator_changed(self, column, order):
        self._model.sort(column, order)

    def _on_model_data_changed(self, top_left, bottom_right, roles):
        if QtCore.Qt.CheckStateRole in roles:
            self._update_checked_state()

    def _update_checked_state(self):
        checked = self.get_checked_objects()

        total_rows = self._model.rowCount()
        if total_rows == 0:
            self.check_all_checkbox.setCheckState(QtCore.Qt.Unchecked)
            self.check_all_checkbox.setEnabled(False)
        else:
            self.check_all_checkbox.setEnabled(True)
            if len(checked) == total_rows:
                self.check_all_checkbox.setCheckState(QtCore.Qt.Checked)
                self.check_all_checkbox.setTristate(False)
            elif len(checked) == 0:
                self.check_all_checkbox.setCheckState(QtCore.Qt.Unchecked)
                self.check_all_checkbox.setTristate(False)
            else:
                self.check_all_checkbox.setTristate(True)
                self.check_all_checkbox.setCheckState(QtCore.Qt.PartiallyChecked)

        self.checkedStateChanged.emit(checked)
