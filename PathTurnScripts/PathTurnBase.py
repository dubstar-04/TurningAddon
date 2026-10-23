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
import Part
import Path
import Path.Log as PathLog
import Path.Op.Base as PathOp
import PathScripts.PathUtils as PathUtils
# import PathScripts.PathGeom as PathGeom

from PySide import QtCore

if FreeCAD.GuiUp:
    import FreeCADGui

from liblathe.base.point import Point
from liblathe.base.segment import Segment
from liblathe.tool.tool import Tool

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

    def opFeatures(self, obj):
        '''opFeatures(obj) ... returns the OR'ed list of features used and supported by the operation.'''
        return PathOp.FeatureDiameters | PathOp.FeatureTool | PathOp.FeatureDepths | PathOp.FeatureCoolant

    def initOperation(self, obj):
        '''initOperation(obj)'''

        obj.addProperty("App::PropertyLength", "StepOver", "Turn Path", translate("TurnPath", "Operation Stepover"))
        obj.addProperty("App::PropertyInteger", "FinishPasses", "Turn Path", translate("TurnPath", "Number of Finish Passes"))
        obj.addProperty("App::PropertyFloat", "StockToLeave", "Turn Path", translate("TurnPath", "Distance for stock to leave uncut"))
        obj.addProperty("App::PropertyBool", "AllowGrooving", "Turn Path", translate("TurnPath", "Minimum Diameter for Operation"))

        obj.StepOver = FreeCAD.Units.Quantity(1.0, FreeCAD.Units.Length)
        obj.FinishPasses = 2
        obj.StockToLeave = 0

    def opExecute(self, obj):
        '''opExecute(obj) ... processes all Base features
        '''
        PathLog.track()
        self.tool = None
        self.minDia = obj.MinDiameter.Value
        self.maxDia = obj.MaxDiameter.Value

        if self.minDia >= self.maxDia:
            raise RuntimeError(translate('PathTurn', "Minimum diameter is equal or greater than maximum diameter"))

        if obj.StartDepth.Value <= obj.FinalDepth.Value:
            raise RuntimeError(translate('PathTurn', "Start depth is equal or less than final depth"))

        self.startOffset = 0
        self.endOffset = 0
        self.allowGrooving = obj.AllowGrooving
        self.stepOver = obj.StepOver.Value
        self.finishPasses = obj.FinishPasses
        self.stockToLeave = obj.StockToLeave

        # Clear any existing gcode
        obj.Path.Commands = []

        print("Process Geometry")
        self.stock_silhoutte = self.get_stock_silhoutte(obj)
        self.part_outline = self.get_part_outline()
        self.generate_gcode(obj)

    def getProps(self, obj):
        parentJob = PathUtils.findParentJob(obj)

        props = {}
        props['allow_grooving'] = self.allowGrooving
        props['step_over'] = self.stepOver
        props['finish_passes'] = self.finishPasses
        props['stock_to_leave'] = self.stockToLeave
        props['hfeed'] = obj.ToolController.HorizFeed.Value
        props['vfeed'] = obj.ToolController.VertFeed.Value
        props['clearance'] = parentJob.SetupSheet.SafeHeightOffset.Value
        return props

    def get_stock_silhoutte(self, obj):
        '''
        Get Stock Silhoutte
        '''
        stock_plane_length = obj.StartDepth.Value - obj.FinalDepth.Value
        stock_plane_width = (obj.MaxDiameter.Value - obj.MinDiameter.Value) / 2
        stock_plane = Part.makePlane(stock_plane_length, stock_plane_width,
                                     FreeCAD.Vector(obj.MinDiameter.Value / 2, 0, obj.FinalDepth.Value),
                                     FreeCAD.Vector(0, 1, 0))
        return stock_plane

    def get_part_outline(self):
        '''
        Get Part Outline
        '''
        # TODO: Revisit the edge extraction and find a more elegant method
        model = self.model[0].Shape
        # get a section through the part origin on the XZ Plane
        sections = Path.Area().add(model).makeSections(mode=0, heights=[0.0], project=True, plane=self.stock_silhoutte)
        if not sections:
            raise ValueError("Turning model has no XZ section")
        part_silhoutte = sections[0].setParams(Offset=0.0).getShape()
        # get an offset section larger than the part section
        part_bound_face = sections[0].setParams(Offset=0.1).getShape()

        # ensure the cutplane is larger than the part or segments will be missed
        modelBB = model.BoundBox
        plane_length = modelBB.ZLength * 1.5
        plane_width = (modelBB.XLength / 2) * 1.5
        z_ref = modelBB.ZMax + (plane_length - modelBB.ZLength) / 2

        # create a plane larger than the part
        cut_plane = Part.makePlane(plane_length, plane_width, FreeCAD.Vector(0, 0, z_ref), FreeCAD.Vector(0, -1, 0))
        # Cut the part section from the cut plane
        path_area = cut_plane.cut(part_silhoutte)

        part_edges = []
        for edge in path_area.Edges:
            if all(part_bound_face.isInside(vertex.Point, 0.1, True) for vertex in edge.Vertexes):
                part_edges.append(edge)
        if not part_edges:
            raise ValueError("Turning model has no usable profile edges")
        segments = self.getSegmentsFromEdges(Part.Wire(part_edges).OrderedEdges)
        if not segments:
            raise ValueError("Turning model has no profile away from the spindle axis")
        if segments[0].start.Z < segments[-1].end.Z:
            segments = [Segment(seg.end, seg.start, -seg.bulge) for seg in reversed(segments)]
        return segments

    def getToolShape(self, obj):
        toolShape = obj.ToolController.Tool.Shape
        box = toolShape.BoundBox
        if box.XLength <= 0 or box.ZLength <= 0:
            raise ValueError("Turning tool must have a non-zero XZ section")
        plane = Part.makePlane(
            box.ZLength, box.XLength,
            FreeCAD.Vector(box.XMin, box.Center.y, box.ZMin), FreeCAD.Vector(0, -1, 0))
        sections = Path.Area().add(toolShape).makeSections(
            mode=0, heights=[0.0], project=True, plane=plane)
        if not sections:
            raise ValueError("Turning tool has no XZ section")
        section = sections[0].setParams(Offset=0.0).getShape()
        if len(section.Wires) != 1 or not section.Wires[0].isClosed():
            raise ValueError("Turning tool must have one closed XZ insert profile")
        return self.getSegmentsFromEdges(section.Wires[0].OrderedEdges, True)

    def getSegmentsFromEdges(self, edges, allowOnXAxis=False):
        segments = []
        for edge in edges:
            curve = edge.Curve
            if not isinstance(curve, (Part.Line, Part.Circle)):
                raise ValueError("Turning profiles support only straight lines and circular arcs")
            first, last = edge.FirstParameter, edge.LastParameter
            if edge.Orientation == "Reversed":
                first, last = last, first
            start, end = edge.valueAt(first), edge.valueAt(last)
            if (not allowOnXAxis and isinstance(curve, Part.Line)
                    and math.isclose(start.x, 0, abs_tol=1e-7)
                    and math.isclose(end.x, 0, abs_tol=1e-7)):
                continue
            parameters = [first, last]
            if isinstance(curve, Part.Circle) and edge.isClosed():
                parameters.insert(1, (first + last) / 2)
            for begin, finish in zip(parameters, parameters[1:]):
                start, end = edge.valueAt(begin), edge.valueAt(finish)
                segment = Segment(Point(start.x, start.z), Point(end.x, end.z))
                if isinstance(curve, Part.Circle):
                    middle = edge.valueAt((begin + finish) / 2)
                    cross = ((middle.x - start.x) * (end.z - start.z)
                             - (middle.z - start.z) * (end.x - start.x))
                    # LibLathe's positive bulge is clockwise in XZ.
                    segment.setBulge(-math.copysign(abs(finish - begin), cross))
                segments.append(segment)
        return segments

    def generate_gcode(self, obj):
        '''
        Base function to generate gcode for the OP by writing path command to self.commandlist
        Calls operations op_generate_gcode.
        '''
        turnTool = Tool()
        turnTool.set_tool_from_segments(self.getToolShape(obj))
        self.op_generate_gcode(obj, turnTool)

    def op_generate_gcode(self, obj, turnTool):
        '''op_generate_gcode(obj) ... overwrite to set initial default values.
        Called after the receiver has been fully created with all properties.
        Should be overwritten by subclasses.'''
        pass  # pylint: disable=unnecessary-pass
