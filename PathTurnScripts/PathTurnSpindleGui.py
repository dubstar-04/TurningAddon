from pathlib import Path

import FreeCAD
import Path.Op.Gui.Base as PathOpGui
from PySide import QtGui

from PathTurnScripts.PathTurnBase import (
    MAX_SPINDLE_SPEED_PROPERTY,
    SPINDLE_MODE_CSS,
    SPINDLE_MODE_PROPERTY,
    SPINDLE_MODE_RPM,
    SURFACE_SPEED_PROPERTY,
    ensure_turning_spindle_properties,
)


def translate(text):
    return FreeCAD.Qt.translate("PathTurn", text)


class TaskPanelTurningSpindlePage(PathOpGui.TaskPanelPage):
    """Edit the selected Tool Controller's turning spindle settings."""

    def getForm(self):
        form = QtGui.QWidget()
        layout = QtGui.QGridLayout(form)
        layout.setColumnStretch(1, 1)
        layout.setRowStretch(5, 1)

        self.controllerName = QtGui.QLabel(form)
        self.controllerName.setWordWrap(True)
        layout.addWidget(self.controllerName, 0, 0, 1, 2)

        self.spindleMode = QtGui.QComboBox(form)
        layout.addWidget(QtGui.QLabel(translate("Mode"), form), 1, 0)
        layout.addWidget(self.spindleMode, 1, 1)

        self.surfaceSpeed = QtGui.QDoubleSpinBox(form)
        self.surfaceSpeed.setRange(0, 1_000_000)
        self.surfaceSpeed.setDecimals(1)
        self.surfaceSpeed.setSingleStep(10)
        self.surfaceSpeed.setSuffix(" m/min")
        self.surfaceSpeedLabel = QtGui.QLabel(translate("Surface speed"), form)
        layout.addWidget(self.surfaceSpeedLabel, 2, 0)
        layout.addWidget(self.surfaceSpeed, 2, 1)

        self.maxSpindleSpeed = QtGui.QSpinBox(form)
        self.maxSpindleSpeed.setRange(0, 1_000_000)
        self.maxSpindleSpeed.setSuffix(" RPM")
        self.maxSpindleSpeedLabel = QtGui.QLabel(translate("Maximum spindle speed"), form)
        layout.addWidget(self.maxSpindleSpeedLabel, 3, 0)
        layout.addWidget(self.maxSpindleSpeed, 3, 1)

        self.spindleNote = QtGui.QLabel(form)
        self.spindleNote.setWordWrap(True)
        layout.addWidget(self.spindleNote, 4, 0, 1, 2)
        return form

    def initPage(self, obj):
        self.setIcon(str(Path(__file__).parent.parent / "Gui/Resources/Icons/CAM-TurningAddon.svg"))
        self.updating = False
        self.spindleMode.currentIndexChanged.connect(self._updateSpindleFields)
        FreeCAD.addDocumentObserver(self)
        self.observing = True
        self.form.destroyed.connect(self.stopObserving)

    def cleanupPage(self, obj):
        self.stopObserving()

    def stopObserving(self, *args):
        if self.observing:
            FreeCAD.removeDocumentObserver(self)
            self.observing = False

    def getTitle(self, obj):
        return translate("Turning Spindle")

    def getSignalsForUpdate(self, obj):
        if getattr(obj.Proxy, "supports_css", True):
            return [
                self.spindleMode.currentIndexChanged,
                self.surfaceSpeed.editingFinished,
                self.maxSpindleSpeed.editingFinished,
            ]
        return []

    def updateData(self, obj, prop):
        if obj == self.obj and prop == "ToolController":
            self.setFields(obj)

    def slotChangedObject(self, obj, prop):
        if (obj == getattr(self.obj, "ToolController", None)
                and prop in ("Label", SPINDLE_MODE_PROPERTY,
                             SURFACE_SPEED_PROPERTY, MAX_SPINDLE_SPEED_PROPERTY)):
            self.setFields(self.obj)

    def setFields(self, obj):
        if self.updating:
            return
        self.updating = True
        try:
            controller = getattr(obj, "ToolController", None)
            supports_css = getattr(obj.Proxy, "supports_css", True)
            self.form.setEnabled(controller is not None)
            self.controllerName.setText(
                translate("Tool Controller: {name}").format(
                    name=controller.Label if controller else translate("None")))
            self.surfaceSpeedLabel.setVisible(supports_css)
            self.surfaceSpeed.setVisible(supports_css)
            self.maxSpindleSpeedLabel.setVisible(supports_css)
            self.maxSpindleSpeed.setVisible(supports_css)

            mode = SPINDLE_MODE_RPM
            if controller is not None and supports_css:
                ensure_turning_spindle_properties(controller, obj)
                mode = str(getattr(controller, SPINDLE_MODE_PROPERTY, SPINDLE_MODE_RPM))

            blocked = self.spindleMode.blockSignals(True)
            try:
                self.spindleMode.clear()
                if supports_css:
                    self.spindleMode.addItem(translate("Fixed RPM"), SPINDLE_MODE_RPM)
                    self.spindleMode.addItem(
                        translate("Constant Surface Speed"), SPINDLE_MODE_CSS)
                else:
                    self.spindleMode.addItem(
                        translate("Fixed RPM (required)"), SPINDLE_MODE_RPM)
                self.spindleMode.setCurrentIndex(max(0, self.spindleMode.findData(mode)))
                self.spindleMode.setEnabled(supports_css and controller is not None)
            finally:
                self.spindleMode.blockSignals(blocked)

            if controller is not None and supports_css:
                self.surfaceSpeed.setValue(
                    float(getattr(controller, SURFACE_SPEED_PROPERTY, 0) or 0))
                self.maxSpindleSpeed.setValue(
                    int(getattr(controller, MAX_SPINDLE_SPEED_PROPERTY, 0) or 0))
            else:
                self.surfaceSpeed.setValue(0)
                self.maxSpindleSpeed.setValue(0)

            is_css = supports_css and mode == SPINDLE_MODE_CSS
            self.surfaceSpeed.setEnabled(is_css)
            self.maxSpindleSpeed.setEnabled(is_css)
            if controller is None:
                note = translate("Select a Tool Controller to configure spindle settings.")
            elif supports_css:
                note = translate("Settings are shared by all operations using this Tool Controller.")
            else:
                note = translate("This operation always uses fixed RPM.")
            self.spindleNote.setText(note)
        finally:
            self.updating = False

    def getFields(self, obj):
        if self.updating or not getattr(obj.Proxy, "supports_css", True):
            return
        controller = getattr(obj, "ToolController", None)
        if controller is None:
            return

        values = (
            (SPINDLE_MODE_PROPERTY, self.spindleMode.currentData()),
            (SURFACE_SPEED_PROPERTY, self.surfaceSpeed.value()),
            (MAX_SPINDLE_SPEED_PROPERTY, self.maxSpindleSpeed.value()),
        )
        self.updating = True
        try:
            ensure_turning_spindle_properties(controller, obj)
            for name, value in values:
                if getattr(controller, name) != value:
                    setattr(controller, name, value)
        finally:
            self.updating = False

    def _updateSpindleFields(self, *args):
        is_css = (getattr(self.obj.Proxy, "supports_css", True)
                  and self.spindleMode.currentData() == SPINDLE_MODE_CSS)
        self.surfaceSpeed.setEnabled(is_css)
        self.maxSpindleSpeed.setEnabled(is_css)


class TaskPanelToolControllerWithSpindlePage(PathOpGui.TaskPanelToolControllerPage):
    def initPage(self, obj):
        super().initPage(obj)
        # CAM has no extra-page hook; insert after this page before its init loop advances.
        index = self.parent.featurePages.index(self) + 1
        self.parent.featurePages.insert(index, TaskPanelTurningSpindlePage(obj, self.features))
