"""Task panel and command for selected turning edge breaks."""

from pathlib import Path

import FreeCAD
import Path.Op.Gui.Base as PathOpGui
from PySide import QtCore, QtGui

from liblathe.op.base import MachiningMode
from liblathe.op.chamfer import ChamferPosition

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

    def getForm(self):
        form = super().getForm()
        self.position_buttons = {
            ChamferPosition.FRONT: form.chamferFront,
            ChamferPosition.BACK: form.chamferBack,
        }
        self.position_group = QtGui.QButtonGroup(form)
        self.position_group.setExclusive(True)
        for button in self.position_buttons.values():
            self.position_group.addButton(button)
        form.chamferFront.setChecked(True)
        external_icons = {position: button.icon()
                          for position, button in self.position_buttons.items()}
        rotation = QtGui.QTransform().rotate(180)
        internal_icons = {
            ChamferPosition.FRONT: QtGui.QIcon(
                external_icons[ChamferPosition.BACK].pixmap(64, 64).transformed(rotation)),
            ChamferPosition.BACK: QtGui.QIcon(
                external_icons[ChamferPosition.FRONT].pixmap(64, 64).transformed(rotation)),
        }
        self.position_icons = {
            MachiningMode.EXTERNAL: external_icons,
            MachiningMode.INTERNAL: internal_icons,
        }
        return form

    def setOpFields(self, obj):
        self.form.chamferSize.show()
        self.form.chamferSizeLabel.show()
        self.quantitySpinBoxes["ChamferSize"].updateWidget()
        self.form.chamferPositionLabel.setEnabled(True)
        self.form.chamferPositionButtons.setEnabled(True)
        selected = ChamferPosition(str(obj.ChamferPosition))
        icons = self.position_icons[MachiningMode(str(obj.Mode))]
        for position, button in self.position_buttons.items():
            button.setChecked(position == selected)
            button.setIcon(icons[position])
        self.form.passOffset.setToolTip(FreeCAD.Qt.translate(
            "PathTurn", "Maximum distance between passes, measured perpendicular to the chamfer."))

    def getFields(self, obj):
        super().getFields(obj)
        position = (ChamferPosition.FRONT if self.form.chamferFront.isChecked()
                    else ChamferPosition.BACK)
        if str(obj.ChamferPosition) != position.value:
            obj.ChamferPosition = position.value
        self.quantitySpinBoxes["ChamferSize"].updateProperty()

    def updateData(self, obj, prop):
        super().updateData(obj, prop)
        if prop in ("Mode", "ChamferPosition"):
            self.setOpFields(obj)

    def getSignalsForUpdate(self, obj):
        return super().getSignalsForUpdate(obj) + [
            self.form.chamferFront.clicked,
            self.form.chamferBack.clicked,
            self.form.chamferSize.editingFinished]


Command = PathOpGui.SetupOperation(
    "TurnChamfer", PathTurnChamfer.Create, TaskPanelOpPage, "CAM-TurnChamfer",
    QtCore.QT_TRANSLATE_NOOP("PathTurnChamfer", "Turn Chamfer"),
    QtCore.QT_TRANSLATE_NOOP(
        "PathTurnChamfer", "Create equal 45-degree edge breaks on selected turning corners"),
    PathTurnChamfer.SetupProperties)
