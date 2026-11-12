"""FreeCAD task panel and command for external threading."""

from pathlib import Path

import FreeCAD
import FreeCADGui
import Path.Base.Gui.Util as PathGuiUtil
import Path.Op.Gui.Base as PathOpGui
from PySide import QtCore

from . import PathTurnBaseGui
from . import PathTurnThread


_icon = Path(__file__).parent.parent / "Gui/Resources/Icons/CAM-TurnThread.svg"


class TaskPanelOpPage(PathTurnBaseGui.TaskPanelTurnBase):
    def getIcon(self, obj):
        return str(_icon)

    def getFields(self, obj):
        super().getFields(obj)
        PathGuiUtil.updateInputField(obj, "Pitch", self.form.pitch)
        obj.SpringPasses = self.form.springPasses.value()

    def setOpFields(self, obj):
        for name in (
                "label_6", "stockToLeave", "label_5", "finishPasses",
                "finishPassOffsetLabel", "finishPassOffset", "allowGrooving"):
            getattr(self.form, name).hide()

        self.form.pitchLabel.show()
        self.form.pitch.show()
        self.form.springPassesLabel.show()
        self.form.springPasses.show()
        self.form.pitch.setText(obj.Pitch.UserString)
        self.form.pitch.setToolTip(FreeCAD.Qt.translate(
            "PathTurn", "Required pitch/lead per spindle revolution in the current length units. "
            "G33 uses this value for spindle synchronization."))
        self.form.passOffset.setToolTip(FreeCAD.Qt.translate(
            "PathTurn", "Maximum radial infeed per pass. The final pass is shortened to reach the root radius."))
        self.form.springPasses.setValue(obj.SpringPasses)
        self.form.setToolTip(FreeCAD.Qt.translate(
            "PathTurn", "Straight single-start external threading with spindle-synchronized G33. "
            "Provide prepared run-in and run-out space in the selected Z range. "
            "Configure spindle index synchronization, spindle direction and fixed RPM. "
            "Thread paths are not represented by the axisymmetric stock guide."))

    def getSignalsForUpdate(self, obj):
        return (super().getSignalsForUpdate(obj)
                + [self.form.pitch.editingFinished, self.form.springPasses.valueChanged])


Command = PathOpGui.SetupOperation(
    "TurnThread", PathTurnThread.Create, TaskPanelOpPage, "CAM-TurnThread",
    QtCore.QT_TRANSLATE_NOOP("PathTurnThread", "Turn Thread"),
    QtCore.QT_TRANSLATE_NOOP(
        "PathTurnThread", "Create straight single-start external threads using spindle-synchronized G33"),
    PathTurnThread.SetupProperties)
