"""Straight single-start external threading with spindle-synchronized G33."""

import json
from pathlib import Path as FilePath

import FreeCAD
import Path
import PathScripts.PathUtils as PathUtils

from . import PathTurnBase
from . import PathTurnAddonHelpers as helpers


_THREAD_DATA_PATH = FilePath(__file__).parent.parent / "Data" / "thread_dimensions.json"
with _THREAD_DATA_PATH.open(encoding="utf-8") as _stream:
    _THREAD_DIMENSIONS = json.load(_stream)


class ThreadData:
    """Lookups for the bundled external thread dimensions."""

    @staticmethod
    def _standard(standard):
        try:
            return _THREAD_DIMENSIONS["standards"][standard]
        except KeyError as error:
            raise ValueError(f"Unknown thread standard: {standard}") from error

    @staticmethod
    def standards():
        return tuple(_THREAD_DIMENSIONS["standards"])

    @staticmethod
    def sizes(standard):
        return tuple(ThreadData._standard(standard)["sizes"])

    @staticmethod
    def pitches(standard, size):
        """Return {designation: pitch record} for a nominal size, e.g. M10."""
        try:
            return ThreadData._standard(standard)["sizes"][size]["pitches"]
        except KeyError as error:
            raise ValueError(f"Unknown thread size {size!r} for {standard!r}") from error

    @staticmethod
    def size_of(standard, name):
        for size, record in ThreadData._standard(standard)["sizes"].items():
            if name in record["pitches"]:
                return size
        raise ValueError(f"Unknown thread {name!r} for {standard!r}")

    @staticmethod
    def fits(standard, name):
        """Return the fit classes available for a thread designation, e.g. M10 x 1.25."""
        return tuple(ThreadData.pitches(standard, ThreadData.size_of(standard, name))[name]["fits"])

    @staticmethod
    def fit_name(standard, fit):
        return FreeCAD.Qt.translate("PathTurn", ThreadData._standard(standard)["fits"].get(fit, fit))

    @staticmethod
    def default_fit(standard):
        return ThreadData._standard(standard)["default_fit"]

    @staticmethod
    def midpoint_targets(standard, fit, name):
        """Return pitch and tolerance-band midpoint diameters in millimetres."""
        record = ThreadData.pitches(standard, ThreadData.size_of(standard, name))[name]
        try:
            ranges = record["fits"][fit]
        except KeyError as error:
            raise ValueError(f"Fit {fit!r} is not available for {name!r}") from error
        return {
            "pitch_mm": record["pitch_mm"],
            "major_diameter_mm": sum(ranges["major_mm"]) / 2,
            "pitch_diameter_mm": sum(ranges["pitch_diameter_mm"]) / 2,
            "minor_diameter_mm": sum(ranges["minor_mm"]) / 2,
        }


class ObjectTurnThread(PathTurnBase.ObjectOp):
    pass_offset_label = FreeCAD.Qt.translate("TurnPath", "Radial Pass Offset")
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
        if not hasattr(obj, "ThreadStandard"):
            obj.addProperty(
                "App::PropertyEnumeration", "ThreadStandard", "Thread",
                FreeCAD.Qt.translate("PathTurn", "Thread standard"))
            obj.ThreadStandard = ["Custom", *ThreadData.standards()]
        else:
            standards = ["Custom", *ThreadData.standards()]
            if obj.getEnumerationsOfProperty("ThreadStandard") != standards:
                legacy = {"ISO Metric": "Metric", "Unified": "Imperial"}
                current = str(obj.ThreadStandard)
                obj.ThreadStandard = standards
                current = legacy.get(current, current)
                obj.ThreadStandard = current if current in standards else "Custom"
        if not hasattr(obj, "ThreadSize"):
            obj.addProperty(
                "App::PropertyString", "ThreadSize", "Thread",
                FreeCAD.Qt.translate("PathTurn", "Standard thread size"))
            obj.ThreadSize = ""
        if not hasattr(obj, "ThreadClass"):
            obj.addProperty(
                "App::PropertyString", "ThreadClass", "Thread",
                FreeCAD.Qt.translate("PathTurn", "Thread tolerance class"))
            obj.ThreadClass = ""
        is_custom = obj.ThreadStandard == "Custom"
        obj.setEditorMode("Pitch", 0 if is_custom else 2)
        obj.setEditorMode("SpringPasses", 0)
        obj.setEditorMode("ThreadStandard", 2)
        obj.setEditorMode("ThreadSize", 2)
        obj.setEditorMode("ThreadClass", 2)
        for name in ("MinDiameter", "MaxDiameter"):
            if hasattr(obj, name):
                obj.setEditorMode(name, 0 if is_custom else 2)

    def setEditorModes(self, obj, features):
        super().setEditorModes(obj, features)
        for name in ("FinishPasses", "StockToLeave", "AllowGrooving"):
            if hasattr(obj, name):
                obj.setEditorMode(name, 2)
        if hasattr(obj, "ThreadStandard"):
            is_custom = obj.ThreadStandard == "Custom"
            obj.setEditorMode("Pitch", 0 if is_custom else 2)
            for name in ("MinDiameter", "MaxDiameter"):
                if hasattr(obj, name):
                    obj.setEditorMode(name, 0 if is_custom else 2)

    def setThreadPreset(self, obj, standard, thread_class=None, name=None):
        if standard == "Custom":
            obj.ThreadStandard = "Custom"
            obj.ThreadSize = ""
            obj.ThreadClass = ""
            self.setEditorModes(obj, self.opFeatures(obj))
            return None

        expressions = dict(obj.ExpressionEngine)
        constrained = [property_name for property_name in ("Pitch", "MinDiameter", "MaxDiameter")
                       if property_name in expressions]
        if constrained:
            raise ValueError(
                "Clear expressions on {} before selecting a standard thread size.".format(
                    ", ".join(constrained)))

        targets = ThreadData.midpoint_targets(standard, thread_class, name)
        obj.ThreadStandard = standard
        obj.ThreadClass = thread_class
        obj.ThreadSize = name
        obj.Pitch = targets["pitch_mm"]
        obj.MinDiameter = targets["minor_diameter_mm"]
        obj.MaxDiameter = targets["major_diameter_mm"]
        self.setEditorModes(obj, self.opFeatures(obj))
        return targets

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
