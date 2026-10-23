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
import os
from collections import OrderedDict

import FreeCAD
import MeshPart
import Part
import Path

from liblathe.base.boundbox import BoundBox
from liblathe.base.point import Point
from liblathe.base.segment import Segment


_rotational_profiles = OrderedDict()


def getResourcePath(resName):
    """Return the path to a named panel resource in the add-on."""
    # get this directory
    pathScripts = os.path.dirname(__file__)
    # get the parent directory
    __dir__ = os.path.dirname(pathScripts)
    # get the resourse directory
    resourcePath = os.path.join(__dir__, 'Gui/Resources/panels')
    res = os.path.join(resourcePath, resName)

    return res


def getliblatheBoundBox(operation):
    """Convert operation diameter and depth limits to a LibLathe XZ bound box.

    Diameter limits become radii; final and start depths bound the Z range.
    """
    return BoundBox(
        Point(operation.MinDiameter.Value / 2, operation.FinalDepth.Value),
        Point(operation.MaxDiameter.Value / 2, operation.StartDepth.Value))


def getPartOutline(models):
    """Return a connected, top-to-bottom LibLathe outline for model shapes.

    Reuse the four most recent verified profiles across operations, excluding
    straight spindle-axis edges from the returned outline. Reject empty models
    and profiles that cannot form one connected cutting contour.
    """
    models = tuple(models)
    if not models:
        raise ValueError("Turning requires a solid model")
    hashes = tuple(shape.hashCode() for shape in models)
    cached = _rotational_profiles.get(hashes)
    if (cached is not None and hashes == cached[0]
            and all(shape.isSame(old) for shape, old in zip(models, cached[1]))):
        profile = cached[2]
    else:
        model = models[0] if len(models) == 1 else Part.makeCompound(models)
        profile = getRotationalProfile(model)
        cached = (hashes, models, profile)
        _rotational_profiles[hashes] = cached
    _rotational_profiles.move_to_end(hashes)
    if len(_rotational_profiles) > 4:
        _rotational_profiles.popitem(last=False)

    edges = [
        edge.copy() for edge in profile.OuterWire.Edges
        if not (isinstance(edge.Curve, Part.Line)
                and all(abs(vertex.Point.x) <= 1e-7 for vertex in edge.Vertexes))
    ]
    wires = Part.sortEdges(edges, 1e-9)
    if len(wires) != 1:
        raise ValueError("Turning model must have one connected outer profile")
    segments = getSegmentsFromEdges(Part.Wire(wires[0]).OrderedEdges)
    if not segments:
        raise ValueError("Turning model has no profile away from the spindle axis")
    if segments[0].start.Z < segments[-1].end.Z:
        segments = [Segment(seg.end, seg.start, -seg.bulge) for seg in reversed(segments)]
    return segments


def getRotationalProfile(model, tolerance=0.01):
    """Return a verified positive-X face enclosing the model's rotation about Z.

    Prefer an exact line/arc section; otherwise build a conservative radial mesh
    envelope using the approximation allowance given by tolerance in millimetres.
    Raise an error if the model is invalid or containment cannot be established.
    """
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
    profile = getSectionProfile(model.common(plane))
    if profile is not None and profileContainsModel(profile, model):
        return profile

    # Radial projection sees every mesh face, including features hidden in any one view.
    for deflection in (tolerance / 8, tolerance / 32):
        projected = getRadialMeshProjection(model, deflection)
        profile = getPositiveProfile(projected, plane)
        if profile is not None and profileContainsModel(profile, model):
            return profile
    raise RuntimeError(
        f"Cannot construct a containing turning profile within {tolerance:g} mm")


def getSectionProfile(section):
    """Fill a positive-X meridional line/arc section toward the spindle axis.

    Return one outer face, or None if the section contains unsupported curves,
    has no usable edges, or cannot form a single connected face.
    """
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


def getPositiveProfile(projected, plane):
    """Fill projected face interiors and clip them to the positive-X workplane.

    Return one outer face with a straight spindle-axis boundary, or None when
    the clipped projection does not meet those requirements.
    """
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


def profileContainsModel(profile, model):
    """Check that revolving the profile about Z contains the entire model.

    Require a valid revolved solid and a valid cut remainder with no faces,
    rather than accepting a volume tolerance that could hide small features.
    """
    if not profile.isValid():
        return False
    envelope = profile.revolve(FreeCAD.Vector(), FreeCAD.Vector(0, 0, 1), 360)
    if not envelope.isValid() or not envelope.Solids:
        return False
    remaining = model.cut(envelope)
    return remaining.isValid() and not remaining.Faces


def getRadialMeshProjection(model, deflection):
    """Build an outward-offset XZ candidate from the model's radial mesh envelope.

    Use deflection in millimetres for absolute meshing and radial interpolation
    error. Merge axial spans, simplify the outline and add a conservative margin.
    The caller must still verify containment against the complete solid model.
    """
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
            mergeRadialProfiles(spans[index], spans[index + 1])
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
    outline = simplifyRadialProfile(outline, deflection / 2)
    outline = [FreeCAD.Vector(0, 0, outline[0].z)] + outline + [
        FreeCAD.Vector(0, 0, outline[-1].z)]
    face = Part.Face(Part.makePolygon(outline + [outline[0]]))
    return Path.Area().add(face).setParams(
        FitArcs=True, Accuracy=deflection / 2, Deflection=deflection,
        CleanDistance=deflection / 2, Offset=4 * deflection, JoinType=1).getShape()


def simplifyRadialProfile(points, tolerance):
    """Simplify ordered XZ polyline points within the given distance tolerance.

    Retain the endpoints and original point order using iterative subdivision.
    Simplification alone does not guarantee an outward boundary; the caller
    must add a margin and verify the final envelope.
    """
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


def mergeRadialProfiles(first, second):
    """Return the upper envelope of two non-empty, ordered axial span lists.

    Each span is (start_z, start_radius, end_z, end_radius), with start_z < end_z.
    Spans within each input must not overlap. Split at crossings and preserve
    axial gaps and radius steps.
    """
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


def getToolSegments(toolShape):
    """Extract LibLathe segments from the tool shape's closed XZ projection.

    Project at the shape's mid-Y plane, retaining its supplied orientation.
    Require one closed outline with non-zero X and Z extents.
    """
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
    return getSegmentsFromEdges(section.Wires[0].OrderedEdges, True)


def getSegmentsFromEdges(edges, allowOnXAxis=False):
    """Convert directed FreeCAD line/circle edges to LibLathe XZ segments.

    Preserve orientation and clockwise-positive bulges, splitting full circles
    into two arcs. Omit straight spindle-axis edges unless allowOnXAxis is True.
    Raise ValueError for unsupported curve types.
    """
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
