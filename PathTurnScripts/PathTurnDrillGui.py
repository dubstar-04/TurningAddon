"""Task panel and command for centreline drilling."""

from pathlib import Path

import FreeCAD
import FreeCADGui
import Path.Op.Gui.Base as PathOpGui
import Path.Base.Gui.Util as PathGuiUtil
from PySide import QtCore

from . import PathTurnBaseGui
from . import PathTurnDrill


_icon = Path(__file__).parent.parent / "Gui/Resources/Icons/CAM-TurnDrill.svg"


class TaskPanelOpPage(PathTurnBaseGui.TaskPanelTurnBase):
    def getIcon(self, obj):
        return str(_icon)

    quantity_fields = {
        "PeckDepth": "peckDepth",
    }

    def getForm(self):
        form = super().getForm()
        for mode in PathTurnDrill.RETRACTION_MODES:
            form.retractionMode.addItem(FreeCAD.Qt.translate("PathTurn", mode), mode)
        form.tipCompensation.addItem(FreeCAD.Qt.translate("PathTurn", "None"))
        form.tipCompensation.addItem(FreeCAD.Qt.translate("PathTurn", "Tool Tip"))
        form.retractionMode.currentIndexChanged.connect(self._updatePeckFields)
        return form

    def initPage(self, obj):
        super().initPage(obj)
        self.quantitySpinBoxes = {
            prop: PathGuiUtil.QuantitySpinBox(getattr(self.form, widget), obj, prop)
            for prop, widget in self.quantity_fields.items()}
        self._updatePeckFields()

    def _updatePeckFields(self, *args):
        pecking = self.form.retractionMode.currentData() != PathTurnDrill.NO_RETRACT
        for field in ("peckDepth", "peckDepthLabel"):
            getattr(self.form, field).setEnabled(pecking)

    def setOpFields(self, obj):
        for name in ("retractionMode", "peckDepth", "tipCompensation"):
            getattr(self.form, name).show()
            getattr(self.form, name + "Label").show()
        for spin_box in self.quantitySpinBoxes.values():
            spin_box.updateWidget()
        blocked = self.form.retractionMode.blockSignals(True)
        self.form.retractionMode.setCurrentIndex(
            self.form.retractionMode.findData(str(obj.RetractionMode)))
        self.form.retractionMode.blockSignals(blocked)
        blocked = self.form.tipCompensation.blockSignals(True)
        self.form.tipCompensation.setCurrentIndex(1 if obj.TipCompensation else 0)
        self.form.tipCompensation.blockSignals(blocked)
        self._updatePeckFields()

    def getFields(self, obj):
        super().getFields(obj)
        for spin_box in self.quantitySpinBoxes.values():
            spin_box.updateProperty()
        if str(obj.RetractionMode) != self.form.retractionMode.currentData():
            obj.RetractionMode = self.form.retractionMode.currentData()
        tip_compensation = self.form.tipCompensation.currentIndex() == 1
        if obj.TipCompensation != tip_compensation:
            obj.TipCompensation = tip_compensation
        self.containment_page.setFields(obj)
        self.updateContainment()

    def updateData(self, obj, prop):
        super().updateData(obj, prop)
        if prop in self.quantitySpinBoxes:
            self.quantitySpinBoxes[prop].updateWidget()
            self._updatePeckFields()

    def getSignalsForUpdate(self, obj):
        return super().getSignalsForUpdate(obj) + [
            self.form.retractionMode.currentIndexChanged, self.form.peckDepth.editingFinished,
            self.form.tipCompensation.currentIndexChanged,
        ]


Command = PathOpGui.SetupOperation(
    "TurnDrill", PathTurnDrill.Create, TaskPanelOpPage, "CAM-TurnDrill",
    QtCore.QT_TRANSLATE_NOOP("PathTurnDrill", "Turn Drill"),
    QtCore.QT_TRANSLATE_NOOP("PathTurnDrill", "Drill on the spindle axis with optional pecking and tip compensation"),
    PathTurnDrill.SetupProperties)
