# -*- coding: utf-8 -*-

# ***************************************************************************
# *                                                                         *
# *   Copyright (c) 2019 Daniel Wood <s.d.wood.82@gmail.com>                *
# *                                                                         *
# *   This program is free software; you can redistribute it and/or modify  *
# *   it under the terms of the GNU Lesser General Public License (LGPL)    *
# *   as published by the Free Software Foundation; either version 2 of     *
# *   the License, or (at your option) any later version.                   *
# *   for detail see the LICENCE text file.                                 *
# *                                                                         *
# *   This program is distributed in the hope that it will be useful,       *
# *   but WITHOUT ANY WARRANTY; without even the implied warranty of        *
# *   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the         *
# *   GNU Library General Public License for more details.                  *
# *                                                                         *
# *   You should have received a copy of the GNU Library General Public     *
# *   License along with this program; if not, write to the Free Software   *
# *   Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  *
# *   USA                                                                   *
# *                                                                         *
# ***************************************************************************

import math

import FreeCAD
import Path.Log as PathLog
import Path.Op.Base as PathOp
import PathScripts.PathUtils as PathUtils
import PathTurnScripts.PathTurnAddonHelpers as PathTurnHelpers

from PySide import QtCore

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


class ObjectOp(PathOp.ObjectOp):
    '''Base class for proxy objects of all turning operations.'''

    uses_pass_offset = True
    pass_offset_label = translate("TurnPath", "Pass Offset")
    has_finish_offset = False

    def opFeatures(self, obj):
        '''opFeatures(obj) ... returns the OR'ed list of features used and supported by the operation.'''
        return PathOp.FeatureDiameters | PathOp.FeatureTool | PathOp.FeatureDepths | PathOp.FeatureCoolant

    def initOperation(self, obj):
        '''initOperation(obj)'''

        obj.addProperty("App::PropertyInteger", "FinishPasses", "Turn Path", translate("TurnPath", "Number of Finish Passes"))
        obj.addProperty("App::PropertyFloat", "StockToLeave", "Turn Path", translate("TurnPath", "Distance for stock to leave uncut"))
        obj.addProperty("App::PropertyBool", "AllowGrooving", "Turn Path", translate("TurnPath", "Minimum Diameter for Operation"))

        obj.addProperty("App::PropertyLength", "PassOffset", "Turn Path", self.pass_offset_label)
        obj.PassOffset = 1.0
        if self.has_finish_offset:
            obj.addProperty("App::PropertyLength", "FinishPassOffset", "Turn Path",
                            translate("TurnPath", "Finish Pass Offset"))
            obj.FinishPassOffset = 0.0
        obj.FinishPasses = 2
        obj.StockToLeave = 0
        self.setEditorModes(obj, self.opFeatures(obj))

    def setEditorModes(self, obj, features):
        super().setEditorModes(obj, features)
        if hasattr(obj, "PassOffset"):
            obj.setEditorMode("PassOffset", 0 if self.uses_pass_offset else 2)
        for name in ("OpStartDepth", "OpFinalDepth", "OpToolDiameter", "OpStockZMax", "OpStockZMin"):
            if hasattr(obj, name):
                obj.setEditorMode(name, 2)

    def opExecute(self, obj):
        '''opExecute(obj) ... processes all Base features
        '''
        PathLog.track()
        self.tool = None
        self.minDia = obj.MinDiameter.Value
        self.maxDia = obj.MaxDiameter.Value

        if self.minDia >= self.maxDia:
            raise RuntimeError(translate('PathTurn', "Minimum diameter is equal or greater than maximum diameter"))

        if self.minDia < 0 or self.maxDia < 0:
            raise RuntimeError(translate('PathTurn', "Diameter values must be non-negative"))

        if obj.StartDepth.Value <= obj.FinalDepth.Value:
            raise RuntimeError(translate('PathTurn', "Start depth is equal or less than final depth"))

        if self.uses_pass_offset:
            if not math.isfinite(obj.PassOffset.Value) or obj.PassOffset.Value <= 0:
                raise RuntimeError(translate(
                    'PathTurn', "{name} must be finite and positive").format(name=self.pass_offset_label))

        self.allowGrooving = obj.AllowGrooving
        self.finishPasses = obj.FinishPasses
        self.stockToLeave = obj.StockToLeave

        # Clear any existing gcode
        path = obj.Path
        path.Commands = []
        obj.Path = path

        self.part_outline = self.get_part_outline(obj)
        self.generate_gcode(obj)

    def opSetDefaultValues(self, obj, job):
        obj.OpStartDepth = job.Stock.Shape.BoundBox.ZMax
        obj.OpFinalDepth = job.Stock.Shape.BoundBox.ZMin
        if not self.isToolSupported(obj, getattr(obj.ToolController, "Tool", None)):
            obj.ToolController = next(
                (controller for controller in job.Tools.Group
                 if self.isToolSupported(obj, controller.Tool)), None)

    def isToolSupported(self, obj, tool):
        from .PathTurnToolBit import is_drill_tool

        if is_drill_tool(tool) or getattr(tool, "ToolPost", None) not in ("Front", "Rear"):
            return False
        return getattr(tool, "Mode", None) in (None, self.required_tool_mode())

    def required_tool_mode(self):
        return "Internal" if getattr(self, "internal_finishing", False) else "External"

    def opUpdateDepths(self, obj):
        obj.OpStartDepth = obj.OpStockZMax
        obj.OpFinalDepth = obj.OpStockZMin
        self.setEditorModes(obj, self.opFeatures(obj))

    def getProps(self, obj):
        parentJob = PathUtils.findParentJob(obj)

        params = {
            'pass_offset': obj.PassOffset.Value,
            'allow_grooving': self.allowGrooving,
            'finish_passes': self.finishPasses,
            'stock_to_leave': self.stockToLeave,
            'hfeed': obj.ToolController.HorizFeed.Value,
            'vfeed': obj.ToolController.VertFeed.Value,
            'clearance': parentJob.SetupSheet.SafeHeightOffset.Value,
        }
        return params

    def get_part_outline(self, obj):
        return PathTurnHelpers.getPartOutline(base.Shape for base in self.model)

    def generate_gcode(self, obj):
        '''
        Base function to generate gcode for the OP by writing path command to self.commandlist
        Calls operations op_generate_gcode.
        '''
        mode = getattr(obj.ToolController.Tool, "Mode", None)
        if mode not in (None, self.required_tool_mode()):
            raise RuntimeError(translate(
                "PathTurn", "This operation needs an {required} tool, but the selected tool is {mode}.").format(
                    required=self.required_tool_mode(), mode=mode))
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
