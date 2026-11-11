"""Task panel and command for straight centreline drilling."""

from pathlib import Path

import FreeCAD
import FreeCADGui
import Path.Op.Gui.Base as PathOpGui
from PySide import QtCore

from . import PathTurnBaseGui
from . import PathTurnDrill
from .PathTurnContainmentGui import TaskPanelContainment


_icon = Path(__file__).parent.parent / "Gui/Resources/Icons/CAM-TurnDrill.svg"
FreeCADGui.addIcon("CAM-TurnDrill", _icon.read_text(), "SVG")
FreeCADGui.addIcon(":/icons/CAM-TurnDrill.svg", _icon.read_text(), "SVG")


class TaskPanelDrillContainment(TaskPanelContainment):
    def mapping(self, obj):
        return {"plusZ": ("StartDepth", 1), "minusZ": ("FinalDepth", 1)}

    def getForm(self):
        form = super().getForm()
        for name in ("plusX", "minusX"):
            for suffix in ("", "Label", "Set"):
                getattr(form, name + suffix).hide()
        form.plusZLabel.setText(FreeCAD.Qt.translate("PathTurn", "Start depth"))
        form.minusZLabel.setText(FreeCAD.Qt.translate("PathTurn", "Final tip depth"))
        form.setToolTip(FreeCAD.Qt.translate(
            "PathTurn", "Drill tip depths at X=0. The user is responsible for a safe entry plane. "
            "Final depth is not the full-diameter hole depth. Clearance uses the job Safe Height Offset."))
        return form


class TaskPanelOpPage(PathTurnBaseGui.TaskPanelTurnBase):
    taskPanelDepthsPage = TaskPanelDrillContainment

    def getIcon(self, obj):
        return str(_icon)

    def setOpFields(self, obj):
        for name in ("stockToLeave", "label_6", "finishPasses", "label_5", "allowGrooving"):
            getattr(self.form, name).hide()
        self.form.setToolTip(FreeCAD.Qt.translate(
            "PathTurn", "Straight centreline drilling with a native Drill ToolBit and vertical feed. "
            "No pecking, canned cycles, automatic breakthrough, flute-length or holder-clearance checks."))


Command = PathOpGui.SetupOperation(
    "TurnDrill", PathTurnDrill.Create, TaskPanelOpPage, "CAM-TurnDrill",
    QtCore.QT_TRANSLATE_NOOP("PathTurnDrill", "Turn Drill"),
    QtCore.QT_TRANSLATE_NOOP("PathTurnDrill", "Drill on the spindle axis to an explicit drill-tip depth"),
    PathTurnDrill.SetupProperties)
