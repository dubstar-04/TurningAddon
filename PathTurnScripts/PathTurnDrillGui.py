"""Task panel and command for centreline drilling."""

from pathlib import Path

import FreeCAD
import FreeCADGui
import Path.Op.Gui.Base as PathOpGui
from PySide import QtCore

from . import PathTurnBaseGui
from . import PathTurnDrill


_icon = Path(__file__).parent.parent / "Gui/Resources/Icons/CAM-TurnDrill.svg"


class TaskPanelOpPage(PathTurnBaseGui.RetractionModeFields, PathTurnBaseGui.TaskPanelTurnBase):
    def getIcon(self, obj):
        return str(_icon)

    quantity_fields = {
        **PathTurnBaseGui.TaskPanelTurnBase.quantity_fields,
        "PeckDepth": "peckDepth",
    }

    def getForm(self):
        form = super().getForm()
        self._setupRetractionMode(form)
        form.tipCompensation.addItem(FreeCAD.Qt.translate("PathTurn", "None"))
        form.tipCompensation.addItem(FreeCAD.Qt.translate("PathTurn", "Tool Tip"))
        return form

    def initPage(self, obj):
        super().initPage(obj)
        self._updatePeckFields()

    def setOpFields(self, obj):
        self._setRetractionFields(obj)
        self.form.tipCompensation.show()
        self.form.tipCompensationLabel.show()
        blocked = self.form.tipCompensation.blockSignals(True)
        self.form.tipCompensation.setCurrentIndex(1 if obj.TipCompensation else 0)
        self.form.tipCompensation.blockSignals(blocked)

    def getFields(self, obj):
        super().getFields(obj)
        self._getRetractionFields(obj)
        tip_compensation = self.form.tipCompensation.currentIndex() == 1
        if obj.TipCompensation != tip_compensation:
            obj.TipCompensation = tip_compensation
        self.containment_page.setFields(obj)
        self.updateContainment()

    def getSignalsForUpdate(self, obj):
        return (super().getSignalsForUpdate(obj) + self._retractionSignals()
                + [self.form.tipCompensation.currentIndexChanged])


Command = PathOpGui.SetupOperation(
    "TurnDrill", PathTurnDrill.Create, TaskPanelOpPage, "CAM-TurnDrill",
    QtCore.QT_TRANSLATE_NOOP("PathTurnDrill", "Turn Drill"),
    QtCore.QT_TRANSLATE_NOOP("PathTurnDrill", "Drill on the spindle axis with optional pecking and tip compensation"),
    PathTurnDrill.SetupProperties)
