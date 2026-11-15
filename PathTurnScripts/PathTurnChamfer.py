"""Containment-positioned, equal-distance turning edge breaks."""

from enum import Enum
import math

import FreeCAD
import Path

from liblathe.base.boundbox import BoundBox
from liblathe.base.point import Point
from liblathe.op.base import Direction, MachiningMode

from . import PathTurnAddonHelpers as helpers
from . import PathTurnBase


class ChamferSide(Enum):
    NEGATIVE_Z = "-Z"
    POSITIVE_Z = "+Z"


def chamfer_containment(obj):
    """Return user limits with the inactive radial and axial edges offset by chamfer size."""
    size = obj.ChamferSize.Value
    if not math.isfinite(size) or size <= 0:
        raise ValueError(FreeCAD.Qt.translate(
            "PathTurn", "Chamfer Size must be finite and positive."))

    mode = MachiningMode(str(obj.Mode))
    side = ChamferSide(str(obj.ChamferSide))
    if mode == MachiningMode.EXTERNAL:
        radial_max = obj.MaxDiameter.Value / 2
        radial_min = radial_max - size
        if radial_min < 0:
            raise ValueError(FreeCAD.Qt.translate(
                "PathTurn", "Chamfer Size cannot extend Radial Min past the spindle axis."))
    else:
        radial_min = obj.MinDiameter.Value / 2
        radial_max = radial_min + size

    if side == ChamferSide.NEGATIVE_Z:
        axial_max = obj.StartDepth.Value
        axial_min = axial_max - size
    else:
        axial_min = obj.FinalDepth.Value
        axial_max = axial_min + size

    tool = getattr(getattr(obj, "ToolController", None), "Tool", None)
    from .PathTurnToolBit import post_from_parameters

    post = post_from_parameters({"ToolPost": tool.ToolPost if tool else None})
    sign = -1 if post == "Rear" else 1
    return BoundBox(Point(sign * radial_min, axial_min),
                    Point(sign * radial_max, axial_max))


def containment_corner_index(obj, outline):
    """Find the profile corner at the intersection of the active containment limits."""
    bounds = chamfer_containment(obj)
    mode = MachiningMode(str(obj.Mode))
    side = ChamferSide(str(obj.ChamferSide))
    radial_edges = (abs(bounds.XMin), abs(bounds.XMax))
    radius = max(radial_edges) if mode == MachiningMode.EXTERNAL else min(radial_edges)
    z = bounds.ZMax if side == ChamferSide.NEGATIVE_Z else bounds.ZMin
    points = [edge.start for edge in outline]
    if outline:
        points.append(outline[-1].end)
    matches = [index for index, point in enumerate(points)
               if abs(abs(point.X) - radius) <= 1e-5 and abs(point.Z - z) <= 1e-5]
    if len(matches) != 1:
        raise ValueError(FreeCAD.Qt.translate(
            "PathTurn", "Containment must place its active radial and axial limits "
            "at one profile corner."))
    return matches[0]


def expanded_cutting_containment(bounds, tool, clearance, *, internal=False, rear=False):
    """Include the complete insert compensation around the user-facing chamfer limits."""
    tool_bounds = tool.get_segmentgroup().boundbox()
    radial = max(abs(tool_bounds.XMin), abs(tool_bounds.XMax)) + max(clearance, 0.01)
    axial = max(abs(tool_bounds.ZMin), abs(tool_bounds.ZMax)) + max(clearance, 0.01)
    radial_min, radial_max = bounds.XMin - radial, bounds.XMax + radial
    if internal:
        if rear:
            radial_max = min(0, radial_max)
        else:
            radial_min = max(0, radial_min)
    return BoundBox(
        Point(radial_min, bounds.ZMin - axial),
        Point(radial_max, bounds.ZMax + axial))


class ObjectTurnChamfer(PathTurnBase.ObjectOp):
    supports_internal_mode = True
    supports_direction_control = False

    def opFeatures(self, obj):
        return super().opFeatures(obj)

    def initOperation(self, obj):
        super().initOperation(obj)
        obj.PassOffset = 0.25
        obj.addProperty("App::PropertyLength", "ChamferSize", "Turn Path", FreeCAD.Qt.translate(
            "PathTurn", "Equal distance removed along each adjacent face (45-degree edge break)."))
        obj.ChamferSize = 1.0
        self._addChamferSide(obj)
        self.setEditorModes(obj, self.opFeatures(obj))

    def opOnDocumentRestored(self, obj):
        super().opOnDocumentRestored(obj)
        self._addChamferSide(obj)
        self.setEditorModes(obj, self.opFeatures(obj))

    def _addChamferSide(self, obj):
        self._addEnumeration(obj, "ChamferSide", ChamferSide, ChamferSide.NEGATIVE_Z,
                             FreeCAD.Qt.translate("PathTurn", "Side of the workpiece to chamfer."))

    def setEditorModes(self, obj, features):
        super().setEditorModes(obj, features)
        if hasattr(obj, "ChamferSide") and hasattr(obj, "Mode"):
            radial = ("MaxDiameter" if str(obj.Mode) == MachiningMode.EXTERNAL.value
                      else "MinDiameter")
            axial = ("StartDepth" if str(obj.ChamferSide) == ChamferSide.NEGATIVE_Z.value
                     else "FinalDepth")
            active = {radial, axial}
            for name in ("MinDiameter", "MaxDiameter", "StartDepth", "FinalDepth"):
                if hasattr(obj, name):
                    obj.setEditorMode(name, 0 if name in active else 2)
        if hasattr(obj, "Direction"):
            obj.setEditorMode("Direction", 2)

    def onChanged(self, obj, prop):
        super().onChanged(obj, prop)
        if prop in ("Mode", "ChamferSide"):
            self.setEditorModes(obj, self.opFeatures(obj))

    def getContainment(self, obj):
        return chamfer_containment(obj)

    def checkDepths(self, obj):
        """Check the derived axial limits instead of the stored inactive depth."""
        try:
            bounds = chamfer_containment(obj)
        except ValueError as error:
            FreeCAD.Console.PrintError(f"{obj.Label}: {error}\n")
            return False
        return bounds.ZMin < bounds.ZMax

    def op_generate_gcode(self, obj, turnTool):
        from liblathe.op.chamfer import ChamferOP

        operation = ChamferOP()
        params = self.getProps(obj)
        operation.setParams({
            **params,
            "direction": Direction.RADIAL,
            "chamfer_side": Direction(str(obj.ChamferSide)),
            "chamfer_size": obj.ChamferSize.Value,
            "corner_indices": (containment_corner_index(obj, self.part_outline),),
        })
        operation.add_containment(expanded_cutting_containment(
            chamfer_containment(obj), turnTool, params["clearance"],
            internal=str(obj.Mode) == MachiningMode.INTERNAL.value,
            rear=getattr(obj.ToolController.Tool, "ToolPost", None) == "Rear"))
        operation.add_stock(helpers.getStock(obj))
        operation.addPartSegments(self.part_outline)
        operation.add_tool(turnTool)
        commands = operation.getGCode()
        self.commandlist.extend(
            Path.Command(command.get_movement(), command.getParams()) for command in commands)


def SetupProperties():
    return ["Mode", "ChamferSide", "PassOffset", "ChamferSize"]


def Create(name, obj=None, parentJob=None):
    if obj is None:
        obj = FreeCAD.ActiveDocument.addObject("Path::FeaturePython", name)
    obj.Proxy = ObjectTurnChamfer(obj, name, parentJob)
    return obj
