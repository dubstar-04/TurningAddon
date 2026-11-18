"""Experimental centreline drilling with a native FreeCAD drill ToolBit."""

import math

import FreeCAD
import Path

from . import PathTurnAddonHelpers as helpers
from . import PathTurnBase
from .PathTurnBase import NO_RETRACT, RETRACTION_MODES, peck_parameters
from .PathTurnToolBit import is_drill_tool


def getDrill(tool):
    from liblathe.tool.drill import Drill

    if not is_drill_tool(tool):
        raise ValueError(FreeCAD.Qt.translate("PathTurn", "Turn Drill requires a Drill ToolBit."))
    return Drill(tool.Diameter.Value, tool.TipAngle.Value, tool.Length.Value)


class ObjectTurnDrill(PathTurnBase.ObjectOp):
    centreline_drilling = True
    supports_css = False
    uses_pass_offset = False

    def initOperation(self, obj):
        super().initOperation(obj)
        obj.addProperty("App::PropertyEnumeration", "RetractionMode", "Turn Path", FreeCAD.Qt.translate(
            "PathTurn", "None drills to depth in one feed. Partial Retract steps and retracts one drill "
            "diameter. Full Retract steps and retracts to the clearance."))
        obj.RetractionMode = RETRACTION_MODES
        obj.RetractionMode = NO_RETRACT
        obj.addProperty("App::PropertyLength", "PeckDepth", "Turn Path", FreeCAD.Qt.translate(
            "PathTurn", "Maximum new depth per step."))
        obj.addProperty("App::PropertyBool", "TipCompensation", "Turn Path", FreeCAD.Qt.translate(
            "PathTurn", "Extend the tip beyond Final Depth so the full drill diameter reaches that depth."))
        self.setEditorModes(obj, self.opFeatures(obj))

    def opSetDefaultValues(self, obj, job):
        super().opSetDefaultValues(obj, job)
        self.applyExpression(obj, "PeckDepth", "OpToolDiameter * 1")

    @staticmethod
    def _length(obj, name):
        # FreeCAD updates OpToolDiameter during execute, after expressions were evaluated.
        expression = dict(obj.ExpressionEngine).get(name)
        if expression:
            return FreeCAD.Units.Quantity(obj.evalExpression(expression)).Value
        return getattr(obj, name).Value

    def opOnChanged(self, obj, prop):
        super().opOnChanged(obj, prop)
        if prop == "RetractionMode":
            self.setEditorModes(obj, self.opFeatures(obj))

    def isToolSupported(self, obj, tool):
        return is_drill_tool(tool)

    def setEditorModes(self, obj, features):
        super().setEditorModes(obj, features)
        for name in ("MinDiameter", "MaxDiameter"):
            if hasattr(obj, name):
                obj.setEditorMode(name, 2)
        if hasattr(obj, "RetractionMode") and hasattr(obj, "PeckDepth"):
            obj.setEditorMode("PeckDepth", 0 if str(obj.RetractionMode) != NO_RETRACT else 2)

    def opExecute(self, obj):
        path = obj.Path
        path.Commands = []
        obj.Path = path
        from liblathe.op.drill import DrillOP

        depths = (obj.StartDepth.Value, obj.FinalDepth.Value)
        if not all(math.isfinite(value) for value in depths) or depths[0] <= depths[1]:
            raise ValueError(FreeCAD.Qt.translate(
                "PathTurn", "Drilling requires finite depths with final depth below start depth."))
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
        operation.setParams({
            **peck_parameters(obj, self._length(obj, "PeckDepth")),
            "reentry_gap_diameters": 1.0,
            "chip_break_retract_diameters": 1.0,
            "tip_compensation": obj.TipCompensation,
        })
        commands = operation.getGCode()
        self.commandlist.extend(
            Path.Command(command.get_movement(), command.getParams()) for command in commands)
        self._apply_spindle_mode(obj)


def SetupProperties():
    return ["RetractionMode", "PeckDepth", "TipCompensation"]


def Create(name, obj=None, parentJob=None):
    if obj is None:
        obj = FreeCAD.ActiveDocument.addObject("Path::FeaturePython", name)
    obj.Proxy = ObjectTurnDrill(obj, name, parentJob)
    return obj
