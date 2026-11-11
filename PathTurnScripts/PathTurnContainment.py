"""Temporary, non-selectable turning containment graphics."""

import math

import FreeCAD
from pivy import coin
from PathScripts import PathUtils

from .PathTurnAddonHelpers import getContainment


class ContainmentPreview:
    def __init__(self, root):
        self.root = root
        self.node = coin.SoSeparator()
        pick = coin.SoPickStyle()
        pick.style = coin.SoPickStyle.UNPICKABLE
        self.node.addChild(pick)
        # Keep the limits readable through the model without changing its display.
        depth = coin.SoDepthBuffer()
        depth.test = False
        depth.getField("write").setValue(False)
        self.node.addChild(depth)
        light = coin.SoLightModel()
        light.model = coin.SoLightModel.BASE_COLOR
        self.node.addChild(light)
        self.graphics = coin.SoSeparator()
        self.node.addChild(self.graphics)
        self.root.addChild(self.node)

    def clear(self):
        self.graphics.removeAllChildren()

    def show_stock(self, edges, rear=False, *, polygons=()):
        sign = -1 if rear else 1
        fill = coin.SoSeparator()
        material = coin.SoMaterial()
        material.diffuseColor = (0.95, 0.6, 0.12)
        material.transparency = 0.65
        fill.addChild(material)
        hints = coin.SoShapeHints()
        hints.vertexOrdering = coin.SoShapeHints.UNKNOWN_ORDERING
        hints.shapeType = coin.SoShapeHints.UNKNOWN_SHAPE_TYPE
        hints.faceType = coin.SoShapeHints.CONVEX
        fill.addChild(hints)
        coordinates = coin.SoCoordinate3()
        coordinates.point.setValues([
            (sign * x, 0, z) for polygon in polygons for x, z in polygon])
        fill.addChild(coordinates)
        faces = coin.SoFaceSet()
        faces.numVertices.setValues([len(polygon) for polygon in polygons])
        fill.addChild(faces)
        # Draw the fill first so the limit and stock outlines remain legible.
        self.graphics.insertChild(fill, 0)
        group = coin.SoSeparator()
        material = coin.SoMaterial()
        material.diffuseColor = (0.95, 0.6, 0.12)
        group.addChild(material)
        style = coin.SoDrawStyle()
        style.lineWidth = 2
        group.addChild(style)
        coordinates = coin.SoCoordinate3()
        coordinates.point.setValues([
            (sign * x, 0, z) for edge in edges
            for x, z in ((edge[0], edge[1]), (edge[2], edge[3]))])
        group.addChild(coordinates)
        lines = coin.SoLineSet()
        lines.numVertices.setValues([2] * len(edges))
        group.addChild(lines)
        self.graphics.insertChild(group, 1)

    def close(self):
        if self.root is not None:
            self.root.removeChild(self.node)
            self.root = None

    def update(self, obj):
        self.clear()
        bounds = getContainment(obj)
        values = (bounds.XMin, bounds.XMax, bounds.ZMin, bounds.ZMax)
        if (not all(math.isfinite(value) for value in values)
                or values[0] >= values[1] or values[2] >= values[3]
                or (not getattr(obj.Proxy, "centreline_drilling", False)
                    and obj.MinDiameter.Value < 0)):
            raise ValueError(FreeCAD.Qt.translate(
                "PathTurn", "Containment requires 0 <= minimum diameter < maximum diameter "
                "and final depth < start depth."))

        job = PathUtils.findParentJob(obj)
        if job is None:
            raise ValueError(FreeCAD.Qt.translate(
                "PathTurn", "Containment clearance requires a parent CAM job."))
        offset = job.SetupSheet.SafeHeightOffset
        if not math.isfinite(offset.Value) or offset.Value < 0:
            raise ValueError(FreeCAD.Qt.translate(
                "PathTurn", "Clearance must be finite and non-negative."))
        clearance = max(offset.Value, 0.01)
        x0, x1 = bounds.XMin, bounds.XMax
        z0, z1 = bounds.ZMin, bounds.ZMax
        rear = x1 <= 0
        inner, outer = (x1, x0) if rear else (x0, x1)
        sign = -1 if rear else 1
        magenta = (0.55, 0.05, 0.45)
        self._boundary(
            [(outer, 0, z0), (outer, 0, z1)], magenta)
        self._boundary(
            [(inner, 0, z0), (inner, 0, z1)], magenta)
        self._boundary(
            [(x0, 0, z1), (x1, 0, z1)], magenta)
        self._boundary(
            [(x0, 0, z0), (x1, 0, z0)], magenta)
        if getattr(obj.Proxy, "centreline_drilling", False):
            self._boundary(
                [(x0, 0, z1 + clearance), (x1, 0, z1 + clearance)], magenta,
                dashed=True)
        elif not getattr(obj.Proxy, "internal_finishing", False):
            clearance_x = outer + sign * clearance
            self._boundary(
                [(clearance_x, 0, z0), (clearance_x, 0, z1)], magenta,
                dashed=True)

    def _boundary(self, points, color, dashed=False):
        group = coin.SoSeparator()
        coordinates = coin.SoCoordinate3()
        coordinates.point.setValues(points)
        line = coin.SoLineSet()
        line.numVertices.setValues([len(points)])
        halo = coin.SoSeparator()
        white = coin.SoMaterial()
        white.diffuseColor = (1, 1, 1)
        halo.addChild(white)
        halo_style = coin.SoDrawStyle()
        halo_style.lineWidth = 6 if dashed else 7
        if dashed:
            halo_style.linePattern = 0xF0F0
        halo.addChild(halo_style)
        halo.addChild(coordinates)
        halo.addChild(line)
        group.addChild(halo)
        material = coin.SoMaterial()
        material.diffuseColor = color
        group.addChild(material)
        style = coin.SoDrawStyle()
        style.lineWidth = 2 if dashed else 3
        if dashed:
            style.linePattern = 0xF0F0
        group.addChild(style)
        group.addChild(coordinates)
        group.addChild(line)
        self.graphics.addChild(group)
