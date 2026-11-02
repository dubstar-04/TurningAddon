"""Qt membership editor for native turning tool libraries."""

from PySide import QtCore, QtGui

from . import freecad as assets
from .iso_gui import IsoToolDialog, IsoToolEditDialog
from .library import ToolLibrary


translate = QtCore.QCoreApplication.translate


class LibraryDialog(QtGui.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.snapshot = None
        self.table = ToolLibrary()
        self.document_name = None
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
        self.new_tool_button = self._button(
            "document-new", QtGui.QStyle.SP_FileIcon,
            translate("CAM", "New ISO ToolBit"), self.create_iso_tool)
        self.add_button = self._button(
            "list-add", QtGui.QStyle.SP_FileDialogNewFolder,
            translate("CAM", "Add existing ToolBit"), self.add_tool)
        self.edit_button = self._button(
            "document-edit", QtGui.QStyle.SP_FileDialogContentsView,
            translate("CAM", "Edit ToolBit"), self.edit_tool)
        self.remove_button = self._button(
            "list-remove", QtGui.QStyle.SP_TrashIcon,
            translate("CAM", "Remove from library"), self.remove_tool)
        self.renumber_button = self._button(
            "document-edit", QtGui.QStyle.SP_FileDialogDetailedView,
            translate("CAM", "Renumber tool"), self.renumber_tool)
        for button in (self.new_tool_button, self.add_button, self.edit_button, self.remove_button, self.renumber_button):
            actions.addWidget(button)
        actions.addStretch()
        layout.addLayout(actions)

        job_row = QtGui.QHBoxLayout()
        job_row.addWidget(QtGui.QLabel(translate("CAM", "Job")))
        self.jobs = QtGui.QComboBox()
        self.jobs.setSizeAdjustPolicy(QtGui.QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.jobs.setMinimumContentsLength(12)
        job_row.addWidget(self.jobs, 1)
        job_row.addWidget(self._button(
            "view-refresh", QtGui.QStyle.SP_BrowserReload,
            translate("CAM", "Reload CAM jobs"), self.refresh_jobs))
        self.job_button = QtGui.QPushButton(translate("CAM", "Add to job"))
        self.job_button.setIcon(QtGui.QIcon.fromTheme(
            "list-add", self.style().standardIcon(QtGui.QStyle.SP_ArrowForward)))
        self.job_button.setAutoDefault(False)
        self.job_button.clicked.connect(self.add_to_job)
        job_row.addWidget(self.job_button)
        layout.addLayout(job_row)
        self.job_status = QtGui.QLabel()
        self.job_status.setWordWrap(True)
        self.job_status.setTextFormat(QtCore.Qt.PlainText)
        layout.addWidget(self.job_status)

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
        layout.addWidget(self.buttons)
        self.rows.itemSelectionChanged.connect(self._update_actions)
        self.libraries.currentIndexChanged.connect(self.open_library)
        self.jobs.currentIndexChanged.connect(self._update_job_state)
        self._update_actions()
        self.refresh_jobs()
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
        self.new_tool_button.setEnabled(editable)
        self.add_button.setEnabled(editable)
        self.edit_button.setEnabled(editable and selected)
        self.remove_button.setEnabled(editable and selected)
        self.renumber_button.setEnabled(editable and selected)
        self.save_button.setEnabled(editable and self._dirty())
        self.setWindowModified(self._dirty())
        self._update_job_state()

    def _update_job_state(self):
        number = self._selected_number()
        if self.snapshot is None or number is None:
            problem = translate("CAM", "Select a library tool.")
        elif self.snapshot.issues:
            problem = translate("CAM", "Resolve library dependency issues before adding to a job.")
        else:
            problem = assets.job_add_problem(self.document_name, self.jobs.currentData(), number)
        self.job_button.setEnabled(problem is None)
        self.job_status.setText(problem or "")
        self.job_button.setToolTip(problem or translate("CAM", "Add the selected ToolBit using its library number"))

    def refresh_jobs(self):
        previous = self.jobs.currentData()
        previous_document = self.document_name
        try:
            document, choices, preferred = assets.job_choices()
        except (OSError, ValueError, RuntimeError) as error:
            self._report_error(error)
            return
        self.jobs.blockSignals(True)
        self.jobs.clear()
        self.jobs.addItem(translate("CAM", "Select a CAM job"), None)
        for name, label in choices:
            self.jobs.addItem(f"{label} ({name})", name)
        selected = previous if document == previous_document and self.jobs.findData(previous) > 0 else preferred
        self.jobs.setCurrentIndex(max(0, self.jobs.findData(selected)))
        self.document_name = document
        self.jobs.blockSignals(False)
        self._update_job_state()

    def add_to_job(self):
        if not self.job_button.isEnabled():
            return
        entry = self.table.get(self._selected_number())
        try:
            controller = assets.add_to_job(entry, self.document_name, self.jobs.currentData())
        except (OSError, ValueError, RuntimeError) as error:
            self._report_error(error)
            self._update_job_state()
            return
        self._update_job_state()
        self.status.setText(translate(
            "CAM", "Added tool {number} to {job}. Set feeds and spindle speed in its controller before use.").format(
                number=controller.ToolNumber, job=self.jobs.currentText()))

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

    def create_iso_tool(self):
        if not self.new_tool_button.isEnabled():
            return
        try:
            dialog = IsoToolDialog(assets.load_iso_form(), self)
            if dialog.form.exec_() != QtGui.QDialog.Accepted:
                return
            entry = assets.create_iso_tool(*dialog.selection(), self.table.next_number)
            self.table.add(entry)
        except (OSError, ValueError, RuntimeError) as error:
            self._report_error(error)
            return
        self._render(entry.number)
        self.status.setText(translate("CAM", "ToolBit saved; library membership has unsaved changes."))

    def edit_tool(self):
        if not self.edit_button.isEnabled():
            return
        number = self._selected_number()
        entry = self.table.get(number)
        try:
            snapshot = assets.load_iso_tool(entry.tool_id)
            dialog = IsoToolEditDialog(snapshot.values, self)
            if dialog.exec_() != QtGui.QDialog.Accepted:
                return
            values = dialog.values()
            if values == snapshot.values:
                return
            answer = QtGui.QMessageBox.question(
                self, translate("CAM", "Edit shared ToolBit"),
                translate("CAM", "Save changes to this ToolBit? Every library referencing it will use the updated definition."),
                QtGui.QMessageBox.Yes | QtGui.QMessageBox.Cancel, QtGui.QMessageBox.Cancel,
            )
            if answer != QtGui.QMessageBox.Yes:
                return
            updated = assets.save_iso_tool(snapshot, values)
        except (OSError, ValueError, RuntimeError) as error:
            self._report_error(error)
            return
        for table in (self.table, self.snapshot.table):
            for member in table.entries:
                if member.tool_id == updated.uri:
                    table.edit(member.number, name=updated.attributes["name"])
        self.snapshot.tools[entry.tool_id] = updated.attributes
        self._render(number)
        self.status.setText(translate("CAM", "Shared ToolBit changes saved."))

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