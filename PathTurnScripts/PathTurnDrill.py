"""Experimental centreline drilling with a native FreeCAD drill ToolBit."""

import math

import FreeCAD
import Path

from . import PathTurnAddonHelpers as helpers
from . import PathTurnBase
from .PathTurnToolBit import is_drill_tool


def getDrill(tool):
    from liblathe.tool.drill import Drill

    if not is_drill_tool(tool):
        raise ValueError(FreeCAD.Qt.translate("PathTurn", "Turn Drill requires a Drill ToolBit."))
    return Drill(tool.Diameter.Value, tool.TipAngle.Value, tool.Length.Value)


class ObjectTurnDrill(PathTurnBase.ObjectOp):
    centreline_drilling = True
    uses_pass_offset = False

    def isToolSupported(self, obj, tool):
        return is_drill_tool(tool)

    def setEditorModes(self, obj, features):
        super().setEditorModes(obj, features)
        for name in ("MinDiameter", "MaxDiameter"):
            if hasattr(obj, name):
                obj.setEditorMode(name, 2)

    def opExecute(self, obj):
        path = obj.Path
        path.Commands = []
        obj.Path = path
        from liblathe.op.drill import DrillOP

        depths = (obj.StartDepth.Value, obj.FinalDepth.Value)
        if not all(math.isfinite(value) for value in depths) or depths[0] <= depths[1]:
            raise ValueError(FreeCAD.Qt.translate(
                "PathTurn", "Drilling requires finite depths with final tip depth below start depth."))
        feed = obj.ToolController.VertFeed.Value
        clearance = self.getJob(obj).SetupSheet.SafeHeightOffset.Value
        if not math.isfinite(clearance) or clearance <= 0:
            raise ValueError(FreeCAD.Qt.translate(
                "PathTurn", "Set a positive Safe Height Offset in the job Setup Sheet for drilling clearance."))
        drill = getDrill(obj.ToolController.Tool)
        operation = DrillOP()
        operation.add_tool(drill)
        operation.add_containment(helpers.getContainment(obj))
        operation.vfeed = feed
        operation.clearance = clearance
        commands = operation.getGCode()
        self.commandlist.extend(
            Path.Command(command.get_movement(), command.getParams()) for command in commands)


def SetupProperties():
    return []


def Create(name, obj=None, parentJob=None):
    if obj is None:
        obj = FreeCAD.ActiveDocument.addObject("Path::FeaturePython", name)
    obj.Proxy = ObjectTurnDrill(obj, name, parentJob)
    return obj
