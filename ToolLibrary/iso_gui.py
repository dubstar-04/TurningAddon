"""Reusable ISO selection controls without document or machining dependencies."""

import math

from PySide import QtCore, QtGui

from . import iso


translate = QtCore.QCoreApplication.translate


class IsoToolPanel(QtCore.QObject):
    selection_changed = QtCore.Signal()

    tip_angle = iso.TIP_ANGLES
    shape_size = iso.SHAPE_SIZES
    nose_radius = iso.NOSE_RADII
    get_edge_length = staticmethod(iso.get_edge_length)
    get_radius_value = staticmethod(iso.get_radius_value)
    get_tip_angle = staticmethod(iso.get_tip_angle)

    def __init__(self, form):
        super().__init__(form)
        self.form = form
        self.shape_cb = form.shape_cb
        self.size_cb = form.size_cb
        self.radius_cb = form.radius_cb
        self.direction_cb = form.direction_cb
        self.size_val = form.size_val
        self.tipangle_val = form.tipangle_val
        self.radius_val = form.radius_val
        self.result_val = form.result_val

        self.radius_cb.setCurrentText("04")
        self.direction_cb.setCurrentText("R")
        self.shape_cb.currentIndexChanged.connect(self.load_shape_size)
        self.shape_cb.currentIndexChanged.connect(self.load_tool_data)
        self.size_cb.currentIndexChanged.connect(self.load_tool_data)
        self.radius_cb.currentIndexChanged.connect(self.load_tool_data)
        self.direction_cb.currentIndexChanged.connect(self.load_tool_data)
        self.load_shape_size(self.shape_cb.currentIndex())

    def load_shape_size(self, index):
        shape = self.shape_cb.itemText(index)
        self.size_cb.clear()
        self.size_cb.addItems(tuple(self.shape_size[shape]) if shape != "X" else ("-",))

    def load_tool_data(self):
        if self.size_cb.currentText():
            shape = self.shape_cb.currentText()
            size = self.size_cb.currentText()
            radius = self.radius_cb.currentText()
            direction = self.direction_cb.currentText()
            self.size_val.setText(str(self.get_edge_length(shape, size)))
            self.tipangle_val.setText(str(self.get_tip_angle(shape)))
            if shape == "X":
                radius = direction = "-"
                self.radius_val.setText("-")
            else:
                self.radius_val.setText(str(self.get_radius_value(radius)))
            self.result_val.setText(f"{shape}---{size}--{radius}--{direction}")
        self.selection_changed.emit()

    def definition_problem(self):
        if self.shape_cb.currentText() not in ("C", "D", "S", "T"):
            return translate("CAM", "Tool creation supports C, D, S and T shapes. Other shapes are reference-only.")
        if not self.size_cb.currentText():
            return translate("CAM", "Choose an insert size.")
        if self.get_radius_value(self.radius_cb.currentText()) <= 0:
            return translate("CAM", "Sharp noses (00) are reference-only. Choose a non-zero nose radius.")
        return None


class IsoToolDialog(IsoToolPanel):
    def __init__(self, form, parent=None):
        super().__init__(form)
        form.setParent(parent, form.windowFlags())
        form.setWindowTitle(translate("CAM", "New ISO ToolBit"))
        form.job_label.hide()
        form.job_cb.hide()
        form.buttonBox.setStandardButtons(
            QtGui.QDialogButtonBox.Ok | QtGui.QDialogButtonBox.Cancel)
        self.create_button = form.buttonBox.button(QtGui.QDialogButtonBox.Ok)
        self.create_button.setText(translate("CAM", "Create ToolBit"))
        self.selection_changed.connect(self._update_state)
        self._update_state()

    def _update_state(self):
        problem = self.definition_problem()
        self.create_button.setEnabled(problem is None)
        self.form.status_label.setText(problem or "")

    def selection(self):
        return tuple(control.currentText() for control in (
            self.shape_cb, self.size_cb, self.radius_cb, self.direction_cb))


