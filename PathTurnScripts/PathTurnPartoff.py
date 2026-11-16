# -*- coding: utf-8 -*-

# Copyright (c) 2020 Daniel Wood <s.d.wood.82@gmail.com>
# SPDX-License-Identifier: LGPL-2.0-or-later
# See LICENSE for terms. This software is provided WITHOUT ANY WARRANTY.

import FreeCAD
import Path
import PathScripts.PathUtils as PathUtils
import PathTurnScripts.PathTurnBase as PathTurnBase
from PySide import QtCore

import PathTurnScripts.PathTurnAddonHelpers as PathTurnHelpers

import liblathe.op.partoff as LLP
from liblathe.base.boundbox import BoundBox
from liblathe.base.point import Point
from liblathe.base.segmentgroup import SegmentGroup
from liblathe.tool.tool import Tool

__title__ = "Path Turn Part Operation"
__author__ = "dubstar-04 (Daniel Wood)"
__url__ = "http://www.freecadweb.org"
__doc__ = "Class implementation for turning profiling operations."

FACE_TOLERANCE = 1e-5


def translate(context, text, disambig=None):
    return QtCore.QCoreApplication.translate(context, text, disambig)


def tool_width(tool):
    """Return the axial width of the tool's cutting profile."""
    profile = Tool()
    profile.set_tool_from_segments(PathTurnHelpers.getToolSegments(tool.Shape))
    return profile.get_segmentgroup().boundbox().ZLength()


def parting_containment(obj):
    """Return the kerf: Axial Max is the parting face and Axial Min is one tool width behind it."""
    tool = getattr(getattr(obj, "ToolController", None), "Tool", None)
    if tool is None:
        raise ValueError(translate("PathTurn", "Parting requires a tool controller."))
    from .PathTurnToolBit import post_from_parameters

    if obj.MinDiameter.Value >= obj.MaxDiameter.Value:
        raise ValueError(translate(
            "PathTurn", "Minimum diameter is equal or greater than maximum diameter"))
    sign = -1 if post_from_parameters({"ToolPost": tool.ToolPost}) == "Rear" else 1
    face = obj.StartDepth.Value
    return BoundBox(Point(sign * obj.MinDiameter.Value / 2, face - tool_width(tool)),
                    Point(sign * obj.MaxDiameter.Value / 2, face))


def model_z_min(job):
    """Return the back face of the job's models, the default parting face."""
    return job.Proxy.modelBoundBox(job).ZMin


class ObjectTurnPart(PathTurnBase.ObjectOp):
    '''Proxy class for turning Part operations.'''

    uses_pass_offset = False

    def initOperation(self, obj):
        super().initOperation(obj)
        self._addPeckProperties(obj)
        self.setEditorModes(obj, self.opFeatures(obj))

    def opOnDocumentRestored(self, obj):
        super().opOnDocumentRestored(obj)
        self._addPeckProperties(obj)
        self.setEditorModes(obj, self.opFeatures(obj))

    @staticmethod
    def _addPeckProperties(obj):
        if not hasattr(obj, "RetractionMode"):
            obj.addProperty("App::PropertyEnumeration", "RetractionMode", "Turn Path", translate(
                "PathTurn", "None parts off in one feed. Partial Retract steps and backs off one "
                "tool width. Full Retract steps and retracts to the cut start."))
            obj.RetractionMode = PathTurnBase.RETRACTION_MODES
            obj.RetractionMode = PathTurnBase.NO_RETRACT
        if not hasattr(obj, "PeckDepth"):
            obj.addProperty("App::PropertyLength", "PeckDepth", "Turn Path", translate(
                "PathTurn", "Maximum radial depth per peck."))
            obj.PeckDepth = 1.0

    def opOnChanged(self, obj, prop):
        super().opOnChanged(obj, prop)
        if prop == "RetractionMode":
            self.setEditorModes(obj, self.opFeatures(obj))

    def setEditorModes(self, obj, features):
        super().setEditorModes(obj, features)
        # Axial Min is derived from the tool width.
        if hasattr(obj, "FinalDepth"):
            obj.setEditorMode("FinalDepth", 2)
        if hasattr(obj, "RetractionMode") and hasattr(obj, "PeckDepth"):
            pecking = str(obj.RetractionMode) != PathTurnBase.NO_RETRACT
            obj.setEditorMode("PeckDepth", 0 if pecking else 2)

    def opSetDefaultValues(self, obj, job):
        super().opSetDefaultValues(obj, job)
        obj.OpStartDepth = model_z_min(job)

    def opUpdateDepths(self, obj):
        super().opUpdateDepths(obj)
        job = PathUtils.findParentJob(obj)
        if job is not None:
            obj.OpStartDepth = model_z_min(job)

    def getProps(self, obj):
        return {**super().getProps(obj),
                **PathTurnBase.peck_parameters(obj, obj.PeckDepth.Value)}

    def getContainment(self, obj):
        return parting_containment(obj)

    def checkDepths(self, obj):
        """Check the derived kerf instead of the hidden Final Depth."""
        try:
            parting_containment(obj)
        except ValueError as error:
            FreeCAD.Console.PrintError(f"{obj.Label}: {error}\n")
            return False
        return True

    def op_generate_gcode(self, obj, turnTool):
        '''
        Generate GCode for the op
        '''
        containmentBounds = parting_containment(obj)
        outline = SegmentGroup()
        for segment in self.part_outline:
            outline.addSegment(segment)
        part_z_min = outline.boundbox().ZMin
        if containmentBounds.ZMax > part_z_min + FACE_TOLERANCE:
            raise ValueError(translate(
                "PathTurn", "Axial Max ({face:.3f} mm) is inside the part. "
                "Move it to {limit:.3f} mm or below.").format(
                    face=containmentBounds.ZMax, limit=part_z_min))

        PartOP = LLP.PartoffOP()
        PartOP.setParams(self.getProps(obj))
        PartOP.add_containment(containmentBounds)
        PartOP.add_stock(PathTurnHelpers.getStock(obj))

        PartOP.addPartSegments(self.part_outline)
        PartOP.add_tool(turnTool)

        PathCode = PartOP.getGCode()

        for command in PathCode:
            pathCommand = Path.Command(command.get_movement(), command.getParams())
            self.commandlist.append(pathCommand)


def SetupProperties():
    return ["RetractionMode", "PeckDepth"]


def Create(name, obj=None, parentJob=None):
    '''Create(name) ... Creates and returns a TurnPart operation.'''
    if obj is None:
        obj = FreeCAD.ActiveDocument.addObject("Path::FeaturePython", name)
    obj.Proxy = ObjectTurnPart(obj, name, parentJob)
    return obj
