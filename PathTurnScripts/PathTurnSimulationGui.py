"""FreeCAD command entry point for CAM simulation."""

from PySide import QtCore
import FreeCAD
import FreeCADGui


class CommandPathTurnSimulation:
    def GetResources(self):
        return {
            "Pixmap": "CAM-TurnSimulation",
            "MenuText": QtCore.QT_TRANSLATE_NOOP("CAM", "Simulation"),
            "ToolTip": QtCore.QT_TRANSLATE_NOOP("CAM", "Simulate the selected CAM job"),
        }

    def IsActive(self):
        document = FreeCAD.ActiveDocument
        return document is not None and bool(
            document.findObjects("Path::FeaturePython", "Job.*"))

    def Activated(self):
        from PathTurnSimulation.PathSimGui import Show

        Show()


if FreeCAD.GuiUp:
    FreeCADGui.addCommand("CAM_TurnSimulation", CommandPathTurnSimulation())
