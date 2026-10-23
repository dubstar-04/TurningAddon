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
from collections import OrderedDict

import FreeCAD
import MeshPart
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

    _rotational_profiles = OrderedDict()

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
        self.setEditorModes(obj, self.opFeatures(obj))

    def setEditorModes(self, obj, features):
        super().setEditorModes(obj, features)
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

        if not math.isfinite(obj.StepOver.Value) or obj.StepOver.Value <= 0:
            raise RuntimeError(translate('PathTurn', "Stepover must be finite and positive"))

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

    def opSetDefaultValues(self, obj, job):
        obj.OpStartDepth = job.Stock.Shape.BoundBox.ZMax
        obj.OpFinalDepth = job.Stock.Shape.BoundBox.ZMin

    def opUpdateDepths(self, obj):
        obj.OpStartDepth = obj.OpStockZMax
        obj.OpFinalDepth = obj.OpStockZMin
        self.setEditorModes(obj, self.opFeatures(obj))

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
        models = tuple(base.Shape for base in self.model)
        if not models:
            raise ValueError("Turning requires a solid model")
        hashes = tuple(shape.hashCode() for shape in models)
        cached = ObjectOp._rotational_profiles.get(hashes)
        if (cached is not None and hashes == cached[0]
                and all(shape.isSame(old) for shape, old in zip(models, cached[1]))):
            profile = cached[2]
        else:
            model = models[0] if len(models) == 1 else Part.makeCompound(models)
            profile = self.getRotationalProfile(model)
            cached = (hashes, models, profile)
            ObjectOp._rotational_profiles[hashes] = cached
        ObjectOp._rotational_profiles.move_to_end(hashes)
        if len(ObjectOp._rotational_profiles) > 4:
            ObjectOp._rotational_profiles.popitem(last=False)
        self._rotational_profile_cache = cached

        edges = [
            edge.copy() for edge in profile.OuterWire.Edges
            if not (isinstance(edge.Curve, Part.Line)
                    and all(abs(vertex.Point.x) <= 1e-7 for vertex in edge.Vertexes))
        ]
        wires = Part.sortEdges(edges, 1e-9)
        if len(wires) != 1:
            raise ValueError("Turning model must have one connected outer profile")
        segments = self.getSegmentsFromEdges(Part.Wire(wires[0]).OrderedEdges)
        if not segments:
            raise ValueError("Turning model has no profile away from the spindle axis")
        if segments[0].start.Z < segments[-1].end.Z:
            segments = [Segment(seg.end, seg.start, -seg.bulge) for seg in reversed(segments)]
        return segments

    def getRotationalProfile(self, model, tolerance=0.01):
        if not math.isfinite(tolerance) or tolerance < 1e-6:
            raise ValueError("Turning profile tolerance must be finite and at least 0.000001 mm")
        if model.isNull() or not model.Solids or not model.isValid():
            raise ValueError("Turning requires a valid solid model")
        box = model.BoundBox
        radius = math.hypot(max(abs(box.XMin), abs(box.XMax)),
                            max(abs(box.YMin), abs(box.YMax)))
        padding = max(1.0, tolerance * 2)
        plane = Part.makePlane(
            box.ZLength + 2 * padding, radius + padding,
            FreeCAD.Vector(0, 0, box.ZMin - padding), FreeCAD.Vector(0, 1, 0))
        profile = self.getSectionProfile(model.common(plane))
        if profile is not None and self.profileContainsModel(profile, model):
            return profile

        # Radial projection sees every mesh face, including features hidden in any one view.
        for deflection in (tolerance / 8, tolerance / 32):
            projected = self.getRadialMeshProjection(model, deflection)
            profile = self.getPositiveProfile(projected, plane)
            if profile is not None and self.profileContainsModel(profile, model):
                return profile
        raise RuntimeError(
            f"Cannot construct a containing turning profile within {tolerance:g} mm")

    def getSectionProfile(self, section):
        faces = []
        for edge in section.Edges:
            curve = edge.Curve
            first, last = edge.FirstParameter, edge.LastParameter
            parameters = [first, last]
            if isinstance(curve, Part.Circle):
                phase = math.atan2(curve.YAxis.z, curve.XAxis.z)
                parameters = [first] + [
                    phase + index * math.pi
                    for index in range(math.ceil((first - phase) / math.pi),
                                       math.floor((last - phase) / math.pi) + 1)
                    if first + 1e-10 < phase + index * math.pi < last - 1e-10
                ] + [last]
            elif not isinstance(curve, Part.Line):
                return None
            for begin, finish in zip(parameters, parameters[1:]):
                start, end = edge.valueAt(begin), edge.valueAt(finish)
                middle = edge.valueAt((begin + finish) / 2)
                if (abs(start.z - end.z) <= 1e-7
                        or max(start.x, middle.x, end.x) <= 1e-7):
                    continue
                boundary = [curve.toShape(begin, finish)]
                if start.z > end.z:
                    start, end = end, start
                    boundary[0].reverse()
                # Fill each monotonic section edge to the axis; union keeps only the outside.
                points = [end, FreeCAD.Vector(0, 0, end.z),
                          FreeCAD.Vector(0, 0, start.z), start]
                for point, following in zip(points, points[1:]):
                    if (following - point).Length > 1e-7:
                        boundary.append(Part.makeLine(point, following))
                faces.append(Part.Face(Part.Wire(boundary)))
        if not faces:
            return None
        profile = faces[0].multiFuse(faces[1:]).removeSplitter() if len(faces) > 1 else faces[0]
        if len(profile.Faces) != 1:
            return None
        return Part.Face(profile.Faces[0].OuterWire)

    def getPositiveProfile(self, projected, plane):
        filled = Part.makeCompound([Part.Face(face.OuterWire) for face in projected.Faces])
        if filled.isNull() or not filled.Faces:
            return None
        clipped = filled.common(plane).removeSplitter()
        if len(clipped.Faces) != 1:
            return None
        profile = Part.Face(clipped.Faces[0].OuterWire)
        if not any(isinstance(edge.Curve, Part.Line)
                   and all(abs(vertex.Point.x) <= 1e-7 for vertex in edge.Vertexes)
                   for edge in profile.Edges):
            return None
        return profile

    def profileContainsModel(self, profile, model):
        if not profile.isValid():
            return False
        envelope = profile.revolve(FreeCAD.Vector(), FreeCAD.Vector(0, 0, 1), 360)
        if not envelope.isValid() or not envelope.Solids:
            return False
        remaining = model.cut(envelope)
        return remaining.isValid() and not remaining.Faces

    def getRadialMeshProjection(self, model, deflection):
        mesh = MeshPart.meshFromShape(
            Shape=model.copy(), LinearDeflection=deflection,
            AngularDeflection=0.5, Relative=False)
        vertices, facets = mesh.Topology
        edges = {
            tuple(sorted((facet[i], facet[(i + 1) % 3])))
            for facet in facets for i in range(3)
        }
        spans = []
        for first, last in edges:
            start, end = vertices[first], vertices[last]
            if abs(start.z - end.z) <= 1e-7:
                continue
            if start.z > end.z:
                start, end = end, start
            pending = [(start, end)]
            while pending:
                start, end = pending.pop()
                first_radius = math.hypot(start.x, start.y)
                last_radius = math.hypot(end.x, end.y)
                middle = (start + end) / 2
                middle_radius = math.hypot(middle.x, middle.y)
                # Twice the midpoint gap bounds the convex radial interpolation error.
                if first_radius + last_radius - 2 * middle_radius > deflection:
                    if middle == start or middle == end:
                        raise RuntimeError("Turning profile exceeds available geometry precision")
                    pending.extend(((start, middle), (middle, end)))
                    continue
                if max(first_radius, last_radius) <= 1e-7:
                    continue
                spans.append([(start.z, first_radius, end.z, last_radius)])
        if not spans:
            raise ValueError("Turning model has no usable mesh profile")
        while len(spans) > 1:
            spans = [
                self.mergeRadialProfiles(spans[index], spans[index + 1])
                if index + 1 < len(spans) else spans[index]
                for index in range(0, len(spans), 2)
            ]
        outline = []
        for first_z, first_radius, last_z, last_radius in spans[0]:
            if outline and abs(outline[-1].z - first_z) > 1e-7:
                raise ValueError("Turning model must have a connected axial profile")
            for z, radius in ((first_z, first_radius), (last_z, last_radius)):
                point = FreeCAD.Vector(radius, 0, z)
                if not outline or (point - outline[-1]).Length > 1e-7:
                    outline.append(point)
        outline = self.simplifyRadialProfile(outline, deflection / 2)
        outline = [FreeCAD.Vector(0, 0, outline[0].z)] + outline + [
            FreeCAD.Vector(0, 0, outline[-1].z)]
        face = Part.Face(Part.makePolygon(outline + [outline[0]]))
        return Path.Area().add(face).setParams(
            FitArcs=True, Accuracy=deflection / 2, Deflection=deflection,
            CleanDistance=deflection / 2, Offset=4 * deflection, JoinType=1).getShape()

    def simplifyRadialProfile(self, points, tolerance):
        keep = {0, len(points) - 1}
        pending = [(0, len(points) - 1)]
        while pending:
            first, last = pending.pop()
            start, end = points[first], points[last]
            dx, dz = end.x - start.x, end.z - start.z
            length_squared = dx * dx + dz * dz
            greatest = tolerance * tolerance
            furthest = None
            for index in range(first + 1, last):
                x, z = points[index].x - start.x, points[index].z - start.z
                fraction = (max(0, min(1, (x * dx + z * dz) / length_squared))
                            if length_squared else 0)
                distance_squared = (x - fraction * dx) ** 2 + (z - fraction * dz) ** 2
                if distance_squared > greatest:
                    greatest, furthest = distance_squared, index
            if furthest is not None:
                keep.add(furthest)
                pending.extend(((first, furthest), (furthest, last)))
        return [points[index] for index in sorted(keep)]

    def mergeRadialProfiles(self, first, second):
        merged = []
        i = j = 0
        z = min(first[0][0], second[0][0])
        while i < len(first) or j < len(second):
            while i < len(first) and first[i][2] <= z:
                i += 1
            while j < len(second) and second[j][2] <= z:
                j += 1
            active = []
            boundaries = []
            for spans, index in ((first, i), (second, j)):
                if index < len(spans):
                    start, start_radius, end, end_radius = spans[index]
                    if start <= z:
                        boundaries.append(end)
                        active.append((start, start_radius, end, end_radius))
                    else:
                        boundaries.append(start)
            if not boundaries:
                break
            end = min(boundaries)
            values = []
            for start, start_radius, finish, finish_radius in active:
                slope = (finish_radius - start_radius) / (finish - start)
                values.append((start_radius + slope * (z - start),
                               start_radius + slope * (end - start)))
            if len(values) == 2:
                left = values[0][0] - values[1][0]
                right = values[0][1] - values[1][1]
                if (left < 0 < right) or (right < 0 < left):
                    fraction = left / (left - right)
                    crossing = z + fraction * (end - z)
                    radius = values[0][0] + fraction * (values[0][1] - values[0][0])
                    merged.append((z, max(value[0] for value in values), crossing, radius))
                    merged.append((crossing, radius, end, max(value[1] for value in values)))
                else:
                    merged.append((z, max(value[0] for value in values),
                                   end, max(value[1] for value in values)))
            elif values:
                merged.append((z, values[0][0], end, values[0][1]))
            z = end
        return merged

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
