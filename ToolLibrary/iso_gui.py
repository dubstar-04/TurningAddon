"""Reusable ISO selection controls without document or machining dependencies."""

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