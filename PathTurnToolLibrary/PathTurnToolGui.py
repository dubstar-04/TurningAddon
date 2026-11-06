"""Qt membership editor for native turning tool libraries."""

import math

from PySide import QtCore, QtGui

from . import PathTurnAdapter as assets
from .PathTurnToolTable import ToolLibrary


translate = QtCore.QCoreApplication.translate


def _icon(name, fallback):
    """Prefer FreeCAD's bundled icon, falling back to Qt's when FreeCAD's GUI resources are absent."""
    path = f":/icons/{name}.svg"
    if QtCore.QFile.exists(path):
        return QtGui.QIcon(path)
    return QtGui.QApplication.style().standardIcon(fallback)


class RotationSpinBox(QtGui.QDoubleSpinBox):
    """Angle field stepping 45 degrees and wrapping through 0/360."""

    def __init__(self, text, parent=None):
        import FreeCAD

        super().__init__(parent)
        self.original = text
        self.setRange(0, 359.9)
        self.setDecimals(1)
        self.setSingleStep(45)
        self.setWrapping(True)
        self.setSuffix(" deg")
        self.setValue(FreeCAD.Units.Quantity(text).Value % 360)
        self._original_value = self.value()

    def stepBy(self, steps):
        self.setValue((self.value() + steps * self.singleStep()) % 360)

    def quantity(self):
        """Keep the stored text when unchanged so editing detects no change."""
        if self.value() == self._original_value:
            return self.original
        return f"{self.value():g} deg"


