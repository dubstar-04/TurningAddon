# -*- coding: utf-8 -*-

# Copyright (c) 2019 Daniel Wood <s.d.wood.82@gmail.com>
# SPDX-License-Identifier: LGPL-2.0-or-later
# See LICENSE for terms. This software is provided WITHOUT ANY WARRANTY.

import math

import FreeCAD
import Path
import Path.Log as PathLog
import Path.Op.Base as PathOp
import PathScripts.PathUtils as PathUtils
import PathTurnScripts.PathTurnAddonHelpers as PathTurnHelpers
from PathTurnScripts.PathTurnSpindle import spindle_commands

from PySide import QtCore

from liblathe.op.base import Direction, MachiningMode
from liblathe.tool.tool import Tool, ToolSide

__title__ = "Path Turn Base Operation"
__author__ = "dubstar-04 (Daniel Wood)"
__url__ = "http://www.freecadweb.org"
__doc__ = "Base class implementation for turning operations."


# Qt translation handling
def translate(context, text, disambig=None):
    return QtCore.QCoreApplication.translate(context, text, disambig)


LOGLEVEL = False

if LOGLEVEL:
    PathLog.setLevel(PathLog.Level.DEBUG, PathLog.thisModule())
    PathLog.trackModule(PathLog.thisModule())
else:
    PathLog.setLevel(PathLog.Level.INFO, PathLog.thisModule())


NO_RETRACT = "None"
PARTIAL_RETRACT = "Partial Retract"
FULL_RETRACT = "Full Retract"
RETRACTION_MODES = [NO_RETRACT, PARTIAL_RETRACT, FULL_RETRACT]
SPINDLE_MODE_RPM = "RPM"
SPINDLE_MODE_CSS = "CSS"
SPINDLE_MODE_PROPERTY = "TurnSpindleMode"
SURFACE_SPEED_PROPERTY = "TurnSurfaceSpeed"
MAX_SPINDLE_SPEED_PROPERTY = "TurnMaxSpindleSpeed"


def job_machine(obj):
    """Return the machine configured on the operation's Job, or None."""
    job = PathUtils.findParentJob(obj)
    get_machine = getattr(getattr(job, "Proxy", None), "getMachine", None)
    return get_machine() if get_machine else None


def machine_outputs_imperial(machine):
    """Return True if the machine's new-style post output units are imperial (G20)."""
    units = getattr(getattr(machine, "output", None), "units", None)
    return getattr(units, "value", units) == "imperial"


def configured_machine_max_rpm(obj, machine=None):
    """Return the sole configured rotary toolhead's max RPM, or zero if unavailable."""
    if machine is None:
        machine = job_machine(obj)
    if machine is None:
        return 0

    rotary_toolheads = [
        toolhead for toolhead in getattr(machine, "toolheads", ())
        if getattr(getattr(toolhead, "toolhead_type", None), "value",
                   getattr(toolhead, "toolhead_type", None)) == "rotary"
    ]
    if len(rotary_toolheads) != 1:
        return 0

    max_rpm = float(rotary_toolheads[0].max_rpm or 0)
    return math.floor(max_rpm) if math.isfinite(max_rpm) and max_rpm > 0 else 0


def ensure_turning_spindle_properties(controller, obj):
    """Add persistent Addon spindle settings to a Tool Controller."""
    if controller is None:
        return

    if not hasattr(controller, SPINDLE_MODE_PROPERTY):
        controller.addProperty(
            "App::PropertyEnumeration", SPINDLE_MODE_PROPERTY, "Turning",
            translate("PathTurn", "Spindle speed control mode"))
        setattr(controller, SPINDLE_MODE_PROPERTY, [SPINDLE_MODE_RPM, SPINDLE_MODE_CSS])
        setattr(controller, SPINDLE_MODE_PROPERTY, SPINDLE_MODE_RPM)

    if not hasattr(controller, SURFACE_SPEED_PROPERTY):
        controller.addProperty(
            "App::PropertyFloat", SURFACE_SPEED_PROPERTY, "Turning",
            translate("PathTurn", "Constant surface speed in metres per minute"))
        setattr(controller, SURFACE_SPEED_PROPERTY, 0.0)

    if not hasattr(controller, MAX_SPINDLE_SPEED_PROPERTY):
        controller.addProperty(
            "App::PropertyInteger", MAX_SPINDLE_SPEED_PROPERTY, "Turning",
            translate("PathTurn", "Maximum spindle speed in RPM"))
        setattr(controller, MAX_SPINDLE_SPEED_PROPERTY, configured_machine_max_rpm(obj))
    elif getattr(controller, MAX_SPINDLE_SPEED_PROPERTY) <= 0:
        machine_max_rpm = configured_machine_max_rpm(obj)
        if machine_max_rpm > 0:
            setattr(controller, MAX_SPINDLE_SPEED_PROPERTY, machine_max_rpm)


