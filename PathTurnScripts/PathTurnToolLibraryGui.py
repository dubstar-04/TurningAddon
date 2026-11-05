"""FreeCAD command entry point for the turning tool library."""

from PySide import QtCore

import FreeCAD
import FreeCADGui


class CommandPathTurnToolLibrary:
    def GetResources(self):
        return {
            "Pixmap": "CAM-TurnToolHelper",
            "MenuText": QtCore.QT_TRANSLATE_NOOP("CAM", "Turning Tool Library"),
            "ToolTip": QtCore.QT_TRANSLATE_NOOP(
                "CAM", "Manage native turning tools and add them to a CAM job"),
        }

    def Activated(self):
        from PathTurnToolLibrary.PathTurnToolGui import LibraryDialog

        dialog = LibraryDialog(FreeCADGui.getMainWindow())
        dialog.exec_()


if FreeCAD.GuiUp:
    FreeCADGui.addCommand("CAM_TurnToolHelper", CommandPathTurnToolLibrary())