class ToolPreview(QtGui.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.outlines = ()
        self.nose_centre = None
        self.active_tip = None
        self.rotation = 0.0
        self.fit_radius = 0.0
        self.x_flipped = False
        self.message = translate("CAM", "Updating preview...")
        self.setMinimumSize(240, 240)
        self.setSizePolicy(QtGui.QSizePolicy.Expanding, QtGui.QSizePolicy.Expanding)

    def set_outline(self, outlines, message="", *, nose_centre=None, fit_radius=None, active_tip=None):
        self.outlines = outlines
        self.nose_centre = nose_centre
        self.active_tip = active_tip
        points = [point for edge in outlines for point in edge]
        if nose_centre is not None:
            points.append(nose_centre)
        self.fit_radius = (fit_radius if fit_radius is not None else
                           max((math.hypot(*point) for point in points), default=0.0))
        self.message = message
        self.update()

    def set_x_flipped(self, flipped):
        self.x_flipped = flipped
        self.update()

    def paintEvent(self, _event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        palette = self.palette()
        painter.fillRect(self.rect(), palette.window())
        side = min(self.width(), self.height())
        painter.translate((self.width() - side) / 2, (self.height() - side) / 2)
        painter.fillRect(QtCore.QRectF(0, 0, side, side), palette.base())
        origin = QtCore.QPointF(side / 2, side / 2)
        x_colour = QtGui.QColor("#cc3333")
        z_colour = QtGui.QColor("#3333cc")
        painter.setPen(QtGui.QPen(z_colour, 1.5))
        painter.drawLine(QtCore.QPointF(8, origin.y()), QtCore.QPointF(side - 8, origin.y()))
        painter.drawLine(QtCore.QPointF(side - 8, origin.y()),
                         QtCore.QPointF(side - 14, origin.y() - 3))
        painter.drawLine(QtCore.QPointF(side - 8, origin.y()),
                         QtCore.QPointF(side - 14, origin.y() + 3))
        painter.drawText(QtCore.QPointF(
            side - self.fontMetrics().horizontalAdvance("+Z") - 8, origin.y() - 8), "+Z")
        painter.setPen(QtGui.QPen(x_colour, 1.5))
        painter.drawLine(QtCore.QPointF(origin.x(), 8), QtCore.QPointF(origin.x(), side - 8))
        arrow_tip = 8 if self.x_flipped else side - 8
        arrow_tail = 14 if self.x_flipped else side - 14
        painter.drawLine(QtCore.QPointF(origin.x(), arrow_tip), QtCore.QPointF(origin.x() - 3, arrow_tail))
        painter.drawLine(QtCore.QPointF(origin.x(), arrow_tip), QtCore.QPointF(origin.x() + 3, arrow_tail))
        painter.drawText(QtCore.QPointF(origin.x() + 8, 20 if self.x_flipped else side - 12), "+X")
        painter.setPen(palette.text().color())
        if not self.outlines:
            painter.drawText(QtCore.QRect(12, 12, side // 2 - 28, side // 2 - 28),
                             QtCore.Qt.AlignLeft | QtCore.Qt.TextWordWrap, self.message)
            return
        scale = (side / 2 - 32) / max(self.fit_radius, 1e-6)

        def screen(point):
            radial, axial = point
            return QtCore.QPointF(
                origin.x() + axial * scale,
                origin.y() + radial * scale * (-1 if self.x_flipped else 1))

        painter.setPen(QtGui.QPen(palette.text().color(), 2))
        for edge in self.outlines:
            painter.drawPolyline(QtGui.QPolygonF([screen(point) for point in edge]))
        if self.nose_centre is not None:
            painter.setPen(QtGui.QPen(QtGui.QColor("#178354"), 2))
            painter.setBrush(palette.base())
            painter.drawEllipse(screen(self.nose_centre), 3, 3)
        if self.active_tip is not None:
            tip = screen(self.active_tip)
            radians = math.radians(self.rotation)
            direction = QtCore.QPointF(math.cos(radians), math.sin(radians) * (-1 if self.x_flipped else 1))
            painter.setPen(QtGui.QPen(palette.highlight().color(), 1.5, QtCore.Qt.DashLine))
            painter.drawLine(tip, tip + direction * min(64, max(32, self.fit_radius * scale * 0.6)))
            painter.drawLine(tip, tip + QtCore.QPointF(26, 0))
            span = self.rotation % 360
            if span > 180:
                span -= 360
            painter.drawArc(QtCore.QRectF(tip.x() - 22, tip.y() - 22, 44, 44),
                            0, round(span * (16 if self.x_flipped else -16)))
            painter.setBrush(palette.highlight())
            painter.drawEllipse(tip, 2.5, 2.5)
        painter.setPen(QtGui.QPen(palette.highlight().color(), 2))
        painter.setBrush(palette.base())
        painter.drawEllipse(origin, 5, 5)
        painter.drawLine(origin + QtCore.QPointF(-8, 0), origin + QtCore.QPointF(8, 0))
        painter.drawLine(origin + QtCore.QPointF(0, -8), origin + QtCore.QPointF(0, 8))


def _shape_icon(outlines, palette):
    pixmap = QtGui.QPixmap(120, 96)
    pixmap.fill(QtCore.Qt.transparent)
    points = [point for edge in outlines for point in edge]
    if not points:
        raise ValueError(translate("CAM", "The ToolShape has no preview outline."))
    x_min, x_max = min(p[0] for p in points), max(p[0] for p in points)
    z_min, z_max = min(p[1] for p in points), max(p[1] for p in points)
    scale = min(72 / max(x_max - x_min, 1e-6), 96 / max(z_max - z_min, 1e-6))
    painter = QtGui.QPainter(pixmap)
    painter.setRenderHint(QtGui.QPainter.Antialiasing)
    painter.setPen(QtGui.QPen(palette.text().color(), 2))
    for edge in outlines:
        painter.drawPolyline(QtGui.QPolygonF([
            QtCore.QPointF(60 + (axial - (z_min + z_max) / 2) * scale,
                          48 + (radial - (x_min + x_max) / 2) * scale)
            for radial, axial in edge
        ]))
    painter.end()
    return QtGui.QIcon(pixmap)


def _dialog_layout(dialog):
    """Return the dialog's content layout and a status bar spanning its bottom edge."""
    outer = QtGui.QVBoxLayout(dialog)
    outer.setContentsMargins(0, 0, 0, 0)
    outer.setSpacing(0)
    content = QtGui.QWidget()
    outer.addWidget(content, 1)
    status_bar = QtGui.QStatusBar()
    outer.addWidget(status_bar)
    return QtGui.QVBoxLayout(content), status_bar


def _status_label(status_bar, stretch=1):
    label = QtGui.QLabel()
    label.setWordWrap(True)
    label.setTextFormat(QtCore.Qt.PlainText)
    status_bar.addWidget(label, stretch)
    return label


class ToolShapeDialog(QtGui.QDialog):
    """Select a base definition by its native cutting outline without publishing assets."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.import_requested = False
        self.presets = assets.tool_shape_presets()
        self.setWindowTitle(translate("CAM", "ToolBit Shape Selection"))
        self.resize(760, 460)
        self.setMinimumSize(400, 300)
        layout, status_bar = _dialog_layout(self)
        self.shapes = QtGui.QListWidget()
        self.shapes.setViewMode(QtGui.QListView.IconMode)
        self.shapes.setResizeMode(QtGui.QListView.Adjust)
        self.shapes.setMovement(QtGui.QListView.Static)
        self.shapes.setIconSize(QtCore.QSize(120, 96))
        self.shapes.setGridSize(QtCore.QSize(176, 164))
        self.shapes.setSpacing(6)
        self.shapes.setWordWrap(True)
        self.shapes.setSelectionMode(QtGui.QAbstractItemView.SingleSelection)
        errors = []
        for index, snapshot in enumerate(self.presets):
            title = snapshot.values["name"]
            item = QtGui.QListWidgetItem(title)
            item.setData(QtCore.Qt.UserRole, index)
            try:
                geometry = assets.custom_tool_preview(snapshot, snapshot.values)["outlines"]
                item.setIcon(_shape_icon(geometry, self.palette()))
                item.setToolTip(snapshot.values["name"])
            except (OSError, ValueError, RuntimeError, TypeError) as error:
                message = f"{title}: {error}"
                errors.append(message)
                item.setToolTip(message)
                item.setFlags(item.flags() & ~QtCore.Qt.ItemIsEnabled)
            self.shapes.addItem(item)
        layout.addWidget(self.shapes, 1)
        self.problem = _status_label(status_bar)
        self.problem.setText("\n".join(errors))
        buttons = QtGui.QDialogButtonBox(QtGui.QDialogButtonBox.Ok | QtGui.QDialogButtonBox.Cancel)
        self.choose_button = buttons.button(QtGui.QDialogButtonBox.Ok)
        self.choose_button.setText(translate("CAM", "Choose shape"))
        self.choose_button.setEnabled(False)
        self.import_button = buttons.addButton(
            translate("CAM", "Import shape..."), QtGui.QDialogButtonBox.ActionRole)
        self.import_button.clicked.connect(self._import_shape)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        self.shapes.itemSelectionChanged.connect(
            lambda: self.choose_button.setEnabled(bool(self.shapes.selectedItems())))
        self.shapes.itemDoubleClicked.connect(lambda _item: self.accept())
        layout.addWidget(buttons)

    def selected_preset(self):
        items = self.shapes.selectedItems()
        return self.presets[items[0].data(QtCore.Qt.UserRole)] if items else None

    def _import_shape(self):
        self.import_requested = True
        super().accept()

    def accept(self):
        if self.selected_preset() is not None:
            super().accept()


class CustomToolDialog(QtGui.QDialog):
    """Build custom controls from the imported native property's own type and choices."""

    def __init__(self, snapshot, parent=None):
        super().__init__(parent)
        self.snapshot = snapshot
        self.controls = {}
        self.setWindowTitle(translate("CAM", "Custom Turning ToolBit"))
        self.resize(620, 680)
        self.setMinimumSize(480, 560)
        layout, status_bar = _dialog_layout(self)
        scroll = QtGui.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QtGui.QFrame.NoFrame)
        scroll.setMinimumHeight(150)
        scroll.setMaximumHeight(340)
        fields_widget = QtGui.QWidget()
        form = QtGui.QFormLayout(fields_widget)
        form.setFieldGrowthPolicy(QtGui.QFormLayout.AllNonFixedFieldsGrow)
        form.setRowWrapPolicy(QtGui.QFormLayout.WrapLongRows)
        self.name = QtGui.QLineEdit(snapshot.values["name"])
        form.addRow(translate("CAM", "Name"), self.name)
        for name, field in snapshot.fields.items():
            value = snapshot.values[name]
            kind = field["type"]
            if field["readonly"]:
                control = QtGui.QLineEdit(str(value))
                control.setReadOnly(True)
            elif kind == "App::PropertyEnumeration":
                control = QtGui.QComboBox()
                control.addItems(field["choices"])
                control.setCurrentText(value)
                control.currentIndexChanged.connect(self._queue_preview)
            elif kind == "App::PropertyBool":
                control = QtGui.QCheckBox()
                control.setChecked(value)
                control.toggled.connect(self._queue_preview)
            elif kind == "App::PropertyInteger":
                control = QtGui.QSpinBox()
                control.setRange(-2147483648, 2147483647)
                control.setValue(value)
                control.valueChanged.connect(self._queue_preview)
            elif name == "Rotation" and kind == "App::PropertyAngle":
                control = RotationSpinBox(str(value))
                control.valueChanged.connect(self._queue_preview)
            else:
                control = QtGui.QLineEdit(str(value))
                control.textChanged.connect(self._queue_preview)
            control.setToolTip(field["description"])
            self.controls[name] = control
            if not field["hidden"]:
                form.addRow(name, control)
            else:
                control.setParent(fields_widget)
                control.hide()
        scroll.setWidget(fields_widget)
        layout.addWidget(scroll)
        self.preview = ToolPreview()
        layout.addWidget(self.preview, 1)
        self.flip_x_view = QtGui.QCheckBox(translate("CAM", "Flip X view"))
        self.flip_x_view.setToolTip(translate("CAM", "Changes the preview only."))
        self.flip_x_view.toggled.connect(self.preview.set_x_flipped)
        layout.addWidget(self.flip_x_view)
        buttons = QtGui.QDialogButtonBox(QtGui.QDialogButtonBox.Save | QtGui.QDialogButtonBox.Cancel)
        self.problem = _status_label(status_bar)
        self.save_button = buttons.button(QtGui.QDialogButtonBox.Save)
        if not snapshot.uri:
            self.save_button.setText(translate("CAM", "Create ToolBit"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.preview_timer = QtCore.QTimer(self)
        self.preview_timer.setSingleShot(True)
        self.preview_timer.setInterval(250)
        self.preview_timer.timeout.connect(self._refresh_preview)
        self.finished.connect(self.preview_timer.stop)
        self.name.textChanged.connect(self._queue_preview)
        self._refresh_preview()

    def values(self):
        values = {"name": self.name.text()}
        for name, field in self.snapshot.fields.items():
            control = self.controls[name]
            if field["readonly"]:
                values[name] = self.snapshot.values[name]
            elif field["type"] == "App::PropertyEnumeration":
                values[name] = control.currentText()
            elif field["type"] == "App::PropertyBool":
                values[name] = control.isChecked()
            elif field["type"] == "App::PropertyInteger":
                values[name] = control.value()
            elif isinstance(control, RotationSpinBox):
                values[name] = control.quantity()
            elif field["type"] == "App::PropertyFloat":
                values[name] = float(control.text())
            else:
                values[name] = control.text()
        return values

    def _queue_preview(self, *_arguments):
        self.save_button.setEnabled(False)
        self.preview_timer.start()

    def _refresh_preview(self):
        self.preview_timer.stop()
        try:
            geometry = assets.custom_tool_preview(self.snapshot, self.values())
        except (OSError, ValueError, RuntimeError, TypeError) as error:
            self.problem.setText(str(error))
            self.preview.set_outline((), str(error))
            self.save_button.setEnabled(False)
            return
        for name, value in geometry.pop("calculated").items():
            self.controls[name].setText(value)
        self.preview.set_outline(**geometry)
        self.problem.clear()
        self.save_button.setEnabled(True)

    def accept(self):
        self._refresh_preview()
        if self.save_button.isEnabled():
            super().accept()


class LibraryDialog(QtGui.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.snapshot = None
        self.table = ToolLibrary()
        self.document_name = None
        self.setWindowTitle(translate("CAM", "Turning Tool Library") + "[*]")
        self.resize(720, 440)
        self.setMinimumSize(480, 320)
        layout, status_bar = _dialog_layout(self)

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
            "list-add", QtGui.QStyle.SP_FileIcon,
            translate("CAM", "New ToolBit"), self.create_tool)
        self.add_button = self._button(
            "Std_Import", QtGui.QStyle.SP_FileDialogNewFolder,
            translate("CAM", "Add existing ToolBit"), self.add_tool)
        self.edit_button = self._button(
            "edit-edit", QtGui.QStyle.SP_FileDialogContentsView,
            translate("CAM", "Edit ToolBit"), self.edit_tool)
        self.remove_button = self._button(
            "list-remove", QtGui.QStyle.SP_TrashIcon,
            translate("CAM", "Remove from library"), self.remove_tool)
        self.renumber_button = self._button(
            "arrow-up", QtGui.QStyle.SP_ArrowUp,
            translate("CAM", "Renumber tool"), self.renumber_tool)
        for button in (self.new_tool_button, self.remove_button, self.edit_button, self.add_button, self.renumber_button):
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
        self.job_button.setAutoDefault(False)
        self.job_button.clicked.connect(self.add_to_job)
        job_row.addWidget(self.job_button)
        layout.addLayout(job_row)
        self.status = _status_label(status_bar)
        self.buttons = QtGui.QDialogButtonBox(
            QtGui.QDialogButtonBox.Save | QtGui.QDialogButtonBox.Close)
        self.save_button = self.buttons.button(QtGui.QDialogButtonBox.Save)
        self.save_button.setIcon(_icon("document-save", QtGui.QStyle.SP_DialogSaveButton))
        self.save_button.setAutoDefault(False)
        self.save_button.clicked.connect(self.save_library)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self.rows.itemSelectionChanged.connect(self._update_actions)
        self.rows.currentCellChanged.connect(self._update_actions)
        self.libraries.currentIndexChanged.connect(self.open_library)
        self.jobs.currentIndexChanged.connect(self._update_job_state)
        self._update_actions()
        self.refresh_jobs()
        self.reload_libraries()

    def _button(self, icon, fallback, text, callback):
        button = QtGui.QToolButton()
        button.setIcon(_icon(icon, fallback))
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
            assets.add_to_job(entry, self.document_name, self.jobs.currentData())
        except (OSError, ValueError, RuntimeError) as error:
            self._report_error(error)
        self._update_job_state()

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
            message = ""
        self.libraries.setToolTip(assets.library_location()["path"])
        self.status.setText(message)
        self._update_actions()

    def _report_error(self, error):
        QtGui.QMessageBox.warning(self, translate("CAM", "Tool library error"), str(error))

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

    def create_tool(self):
        if not self.new_tool_button.isEnabled():
            return
        try:
            dialog = ToolShapeDialog(self)
            if dialog.exec_() != QtGui.QDialog.Accepted:
                return
            if dialog.import_requested:
                self.create_custom_tool()
                return
            self._create_custom_tool(dialog.selected_preset())
        except (OSError, ValueError, RuntimeError, TypeError) as error:
            self._report_error(error)

    def create_custom_tool(self):
        if not self.new_tool_button.isEnabled():
            return
        filename, _selected_filter = QtGui.QFileDialog.getOpenFileName(
            self, translate("CAM", "Select custom ToolShape"), "",
            translate("CAM", "FreeCAD ToolShape (*.fcstd *.FCStd)"))
        if not filename:
            return
        try:
            snapshot = assets.custom_tool_preset(filename)
        except (OSError, ValueError, RuntimeError) as error:
            self._report_error(error)
            return
        self._create_custom_tool(snapshot)

    def _create_custom_tool(self, snapshot):
        try:
            dialog = CustomToolDialog(snapshot, self)
            if dialog.exec_() != QtGui.QDialog.Accepted:
                return
            entry = assets.create_custom_tool(snapshot, self.table.next_number, values=dialog.values())
            self.table.add(entry)
        except (OSError, ValueError, RuntimeError) as error:
            self._report_error(error)
            return
        self._render(entry.number)

    def edit_tool(self):
        if not self.edit_button.isEnabled():
            return
        number = self._selected_number()
        entry = self.table.get(number)
        try:
            snapshot = assets.load_tool_definition(entry.tool_id)
            dialog = CustomToolDialog(snapshot, self)
            if dialog.exec_() != QtGui.QDialog.Accepted:
                return
            values = dialog.values()
            if values == snapshot.values:
                return
            confirmation = translate("CAM", "Save changes to this ToolBit? Every library referencing it will use the updated definition.")
            answer = QtGui.QMessageBox.question(
                self, translate("CAM", "Edit shared ToolBit"),
                confirmation,
                QtGui.QMessageBox.Yes | QtGui.QMessageBox.Cancel, QtGui.QMessageBox.Cancel,
            )
            if answer != QtGui.QMessageBox.Yes:
                return
            updated = assets.save_custom_tool(snapshot, values)
        except (OSError, ValueError, RuntimeError) as error:
            self._report_error(error)
            return
        for table in (self.table, self.snapshot.table):
            for member in table.entries:
                if member.tool_id == updated.uri:
                    table.edit(
                        member.number, name=updated.attributes["name"], shape=updated.shape_name)
        self.snapshot.tools[entry.tool_id] = updated.attributes
        self._render(number)

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