def peck_parameters(obj, peck_depth):
    """Return LibLathe peck parameters for the operation's RetractionMode."""
    from liblathe.op.base import RetractMode

    mode = str(obj.RetractionMode)
    return {
        "peck_depth": peck_depth if mode != NO_RETRACT else 0.0,
        "retract_mode": (RetractMode.PARTIAL_RETRACT if mode == PARTIAL_RETRACT
                         else RetractMode.FULL_RETRACT),
    }


class ObjectOp(PathOp.ObjectOp):
    '''Base class for proxy objects of all turning operations.'''

    supports_css = True
    uses_pass_offset = True
    uses_finish_passes = False
    uses_stock_to_leave = False
    uses_allow_grooving = False
    pass_offset_label = translate("TurnPath", "Pass Offset")
    has_finish_offset = False
    supports_internal_mode = False
    supports_direction_control = True
    direction_tooltip = translate("TurnPath", "Cutting direction")

    def opFeatures(self, obj):
        '''opFeatures(obj) ... returns the OR'ed list of features used and supported by the operation.'''
        return PathOp.FeatureDiameters | PathOp.FeatureTool | PathOp.FeatureDepths | PathOp.FeatureCoolant

    @classmethod
    def optional_parameters(cls):
        """Return (property name, used by this operation) for the shared optional parameters."""
        return (("PassOffset", cls.uses_pass_offset),
                ("FinishPasses", cls.uses_finish_passes),
                ("StockToLeave", cls.uses_stock_to_leave),
                ("AllowGrooving", cls.uses_allow_grooving))

    def initOperation(self, obj):
        '''initOperation(obj)'''

        if self.uses_pass_offset:
            obj.addProperty("App::PropertyLength", "PassOffset", "Turn Path", self.pass_offset_label)
            obj.PassOffset = 1.0
        if self.uses_finish_passes:
            obj.addProperty("App::PropertyInteger", "FinishPasses", "Turn Path",
                            translate("TurnPath", "Number of Finish Passes"))
            obj.FinishPasses = 2
        if self.uses_stock_to_leave:
            obj.addProperty("App::PropertyFloat", "StockToLeave", "Turn Path",
                            translate("TurnPath", "Distance for stock to leave uncut"))
            obj.StockToLeave = 0
        if self.uses_allow_grooving:
            obj.addProperty("App::PropertyBool", "AllowGrooving", "Turn Path",
                            translate("TurnPath", "Minimum Diameter for Operation"))
        if self.has_finish_offset:
            obj.addProperty("App::PropertyLength", "FinishPassOffset", "Turn Path",
                            translate("TurnPath", "Finish Pass Offset"))
            obj.FinishPassOffset = 0.0
        if self.supports_internal_mode:
            self._addModeAndDirection(obj)
        self.setEditorModes(obj, self.opFeatures(obj))

    def opOnDocumentRestored(self, obj):
        super().opOnDocumentRestored(obj)
        if self.supports_css:
            ensure_turning_spindle_properties(getattr(obj, "ToolController", None), obj)
        if self.supports_internal_mode:
            self._addModeAndDirection(obj)

    def onChanged(self, obj, prop):
        parent = getattr(super(), "onChanged", None)
        if parent is not None:
            parent(obj, prop)
        if (self.supports_internal_mode and self.supports_direction_control
                and prop == "Mode" and hasattr(obj, "Direction")):
            obj.Direction = self._defaultDirection(obj).value
        if prop == "ToolController" and self.supports_css:
            ensure_turning_spindle_properties(getattr(obj, "ToolController", None), obj)

    @staticmethod
    def _defaultDirection(obj):
        internal = str(getattr(obj, "Mode", "")) == MachiningMode.INTERNAL.value
        return Direction.RADIAL if internal else Direction.NEGATIVE_Z

    def _addModeAndDirection(self, obj):
        self._addEnumeration(obj, "Mode", MachiningMode, MachiningMode.EXTERNAL,
                             translate("TurnPath", "Machining mode"))
        if self.supports_direction_control:
            self._addEnumeration(obj, "Direction", Direction, self._defaultDirection(obj),
                                 self.direction_tooltip)

    @staticmethod
    def _addEnumeration(obj, name, enum, default, tooltip):
        """Add or refresh an enumeration property whose choices are the enum values."""
        values = [member.value for member in enum]
        created = not hasattr(obj, name)
        if created:
            obj.addProperty("App::PropertyEnumeration", name, "Turn Path", tooltip)
        current = default.value if created else str(getattr(obj, name))
        if created or obj.getEnumerationsOfProperty(name) != values:
            setattr(obj, name, values)
            setattr(obj, name, current if current in values else default.value)

    def setEditorModes(self, obj, features):
        super().setEditorModes(obj, features)
        for name, used in self.optional_parameters():
            if hasattr(obj, name):
                obj.setEditorMode(name, 0 if used else 2)
        for name in ("OpStartDepth", "OpFinalDepth", "OpToolDiameter", "OpStockZMax", "OpStockZMin"):
            if hasattr(obj, name):
                obj.setEditorMode(name, 2)

    def opExecute(self, obj):
        '''opExecute(obj) ... processes all Base features
        '''
        PathLog.track()
        controller = getattr(obj, "ToolController", None)
        if self.supports_css:
            ensure_turning_spindle_properties(controller, obj)
        self.tool = None
        self.minDia = obj.MinDiameter.Value
        self.maxDia = obj.MaxDiameter.Value
        if (getattr(obj.Proxy, "getContainment", None) is None
                and self.minDia >= self.maxDia):
            raise RuntimeError(translate(
                'PathTurn', "Minimum diameter is equal or greater than maximum diameter"))
        bounds = PathTurnHelpers.getContainment(obj)
        radial_min, radial_max = sorted((abs(bounds.XMin), abs(bounds.XMax)))

        if not all(math.isfinite(value) for value in (
                radial_min, radial_max, bounds.ZMin, bounds.ZMax)):
            raise RuntimeError(translate('PathTurn', "Containment limits must be finite"))

        if radial_min >= radial_max:
            raise RuntimeError(translate('PathTurn', "Minimum diameter is equal or greater than maximum diameter"))

        if self.minDia < 0 or self.maxDia < 0:
            raise RuntimeError(translate('PathTurn', "Diameter values must be non-negative"))

        if bounds.ZMin >= bounds.ZMax:
            raise RuntimeError(translate('PathTurn', "Start depth is equal or less than final depth"))

        # Clear any existing gcode
        path = obj.Path
        path.Commands = []
        obj.Path = path

        if self.uses_pass_offset:
            if not math.isfinite(obj.PassOffset.Value) or obj.PassOffset.Value <= 0:
                raise RuntimeError(translate(
                    'PathTurn', "{name} must be finite and positive").format(name=self.pass_offset_label))

        self.part_outline = self.get_part_outline(obj)
        self.generate_gcode(obj)
        self._apply_spindle_mode(obj)

    def _apply_spindle_mode(self, obj):
        controller = getattr(obj, "ToolController", None)
        mode = str(getattr(controller, SPINDLE_MODE_PROPERTY, SPINDLE_MODE_RPM))
        if mode not in (SPINDLE_MODE_RPM, SPINDLE_MODE_CSS):
            raise RuntimeError(translate("PathTurn", "Unknown spindle speed control mode."))
        if mode != SPINDLE_MODE_CSS:
            return

        prefix_count = 1 + bool(obj.Comment)
        if len(self.commandlist) <= prefix_count:
            return

        spindle_speed = float(getattr(controller, "SpindleSpeed", 0) or 0)
        surface_speed = float(getattr(controller, SURFACE_SPEED_PROPERTY, 0) or 0)
        max_rpm = int(getattr(controller, MAX_SPINDLE_SPEED_PROPERTY, 0) or 0)
        machine = job_machine(obj)
        machine_max_rpm = configured_machine_max_rpm(obj, machine)
        try:
            commands = spindle_commands(
                mode, self.supports_css, spindle_speed, surface_speed, max_rpm, machine_max_rpm,
                imperial_output=machine_outputs_imperial(machine))
        except ValueError as error:
            raise RuntimeError(
                translate("PathTurn", str(error)).format(limit=machine_max_rpm)) from error

        for index, (name, params) in enumerate(commands):
            command = Path.Command(name, params)
            if index == 0:
                self.commandlist.insert(prefix_count, command)
            else:
                self.commandlist.append(command)

    def opSetDefaultValues(self, obj, job):
        obj.OpStartDepth = job.Stock.Shape.BoundBox.ZMax
        obj.OpFinalDepth = job.Stock.Shape.BoundBox.ZMin
        if not self.isToolSupported(obj, getattr(obj.ToolController, "Tool", None)):
            obj.ToolController = next(
                (controller for controller in job.Tools.Group
                 if self.isToolSupported(obj, controller.Tool)), None)
            if obj.ToolController is not None and hasattr(obj, "OpToolDiameter"):
                obj.OpToolDiameter = obj.ToolController.Tool.Diameter

    def isToolSupported(self, obj, tool):
        from .PathTurnToolBit import is_drill_tool

        if is_drill_tool(tool) or getattr(tool, "ToolPost", None) not in ("Front", "Rear"):
            return False
        return getattr(tool, "Mode", None) in (None, self.required_tool_mode(obj))

    def required_tool_mode(self, obj=None):
        """Return the tool Mode string required by this operation."""
        if self.supports_internal_mode and obj is not None:
            return MachiningMode(str(obj.Mode)).value
        return MachiningMode.EXTERNAL.value

    def opUpdateDepths(self, obj):
        obj.OpStartDepth = obj.OpStockZMax
        obj.OpFinalDepth = obj.OpStockZMin
        self.setEditorModes(obj, self.opFeatures(obj))

    def getProps(self, obj):
        parentJob = PathUtils.findParentJob(obj)

        params = {
            'hfeed': obj.ToolController.HorizFeed.Value,
            'vfeed': obj.ToolController.VertFeed.Value,
            'clearance': parentJob.SetupSheet.SafeHeightOffset.Value,
        }
        if self.uses_pass_offset:
            params['pass_offset'] = obj.PassOffset.Value
        if self.uses_finish_passes:
            params['finish_passes'] = obj.FinishPasses
        if self.uses_stock_to_leave:
            params['stock_to_leave'] = obj.StockToLeave
        if self.uses_allow_grooving:
            params['allow_grooving'] = obj.AllowGrooving
        if self.supports_internal_mode:
            params["mode"] = MachiningMode(str(obj.Mode))
            if self.supports_direction_control:
                params["direction"] = Direction(str(obj.Direction))
        return params

    def get_part_outline(self, obj):
        if self.supports_internal_mode and str(obj.Mode) == MachiningMode.INTERNAL.value:
            return PathTurnHelpers.getInternalOutline(obj, self.model)
        return PathTurnHelpers.getPartOutline(base.Shape for base in self.model)

    def generate_gcode(self, obj):
        '''
        Base function to generate gcode for the OP by writing path command to self.commandlist
        Calls operations op_generate_gcode.
        '''
        tool_mode = getattr(obj.ToolController.Tool, "Mode", None)
        required_mode = self.required_tool_mode(obj)
        if tool_mode not in (None, required_mode):
            raise RuntimeError(translate(
                "PathTurn", "This operation needs an {required} tool, but the selected tool is {mode}.").format(
                    required=required_mode, mode=tool_mode))
        if getattr(obj.ToolController.Tool, "Compensation", "Tip Tangent") != "Tip":
            from liblathe.version import __version__
            from packaging.version import Version

            if Version(__version__) < Version("0.0.8"):
                raise RuntimeError(translate(
                    "PathTurn", "Compensated tool references require LibLathe 0.0.8 or later in FreeCAD's Python environment."))
        turnTool = Tool()
        from .PathTurnToolBit import post_from_parameters

        post = post_from_parameters({"ToolPost": obj.ToolController.Tool.ToolPost})
        turnTool.side = ToolSide.NEAR if post == "Front" else ToolSide.FAR
        turnTool.set_tool_from_segments(
            PathTurnHelpers.getToolSegments(obj.ToolController.Tool.Shape))
        if post == "Rear":
            from liblathe.op.base import reflect_x_segments

            outline = self.part_outline
            try:
                self.part_outline = reflect_x_segments(outline)
                self.op_generate_gcode(obj, turnTool)
            finally:
                self.part_outline = outline
        else:
            self.op_generate_gcode(obj, turnTool)

    def op_generate_gcode(self, obj, turnTool):
        '''op_generate_gcode(obj) ... overwrite to set initial default values.
        Called after the receiver has been fully created with all properties.
        Should be overwritten by subclasses.'''
        pass  # pylint: disable=unnecessary-pass
