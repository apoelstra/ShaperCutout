# SPDX-License-Identifier: GPL-3.0-or-later

"""'Add Custom Anchor' dialog for a ShaperSvgPage.

Lets the user place the page's custom anchor either
  * automatically, using the best-90-degree-corner algorithm on one of the
    page's cutouts, or
  * interactively on the page view, at a vertex (or circle center), or at the
    intersection of two edges.
"""

from PySide import QtWidgets


def _page_view_widget(page_obj):
    """Ensure the page's MDI view is open and return its _PageWidget."""
    vobj = page_obj.ViewObject
    if vobj is None or vobj.Proxy is None:
        return None
    vobj.Proxy._open_view(page_obj)
    if not vobj.Proxy._subwindow_alive():
        return None
    return vobj.Proxy._subwindow.widget()


class AddAnchorDialog(QtWidgets.QDialog):
    def __init__(self, page_obj, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add Custom Anchor")
        self._page_obj = page_obj

        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(QtWidgets.QLabel("Custom anchor on object:"))

        self.list_widget = QtWidgets.QListWidget()
        for child in page_obj.Group:
            if hasattr(child.Proxy, 'anchor_wires'):
                self.list_widget.addItem(child.Label)
        if self.list_widget.count() > 0:
            self.list_widget.setCurrentRow(0)
        layout.addWidget(self.list_widget)

        buttons = QtWidgets.QHBoxLayout()
        self.auto_button = QtWidgets.QPushButton("Automatically Place On")
        self.auto_button.setToolTip(
            "Place the anchor at the best 90-degree corner of the selected object")
        self.auto_button.clicked.connect(self._on_auto)
        self.auto_button.setEnabled(self.list_widget.count() > 0)
        buttons.addWidget(self.auto_button)

        self.vertex_button = QtWidgets.QPushButton("Place at Vertex")
        self.vertex_button.setToolTip(
            "Click a vertex or circle center on the page view")
        self.vertex_button.clicked.connect(lambda: self._on_interactive('vertex'))
        buttons.addWidget(self.vertex_button)

        self.intersect_button = QtWidgets.QPushButton("Place at Intersection")
        self.intersect_button.setToolTip(
            "Click two edges on the page view; the anchor is placed at their "
            "intersection")
        self.intersect_button.clicked.connect(
            lambda: self._on_interactive('intersection'))
        buttons.addWidget(self.intersect_button)
        layout.addLayout(buttons)

        hint = QtWidgets.QLabel(
            "In interactive modes, use the mouse scroll wheel to rotate the "
            "anchor preview (15 degrees, or 1 degree with Shift held); press "
            "Esc or right-click to cancel.")
        hint.setWordWrap(True)
        layout.addWidget(hint)

    def _selected_child(self):
        row = self.list_widget.currentRow()
        if row < 0:
            return None
        label = self.list_widget.item(row).text()
        for child in self._page_obj.Group:
            if child.Label == label:
                return child
        return None

    def _on_auto(self):
        child = self._selected_child()
        if child is None:
            return
        if not self._page_obj.Proxy.auto_place_anchor(self._page_obj, child):
            QtWidgets.QMessageBox.warning(
                self, "No Anchor Found",
                f"No 90-degree corner found on '{child.Label}'.")
            return
        self._page_obj.touch()
        self._page_obj.Document.recompute()
        self.accept()

    def _on_interactive(self, mode):
        widget = _page_view_widget(self._page_obj)
        if widget is None:
            QtWidgets.QMessageBox.warning(
                self, "Page View Needed",
                "Could not open the page view; double-click the page first.")
            return
        # Hide (rather than close) so the page view is unobstructed while the
        # user clicks; they can close this dialog when done.
        self.hide()
        widget.start_anchor_placement(mode)
        widget.setFocus()


def open_add_anchor_dialog(page_obj):
    dialog = AddAnchorDialog(page_obj)
    dialog.show()
    return dialog
