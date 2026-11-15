"""Task panel and command for selected turning edge breaks."""

from pathlib import Path

import FreeCAD
import Path.Op.Gui.Base as PathOpGui
from PySide import QtCore

from . import PathTurnBaseGui
from . import PathTurnChamfer


_icon = Path(__file__).parent.parent / "Gui/Resources/Icons/CAM-TurnChamfer.svg"


class TaskPanelOpPage(PathTurnBaseGui.TaskPanelTurnBase):
    quantity_fields = {
        **PathTurnBaseGui.TaskPanelTurnBase.quantity_fields,
        "ChamferSize": "chamferSize",
    }

    def getIcon(self, obj):
        return str(_icon)

    def setOpFields(self, obj):
        self.form.chamferSize.show()
        self.form.chamferSizeLabel.show()
        self.quantitySpinBoxes["ChamferSize"].updateWidget()
        self.form.directionLabel.setText(FreeCAD.Qt.translate("PathTurn", "Chamfer Side"))
        self.form.directionLabel.show()
        self.form.direction.show()
        self.form.direction.blockSignals(True)
        self.form.direction.clear()
        self.form.direction.addItems(obj.getEnumerationsOfProperty("ChamferSide"))
        self.form.direction.setCurrentIndex(
            self.form.direction.findText(str(obj.ChamferSide)))
        self.form.direction.blockSignals(False)
        self.form.direction.setToolTip(FreeCAD.Qt.translate(
            "PathTurn", "-Z: position the chamfer from Axial Max.\n"
            "+Z: position the chamfer from Axial Min."))
        self.form.passOffset.setToolTip(FreeCAD.Qt.translate(
            "PathTurn", "Maximum distance between passes, measured perpendicular to the chamfer."))

    def getFields(self, obj):
        super().getFields(obj)
        side = self.form.direction.currentText()
        if side and str(obj.ChamferSide) != side:
            obj.ChamferSide = side
        self.quantitySpinBoxes["ChamferSize"].updateProperty()

    def getSignalsForUpdate(self, obj):
        return super().getSignalsForUpdate(obj) + [
            self.form.direction.currentIndexChanged,
            self.form.chamferSize.editingFinished]


Command = PathOpGui.SetupOperation(
    "TurnChamfer", PathTurnChamfer.Create, TaskPanelOpPage, "CAM-TurnChamfer",
    QtCore.QT_TRANSLATE_NOOP("PathTurnChamfer", "Turn Chamfer"),
    QtCore.QT_TRANSLATE_NOOP(
        "PathTurnChamfer", "Create equal 45-degree edge breaks on selected turning corners"),
    PathTurnChamfer.SetupProperties)
