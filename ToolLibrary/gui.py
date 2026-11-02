"""Qt membership editor for native turning tool libraries."""

from PySide import QtCore, QtGui

from . import freecad as assets
from .library import ToolLibrary


translate = QtCore.QCoreApplication.translate


class LibraryDialog(QtGui.QDialog):
    def __init__(self, parent=None, iso_helper=None):
        super().__init__(parent)
        self.snapshot = None
        self.table = ToolLibrary()
        self.setWindowTitle(translate("CAM", "Turning Tool Library") + "[*]")
        self.resize(720, 440)
        self.setMinimumSize(480, 320)
        layout = QtGui.QVBoxLayout(self)

        selector = QtGui.QHBoxLayout()
        selector.addWidget(QtGui.QLabel(translate("CAM", "Library")))
        self.libraries = QtGui.QComboBox()
        self.libraries.setSizeAdjustPolicy(QtGui.QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.libraries.setMinimumContentsLength(12)
        selector.addWidget(self.libraries, 1)
        selector.addWidget(self._button(
            "document-new", QtGui.QStyle.SP_FileIcon,
            translate("CAM", "New library"), self.create_library))
        selector.addWidget(self._button(
            "view-refresh", QtGui.QStyle.SP_BrowserReload,
            translate("CAM", "Reload libraries"), self.reload_libraries))
        layout.addLayout(selector)

        self.rows = QtGui.QTableWidget(0, 3)
        self.rows.setHorizontalHeaderLabels([
            translate("CAM", "Number"), translate("CAM", "Name"),
            translate("CAM", "Shape"),
        ])
        self.rows.setSelectionBehavior(QtGui.QAbstractItemView.SelectRows)
        self.rows.setSelectionMode(QtGui.QAbstractItemView.SingleSelection)
        self.rows.setEditTriggers(QtGui.QAbstractItemView.NoEditTriggers)
        self.rows.verticalHeader().hide()
        header = self.rows.horizontalHeader()
        header.setSectionResizeMode(0, QtGui.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QtGui.QHeaderView.Stretch)
        header.setSectionResizeMode(2, QtGui.QHeaderView.ResizeToContents)
        layout.addWidget(self.rows, 1)

        actions = QtGui.QHBoxLayout()
        self.add_button = self._button(
            "list-add", QtGui.QStyle.SP_FileDialogNewFolder,
            translate("CAM", "Add existing ToolBit"), self.add_tool)
        self.remove_button = self._button(
            "list-remove", QtGui.QStyle.SP_TrashIcon,
            translate("CAM", "Remove from library"), self.remove_tool)
        self.renumber_button = self._button(
            "document-edit", QtGui.QStyle.SP_FileDialogDetailedView,
            translate("CAM", "Renumber tool"), self.renumber_tool)
        for button in (self.add_button, self.remove_button, self.renumber_button):
            actions.addWidget(button)
        actions.addStretch()
        layout.addLayout(actions)

        self.status = QtGui.QLabel()
        self.status.setWordWrap(True)
        self.status.setTextFormat(QtCore.Qt.PlainText)
        layout.addWidget(self.status)
        self.buttons = QtGui.QDialogButtonBox(
            QtGui.QDialogButtonBox.Save | QtGui.QDialogButtonBox.Close)
        self.save_button = self.buttons.button(QtGui.QDialogButtonBox.Save)
        self.save_button.setAutoDefault(False)
        self.save_button.clicked.connect(self.save_library)
        self.buttons.rejected.connect(self.reject)
        if iso_helper is not None:
            helper_button = self.buttons.addButton(
                translate("CAM", "ISO tool helper..."), QtGui.QDialogButtonBox.ActionRole)
            helper_button.setAutoDefault(False)
            helper_button.clicked.connect(iso_helper)
        layout.addWidget(self.buttons)
        self.rows.itemSelectionChanged.connect(self._update_actions)
        self.libraries.currentIndexChanged.connect(self.open_library)
        self._update_actions()
        self.reload_libraries()

    def _button(self, icon, fallback, text, callback):
        button = QtGui.QToolButton()
        button.setIcon(QtGui.QIcon.fromTheme(icon, self.style().standardIcon(fallback)))
        button.setToolTip(text)
        button.setAccessibleName(text)
        button.clicked.connect(callback)
        return button

    def _dirty(self):
        return self.snapshot is not None and self.table.entries != self.snapshot.table.entries

    def _selected_number(self):
        row = self.rows.currentRow()
        return self.rows.item(row, 0).data(QtCore.Qt.UserRole) if row >= 0 else None

    def _update_actions(self):
        writable = assets.library_location()["writable"]
        editable = self.snapshot is not None and not self.snapshot.issues and writable
        selected = self._selected_number() is not None
        self.add_button.setEnabled(editable)
        self.remove_button.setEnabled(editable and selected)
        self.renumber_button.setEnabled(editable and selected)
        self.save_button.setEnabled(editable and self._dirty())
        self.setWindowModified(self._dirty())

    def _render(self, selected_number=None):
        entries = self.table.entries
        self.rows.setRowCount(0)
        self.rows.setRowCount(len(entries))
        for row, entry in enumerate(entries):
            for column, value in enumerate((str(entry.number), entry.name, entry.shape)):
                item = QtGui.QTableWidgetItem(value)
                item.setToolTip(entry.tool_id)
                if column == 0:
                    item.setData(QtCore.Qt.UserRole, entry.number)
                self.rows.setItem(row, column, item)
            if entry.number == selected_number:
                self.rows.selectRow(row)
        if self.snapshot is None:
            message = translate("CAM", "No library selected.")
        elif self.snapshot.issues:
            message = "\n".join(self.snapshot.issues)
        elif not assets.library_location()["writable"]:
            message = translate("CAM", "Library location is read-only.")
        else:
            message = assets.library_location()["path"]
        self.status.setText(message)
        self._update_actions()

    def _report_error(self, error):
        message = str(error)
        self.status.setText(message)
        QtGui.QMessageBox.warning(self, translate("CAM", "Tool library error"), message)

    def _select_uri(self, uri):
        self.libraries.blockSignals(True)
        self.libraries.setCurrentIndex(max(0, self.libraries.findData(uri)))
        self.libraries.blockSignals(False)

    def _set_snapshot(self, snapshot):
        self.snapshot = snapshot
        self.table = ToolLibrary(snapshot.table.entries) if snapshot else ToolLibrary()
        if snapshot:
            index = self.libraries.findData(snapshot.uri)
            if index < 0:
                self.libraries.addItem(snapshot.name, snapshot.uri)
                index = self.libraries.findData(snapshot.uri)
            self.libraries.setItemText(index, snapshot.name)
            self._select_uri(snapshot.uri)
        self._render()

    def _confirm_leave(self):
        if not self._dirty():
            return True
        answer = QtGui.QMessageBox.question(
            self, translate("CAM", "Unsaved library changes"),
            translate("CAM", "Save changes to the current library?"),
            QtGui.QMessageBox.Save | QtGui.QMessageBox.Discard | QtGui.QMessageBox.Cancel,
            QtGui.QMessageBox.Cancel,
        )
        if answer == QtGui.QMessageBox.Save:
            return self.save_library()
        return answer == QtGui.QMessageBox.Discard

    def reload_libraries(self):
        if not self._confirm_leave():
            return
        preferred = self.snapshot.uri if self.snapshot else assets.selected_library()
        try:
            identities = assets.list_libraries()
        except (OSError, ValueError, RuntimeError) as error:
            self._report_error(error)
            return
        self.libraries.blockSignals(True)
        self.libraries.clear()
        self.libraries.addItem(translate("CAM", "Select a library"), None)
        for uri in identities:
            self.libraries.addItem(uri, uri)
        if preferred and preferred not in identities:
            self.libraries.addItem(preferred, preferred)
        self._select_uri(preferred)
        self.libraries.blockSignals(False)
        self.open_library(self.libraries.currentIndex(), confirm=False)

    def open_library(self, index, confirm=True):
        previous = self.snapshot.uri if self.snapshot else None
        if confirm and not self._confirm_leave():
            self._select_uri(previous)
            return
        uri = self.libraries.itemData(index)
        try:
            snapshot = assets.load_library(uri) if uri else None
            if uri or previous:
                assets.set_selected_library(uri or "")
        except (OSError, ValueError, RuntimeError) as error:
            self._select_uri(previous)
            self._report_error(error)
            return
        self._set_snapshot(snapshot)

    def create_library(self):
        if not self._confirm_leave():
            return
        name, accepted = QtGui.QInputDialog.getText(
            self, translate("CAM", "New library"), translate("CAM", "Name"))
        if not accepted:
            return
        try:
            snapshot = assets.create_library(name)
            assets.set_selected_library(snapshot.uri)
        except (OSError, ValueError, RuntimeError) as error:
            self._report_error(error)
            return
        self.libraries.blockSignals(True)
        self._set_snapshot(snapshot)
        self.libraries.blockSignals(False)

    def add_tool(self):
        if not self.add_button.isEnabled():
            return
        try:
            available = tuple(uri for uri in assets.list_toolbits() if uri not in {
                entry.tool_id for entry in self.table.entries
            })
            if not available:
                raise ValueError(translate("CAM", "No additional ToolBits are available."))
            uri, accepted = QtGui.QInputDialog.getItem(
                self, translate("CAM", "Add existing ToolBit"),
                translate("CAM", "ToolBit"), available, 0, False)
            if not accepted:
                return
            entry = assets.load_tool_entry(uri, self.table.next_number)
            self.table.add(entry)
        except (OSError, ValueError, RuntimeError) as error:
            self._report_error(error)
            return
        self._render(entry.number)

    def remove_tool(self):
        if not self.remove_button.isEnabled():
            return
        number = self._selected_number()
        answer = QtGui.QMessageBox.question(
            self, translate("CAM", "Remove from library"),
            translate("CAM", "Remove tool {number} from this library? Shared ToolBit and ToolShape files will not be deleted.").format(number=number),
            QtGui.QMessageBox.Yes | QtGui.QMessageBox.No, QtGui.QMessageBox.No,
        )
        if answer == QtGui.QMessageBox.Yes:
            self.table.remove(number)
            self._render()

    def renumber_tool(self):
        if not self.renumber_button.isEnabled():
            return
        number = self._selected_number()
        new_number, accepted = QtGui.QInputDialog.getInt(
            self, translate("CAM", "Renumber tool"), translate("CAM", "Number"),
            min(number, 2147483647), 1, 2147483647,
        )
        if not accepted:
            return
        try:
            self.table.renumber(number, new_number)
        except ValueError as error:
            self._report_error(error)
            return
        self._render(new_number)

    def save_library(self):
        if self.snapshot is None:
            return False
        try:
            snapshot = assets.save_library(self.snapshot, self.table)
        except (OSError, ValueError, RuntimeError) as error:
            self._report_error(error)
            return False
        self._set_snapshot(snapshot)
        return True

    def reject(self):
        if self._confirm_leave():
            super().reject()