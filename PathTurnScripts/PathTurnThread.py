"""Straight single-start external threading with spindle-synchronized G33."""

import FreeCAD
import Path
import PathScripts.PathUtils as PathUtils

from . import PathTurnBase
from . import PathTurnAddonHelpers as helpers


class ObjectTurnThread(PathTurnBase.ObjectOp):
    pass_offset_label = FreeCAD.Qt.translate("TurnPath", "Radial Infeed per Pass")
    supports_stock_guide = False
    stock_guide_unavailable_reason = FreeCAD.Qt.translate(
        "PathTurn", "The stock guide cannot represent helical thread geometry.")

    def initOperation(self, obj):
        had_pass_offset = hasattr(obj, "PassOffset")
        super().initOperation(obj)
        if not had_pass_offset:
            obj.PassOffset = 0.1
        self._addThreadProperties(obj)

    def opOnDocumentRestored(self, obj):
        super().opOnDocumentRestored(obj)
        self._addThreadProperties(obj)

    @staticmethod
    def _addThreadProperties(obj):
        if not hasattr(obj, "Pitch"):
            obj.addProperty(
                "App::PropertyLength", "Pitch", "Thread",
                FreeCAD.Qt.translate("PathTurn", "Thread pitch / lead"))
            obj.Pitch = 0
        if not hasattr(obj, "SpringPasses"):
            obj.addProperty(
                "App::PropertyInteger", "SpringPasses", "Thread",
                FreeCAD.Qt.translate("PathTurn", "Full-depth spring passes"))
            obj.SpringPasses = 0
        obj.setEditorMode("Pitch", 0)
        obj.setEditorMode("SpringPasses", 0)

    def setEditorModes(self, obj, features):
        super().setEditorModes(obj, features)
        for name in ("FinishPasses", "StockToLeave", "AllowGrooving"):
            if hasattr(obj, name):
                obj.setEditorMode(name, 2)

    def getProps(self, obj):
        job = PathUtils.findParentJob(obj)
        if job is None:
            raise ValueError(FreeCAD.Qt.translate("PathTurn", "Threading requires a parent CAM job."))
        return {
            "pitch": obj.Pitch.Value,
            "pass_offset": obj.PassOffset.Value,
            "spring_passes": obj.SpringPasses,
            "clearance": job.SetupSheet.SafeHeightOffset.Value,
        }

    def op_generate_gcode(self, obj, turnTool):
        try:
            from liblathe.op.thread import ThreadOP
        except ModuleNotFoundError as error:
            if error.name != "liblathe.op.thread":
                raise
            raise RuntimeError(FreeCAD.Qt.translate(
                "PathTurn", "Turn Thread requires a LibLathe build containing ThreadOP. "
                "Install it into FreeCAD's Python environment, then restart FreeCAD.")) from error

        operation = ThreadOP()
        operation.setParams(self.getProps(obj))
        operation.add_containment(helpers.getContainment(obj))
        operation.add_stock(helpers.getStock(obj))
        operation.addPartSegments(self.part_outline)
        operation.add_tool(turnTool)
        commands = operation.getGCode()
        if not operation.tool_paths:
            raise RuntimeError(FreeCAD.Qt.translate(
                "PathTurn", "No threading passes were generated. Check pitch, radial infeed and containment."))
        self.commandlist.append(Path.Command("G40"))
        # TODO: Emit G33 directly once FreeCAD's path display and simulation support it.
        # Until then synchronized passes are stored as G1 with a K lead so they display
        # as feeds; the turning post-processor rewrites G1 moves carrying K back to G33.
        self.commandlist.extend(
            Path.Command("G1" if command.get_movement() == "G33" else command.get_movement(),
                         command.getParams())
            for command in commands)


def SetupProperties():
    return ["Pitch", "PassOffset", "SpringPasses"]


def Create(name, obj=None, parentJob=None):
    if obj is None:
        obj = FreeCAD.ActiveDocument.addObject("Path::FeaturePython", name)
    obj.Proxy = ObjectTurnThread(obj, name, parentJob)
    return obj
