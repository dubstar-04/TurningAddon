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


class IsoToolEditDialog(QtGui.QDialog):
    def __init__(self, values, parent=None):
        super().__init__(parent)
        self.setWindowTitle(translate("CAM", "Edit ISO ToolBit"))
        self.resize(480, 320)
        layout = QtGui.QVBoxLayout(self)
        warning = QtGui.QLabel(translate(
            "CAM", "This ToolBit may be shared. Saving affects every library that references it."))
        warning.setWordWrap(True)
        layout.addWidget(warning)
        fields = QtGui.QFormLayout()
        self.name = QtGui.QLineEdit(values["name"])
        fields.addRow(translate("CAM", "Name"), self.name)
        self.dimensions = {}
        for field, label in (
            ("EdgeLength", translate("CAM", "Edge length (mm)")),
            ("TipRadius", translate("CAM", "Nose radius (mm)")),
            ("TipAngle", translate("CAM", "Tip angle (deg)")),
            ("Rotation", translate("CAM", "Rotation (deg)")),
        ):
            control = QtGui.QLineEdit(repr(values[field]))
            validator = QtGui.QDoubleValidator(control)
            validator.setLocale(QtCore.QLocale.c())
            validator.setNotation(QtGui.QDoubleValidator.ScientificNotation)
            control.setValidator(validator)
            fields.addRow(label, control)
            self.dimensions[field] = control
            control.textChanged.connect(self._update_state)
        layout.addLayout(fields)
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
        self._update_state()

    def values(self):
        return dict(
            {field: float(control.text()) for field, control in self.dimensions.items()},
            name=self.name.text(),
        )

    def _update_state(self):
        try:
            values = self.values()
            valid = (
                bool(values["name"].strip())
                and all(math.isfinite(values[field]) for field in self.dimensions)
                and values["EdgeLength"] > 0 and values["TipRadius"] > 0
                and 0 < values["TipAngle"] < 180
            )
        except ValueError:
            valid = False
        self.save_button.setEnabled(valid)
        self.problem.setText("" if valid else translate(
            "CAM", "Enter a name, finite dimensions, positive lengths and a tip angle between 0 and 180 degrees."))