class ToolPreview(QtGui.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.outlines = ()
        self.nose_centre = None
        self.x_flipped = False
        self.message = translate("CAM", "Updating preview...")
        self.setMinimumSize(240, 240)
        self.setSizePolicy(QtGui.QSizePolicy.Expanding, QtGui.QSizePolicy.Expanding)

    def set_outline(self, outlines, message="", *, nose_centre=None):
        self.outlines = outlines
        self.nose_centre = nose_centre
        self.message = message
        self.update()

    def set_x_flipped(self, flipped):
        self.x_flipped = flipped
        self.update()

    def paintEvent(self, _event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        palette = self.palette()
        painter.fillRect(self.rect(), palette.base())
        origin = QtCore.QPointF(self.width() / 2, self.height() / 2)
        x_colour = QtGui.QColor("#cc3333")
        z_colour = QtGui.QColor("#3333cc")
        painter.setPen(QtGui.QPen(z_colour, 1.5))
        painter.drawLine(QtCore.QPointF(8, origin.y()), QtCore.QPointF(self.width() - 8, origin.y()))
        painter.drawLine(QtCore.QPointF(self.width() - 8, origin.y()),
                         QtCore.QPointF(self.width() - 14, origin.y() - 3))
        painter.drawLine(QtCore.QPointF(self.width() - 8, origin.y()),
                         QtCore.QPointF(self.width() - 14, origin.y() + 3))
        painter.drawText(QtCore.QPointF(
            self.width() - self.fontMetrics().horizontalAdvance("+Z") - 8, origin.y() - 8), "+Z")
        painter.setPen(QtGui.QPen(x_colour, 1.5))
        painter.drawLine(QtCore.QPointF(origin.x(), 8), QtCore.QPointF(origin.x(), self.height() - 8))
        arrow_tip = self.height() - 8 if self.x_flipped else 8
        arrow_tail = self.height() - 14 if self.x_flipped else 14
        painter.drawLine(QtCore.QPointF(origin.x(), arrow_tip), QtCore.QPointF(origin.x() - 3, arrow_tail))
        painter.drawLine(QtCore.QPointF(origin.x(), arrow_tip), QtCore.QPointF(origin.x() + 3, arrow_tail))
        painter.drawText(QtCore.QPointF(origin.x() + 8, self.height() - 12 if self.x_flipped else 20), "+X")
        painter.setPen(palette.text().color())
        if not self.outlines:
            painter.drawText(QtCore.QRect(12, 12, self.width() // 2 - 28, self.height() // 2 - 28),
                             QtCore.Qt.AlignLeft | QtCore.Qt.TextWordWrap, self.message)
            return
        points = [(0.0, 0.0)] + [point for edge in self.outlines for point in edge]
        if self.nose_centre is not None:
            points.append(self.nose_centre)
        radial_extent = max(abs(point[0]) for point in points)
        axial_extent = max(abs(point[1]) for point in points)
        scale = min((self.width() / 2 - 32) / max(axial_extent, 1e-6),
                    (self.height() / 2 - 32) / max(radial_extent, 1e-6))

        def screen(point):
            radial, axial = point
            return QtCore.QPointF(
                origin.x() + axial * scale,
                origin.y() + radial * scale * (1 if self.x_flipped else -1))

        painter.setPen(QtGui.QPen(palette.text().color(), 2))
        for edge in self.outlines:
            painter.drawPolyline(QtGui.QPolygonF([screen(point) for point in edge]))
        painter.setPen(QtGui.QPen(palette.highlight().color(), 2))
        painter.setBrush(palette.base())
        painter.drawEllipse(origin, 5, 5)
        painter.drawLine(origin + QtCore.QPointF(-8, 0), origin + QtCore.QPointF(8, 0))
        painter.drawLine(origin + QtCore.QPointF(0, -8), origin + QtCore.QPointF(0, 8))


class IsoToolEditDialog(QtGui.QDialog):
    def __init__(self, values, parent=None, *, preview=None):
        super().__init__(parent)
        self.setWindowTitle(translate("CAM", "Edit ISO ToolBit"))
        self.resize(620, 560)
        self.original_rotation = values["Rotation"]
        self.preview_callback = preview
        layout = QtGui.QVBoxLayout(self)
        warning = QtGui.QLabel(translate(
            "CAM", "This ToolBit may be shared. Saving affects every library that references it."))
        warning.setWordWrap(True)
        layout.addWidget(warning)
        fields = QtGui.QFormLayout()
        self.name = QtGui.QLineEdit(values["name"])
        fields.addRow(translate("CAM", "Name"), self.name)
        self.dimensions = {}
        self.angle_presets = {}
        for field, label in (
            ("EdgeLength", translate("CAM", "Edge length (mm)")),
            ("TipRadius", translate("CAM", "Nose radius (mm)")),
            ("TipAngle", translate("CAM", "Tip angle (deg)")),
            ("Rotation", translate("CAM", "Mounting angle (deg)")),
        ):
            control = QtGui.QLineEdit(repr(values[field]))
            validator = QtGui.QDoubleValidator(control)
            validator.setLocale(QtCore.QLocale.c())
            validator.setNotation(QtGui.QDoubleValidator.ScientificNotation)
            control.setValidator(validator)
            if field == "Rotation":
                row = QtGui.QWidget()
                angles = QtGui.QHBoxLayout(row)
                angles.setContentsMargins(0, 0, 0, 0)
                angles.addWidget(control, 1)
                for angle in (0, 90, 180, 270):
                    button = QtGui.QToolButton()
                    button.setText(str(angle))
                    button.setCheckable(True)
                    button.setFixedWidth(40)
                    button.setToolTip(translate("CAM", "Mounting angle: {angle} degrees").format(angle=angle))
                    button.clicked.connect(
                        lambda checked=False, angle=angle: self._set_angle(angle))
                    self.angle_presets[angle] = button
                    angles.addWidget(button)
                fields.addRow(label, row)
            else:
                fields.addRow(label, control)
            self.dimensions[field] = control
            control.textChanged.connect(self._update_state)
        self.reference = QtGui.QComboBox()
        self.reference.addItem(translate("CAM", "Stored origin"), "StoredOrigin")
        self.reference.addItem(translate("CAM", "Nose centre"), "NoseCentre")
        self.reference.setCurrentIndex(self.reference.findData(values["ToolReference"]))
        fields.addRow(translate("CAM", "Tool reference"), self.reference)
        layout.addLayout(fields)
        self.preview = ToolPreview()
        self.preview.setVisible(preview is not None)
        layout.addWidget(self.preview, 1)
        self.flip_x_view = QtGui.QCheckBox(translate("CAM", "Flip X view"))
        self.flip_x_view.setToolTip(translate(
            "CAM", "Changes the preview only; saved tool geometry and toolpaths are unchanged."))
        self.flip_x_view.setVisible(preview is not None)
        self.flip_x_view.toggled.connect(self.preview.set_x_flipped)
        layout.addWidget(self.flip_x_view)
        self.preview_timer = QtCore.QTimer(self)
        self.preview_timer.setSingleShot(True)
        self.preview_timer.setInterval(250)
        self.preview_timer.timeout.connect(self._refresh_preview)
        self.finished.connect(self.preview_timer.stop)
        self.problem = QtGui.QLabel()
        self.problem.setWordWrap(True)
        layout.addWidget(self.problem)
        buttons = QtGui.QDialogButtonBox(
            QtGui.QDialogButtonBox.Save | QtGui.QDialogButtonBox.Cancel)
        self.save_button = buttons.button(QtGui.QDialogButtonBox.Save)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.name.textChanged.connect(self._update_state)
        self.reference.currentIndexChanged.connect(self._update_state)
        self._update_state()

    def values(self):
        return dict(
            {field: float(control.text()) for field, control in self.dimensions.items()},
            name=self.name.text(),
            ToolReference=self.reference.currentData(),
        )

    def _set_angle(self, angle):
        self.dimensions["Rotation"].setText(repr(float(angle)))
        self._update_state()

    def _update_state(self):
        try:
            values = self.values()
            valid = (
                bool(values["name"].strip())
                and values["ToolReference"] in ("StoredOrigin", "NoseCentre")
                and all(math.isfinite(values[field]) for field in self.dimensions)
                and values["EdgeLength"] > 0 and values["TipRadius"] > 0
                and 0 < values["TipAngle"] < 180
                and (abs(values["Rotation"]) <= 360 or values["Rotation"] == self.original_rotation)
            )
        except ValueError:
            valid = False
        for angle, button in self.angle_presets.items():
            button.setChecked(valid and values["Rotation"] == angle)
        if self.preview_callback is not None:
            self.preview_timer.stop()
            self.preview.set_outline((), translate(
                "CAM", "Updating preview..." if valid else "Preview unavailable: invalid dimensions."))
            if valid:
                self.preview_timer.start()
        self.save_button.setEnabled(valid)
        self.problem.setText("" if valid else translate(
            "CAM", "Enter a name, positive lengths, a tip angle between 0 and 180 degrees, and a mounting angle between -360 and 360 degrees."))

    def _refresh_preview(self):
        self.preview_timer.stop()
        if self.preview_callback is None or not self.save_button.isEnabled():
            return
        try:
            result = self.preview_callback(self.values())
        except (OSError, ValueError, RuntimeError) as error:
            self.preview.set_outline((), translate("CAM", "Preview unavailable"))
            self.preview.setToolTip(str(error))
            self.save_button.setEnabled(False)
            return
        self.preview.setToolTip("")
        data = result if isinstance(result, dict) else {"outlines": result}
        self.preview.set_outline(**data)