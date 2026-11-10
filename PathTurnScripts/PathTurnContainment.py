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

    def close(self):
        if self.root is not None:
            self.root.removeChild(self.node)
            self.root = None

    def update(self, obj):
        self.clear()
        values = (obj.MinDiameter.Value, obj.MaxDiameter.Value,
                  obj.FinalDepth.Value, obj.StartDepth.Value)
        if (not all(math.isfinite(value) for value in values)
                or values[0] < 0 or values[0] >= values[1] or values[2] >= values[3]):
            raise ValueError(FreeCAD.Qt.translate(
                "PathTurn", "Containment requires 0 <= minimum diameter < maximum diameter "
                "and final depth < start depth."))

        bounds = getContainment(obj)
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
        corners = [(x0, 0, z0), (x1, 0, z0), (x1, 0, z1), (x0, 0, z1)]
        fill = coin.SoSeparator()
        material = coin.SoMaterial()
        material.diffuseColor = (1.0, 0.45, 0.1)
        material.transparency = 0.88
        fill.addChild(material)
        coordinates = coin.SoCoordinate3()
        coordinates.point.setValues(corners)
        fill.addChild(coordinates)
        face = coin.SoFaceSet()
        face.numVertices.setValues([4])
        fill.addChild(face)
        self.graphics.addChild(fill)

        rear = x1 <= 0
        inner, outer = (x1, x0) if rear else (x0, x1)
        sign = -1 if rear else 1
        self._boundary(
            [(outer, 0, z0), (outer, 0, z1)], (1.0, 0.3, 0.1))
        self._boundary(
            [(inner, 0, z0), (inner, 0, z1)], (0.1, 0.45, 1.0))
        self._boundary(
            [(x0, 0, z1), (x1, 0, z1)], (0.1, 0.7, 0.25))
        self._boundary(
            [(x0, 0, z0), (x1, 0, z0)], (0.8, 0.55, 0.05))
        clearance_x = outer + sign * clearance
        self._boundary(
            [(outer, 0, z0), (clearance_x, 0, z0),
             (clearance_x, 0, z1), (outer, 0, z1)], (0.65, 0.15, 0.85),
            dashed=True)

    def _boundary(self, points, color, dashed=False):
        group = coin.SoSeparator()
        material = coin.SoMaterial()
        material.diffuseColor = color
        group.addChild(material)
        style = coin.SoDrawStyle()
        style.lineWidth = 3
        if dashed:
            style.linePattern = 0xF0F0
        group.addChild(style)
        coordinates = coin.SoCoordinate3()
        coordinates.point.setValues(points)
        group.addChild(coordinates)
        line = coin.SoLineSet()
        line.numVertices.setValues([len(points)])
        group.addChild(line)
        self.graphics.addChild(group)
