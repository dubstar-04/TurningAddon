"""FreeCAD task panel and command for internal clearing and finishing."""

from pathlib import Path

import FreeCAD
import FreeCADGui
import Path.Op.Gui.Base as PathOpGui
from PySide import QtCore, QtGui

from . import PathTurnBaseGui
from . import PathTurnBore


_icon = Path(__file__).parent.parent / "Gui/Resources/Icons/CAM-TurnBore.svg"


class TaskPanelOpPage(PathTurnBaseGui.TaskPanelTurnBase):
    def getIcon(self, obj):
        return str(_icon)

    def getForm(self):
        form = super().getForm()
        form.cutDirection = QtGui.QComboBox()
        form.cutDirection.addItem(FreeCAD.Qt.translate("PathTurn", "Radial - outward in X"), "Radial")
        form.cutDirection.addItem(FreeCAD.Qt.translate("PathTurn", "Axial - toward bottom in Z"), "Axial")
        layout = form.passOffset.parentWidget().layout()
        row = 5
        layout.addWidget(QtGui.QLabel(FreeCAD.Qt.translate("PathTurn", "Cut direction")), row, 0)
        layout.addWidget(form.cutDirection, row, 1)
        form.setToolTip(FreeCAD.Qt.translate(
            "PathTurn", "Internal clearing and finishing. Containment selects one bore from the job model; "
            "no Base Geometry selection is required. All feed moves stay within containment; "
            "rapids may travel outside it to clearance, using the job Safe Height Offset. "
            "No predrilling, tool-fit, holder or stock-clearance checks."))
        return form

    def setOpFields(self, obj):
        self.form.allowGrooving.hide()
        self.form.cutDirection.setCurrentIndex(self.form.cutDirection.findData(str(obj.CutDirection)))
        self.form.passOffset.setToolTip(FreeCAD.Qt.translate(
            "PathTurn", "Maximum axial spacing for X clearing or radial spacing for Z clearing; "
            "also the normal spacing between finishing contours."))
        self.form.showContainment.setToolTip(FreeCAD.Qt.translate(
            "PathTurn", "Show the magenta limits for tool-reference feed moves. Rapids may leave them to reach clearance. "
            "These are not insert/holder or stock-clearance checks."))

    def getFields(self, obj):
        super().getFields(obj)
        obj.CutDirection = self.form.cutDirection.currentData()

    def getSignalsForUpdate(self, obj):
        return super().getSignalsForUpdate(obj) + [self.form.cutDirection.currentIndexChanged]


Command = PathOpGui.SetupOperation(
    "TurnBore", PathTurnBore.Create, TaskPanelOpPage, "CAM-TurnBore",
    QtCore.QT_TRANSLATE_NOOP("PathTurnBore", "Turn Bore"),
    QtCore.QT_TRANSLATE_NOOP(
        "PathTurnBore", "Clear and finish the model bore selected by containment; no tool-fit or access checks"),
    PathTurnBore.SetupProperties)
FreeCAD.Console.PrintLog("Loading PathTurnBoreGui... done\n")
