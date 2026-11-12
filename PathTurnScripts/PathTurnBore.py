"""Internal finishing of model bores selected by containment."""

import FreeCAD
import Part
import Path
from PathScripts import PathUtils

from . import PathTurnAddonHelpers as helpers
from . import PathTurnBase


def _boreSections(shape):
    box = shape.BoundBox
    radius = max(abs(box.XMin), abs(box.XMax), abs(box.YMin), abs(box.YMax)) + 1
    plane = Part.makePlane(
        box.ZLength + 2, radius, FreeCAD.Vector(0, 0, box.ZMin - 1), FreeCAD.Vector(0, 1, 0))
    walls, floors = [], []
    for face in shape.Faces:
        surface = face.Surface
        planar = isinstance(surface, Part.Plane)
        if not isinstance(surface, (Part.Plane, Part.Cylinder, Part.Cone, Part.Toroid)):
            continue
        if abs(abs(surface.Axis.z) - 1) > 1e-7:
            continue
        if not planar and (abs(surface.Center.x) > 1e-7 or abs(surface.Center.y) > 1e-7):
            continue
        for edge in face.section(plane).Edges:
            middle = edge.valueAt((edge.FirstParameter + edge.LastParameter) / 2)
            u, v = surface.parameter(middle)
            normal = face.normalAt(u, v)
            if planar and normal.z > 0:
                floors.append(edge)
            elif not planar and normal.x < -1e-7:
                walls.append(edge)
    # Attach only inward floors/steps at the bottom of an inner wall, never
    # the outward-facing annulus at its mouth.
    edges = list(walls)
    for floor in floors:
        endpoints = [vertex.Point for vertex in floor.Vertexes]
        if len(endpoints) != 2:
            continue
        outer = max(endpoints, key=lambda point: point.x)
        if any(outer.distanceToPoint(vertex.Point) < 1e-7
               and abs(vertex.Point.z - wall.BoundBox.ZMin) < 1e-7
               for wall in walls for vertex in wall.Vertexes):
            edges.append(floor)
    return edges


def getBoreOutline(obj, models=None):
    if models is None:
        job = PathUtils.findParentJob(obj)
        if job is None:
            raise ValueError(FreeCAD.Qt.translate("PathTurn", "Boring requires a parent CAM job."))
        models = job.Model.Group
    bounds = helpers.getContainment(obj)
    inner, outer = sorted((abs(bounds.XMin), abs(bounds.XMax)))
    window = Part.Face(Part.makePolygon([
        FreeCAD.Vector(inner, 0, bounds.ZMin), FreeCAD.Vector(outer, 0, bounds.ZMin),
        FreeCAD.Vector(outer, 0, bounds.ZMax), FreeCAD.Vector(inner, 0, bounds.ZMax),
        FreeCAD.Vector(inner, 0, bounds.ZMin)]))
    contours = []
    for model in models:
        shape = model.Shape
        if shape.isNull() or not shape.Solids or not shape.isValid():
            raise ValueError(FreeCAD.Qt.translate("PathTurn", "Boring requires valid solid job models."))
        for group in Part.sortEdges(_boreSections(shape), 1e-7):
            if not any(edge.common(window).Length > 1e-7 for edge in group):
                continue
            wire = Part.Wire(group)
            if wire.isClosed():
                raise ValueError(FreeCAD.Qt.translate(
                    "PathTurn", "The contained bore must have an open contour from its mouth to its bottom."))
            segments = helpers.getSegmentsFromEdges(wire.OrderedEdges, True)
            if segments[0].start.Z < segments[-1].end.Z:
                from liblathe.base.segment import Segment

                segments = [Segment(edge.end, edge.start, -edge.bulge) for edge in reversed(segments)]
            contours.append(segments)
    if len(contours) != 1:
        raise ValueError(FreeCAD.Qt.translate(
            "PathTurn", "Containment must select exactly one connected coaxial bore; "
            "found {count}. Adjust the X/Z limits. Supported walls are cylinders, cones "
            "and tori, with flat floors.").format(count=len(contours)))
    return contours[0]


class ObjectTurnBore(PathTurnBase.ObjectOp):
    internal_finishing = True

    def initOperation(self, obj):
        super().initOperation(obj)
        self._addCutDirection(obj)

    def opOnDocumentRestored(self, obj):
        super().opOnDocumentRestored(obj)
        self._addCutDirection(obj)

    @staticmethod
    def _addCutDirection(obj):
        direction = "Radial"
        created = not hasattr(obj, "CutDirection")
        if created:
            obj.addProperty("App::PropertyEnumeration", "CutDirection", "Turn Path",
                            FreeCAD.Qt.translate("TurnPath", "Internal clearing feed direction"))
        else:
            current = str(obj.CutDirection)
            directions = {"X": "Radial", "Z": "Axial", "Radial": "Radial", "Axial": "Axial"}
            if current not in directions:
                raise ValueError(f"Unsupported boring cut direction: {current}")
            direction = directions[current]
        if created or obj.getEnumerationsOfProperty("CutDirection") != ["Radial", "Axial"]:
            obj.CutDirection = ["Radial", "Axial"]
            obj.CutDirection = direction

    def getProps(self, obj):
        from liblathe.op.base import CutDirection

        return {**super().getProps(obj), "cut_direction": CutDirection[str(obj.CutDirection).upper()]}

    def setEditorModes(self, obj, features):
        super().setEditorModes(obj, features)
        for name in ("AllowGrooving", "Base"):
            if hasattr(obj, name):
                obj.setEditorMode(name, 2)

    def get_part_outline(self, obj):
        return getBoreOutline(obj, self.model)

    def op_generate_gcode(self, obj, turnTool):
        try:
            from liblathe.op.bore import BoreOP
        except ModuleNotFoundError as error:
            if error.name != "liblathe.op.bore":
                raise
            raise RuntimeError(FreeCAD.Qt.translate(
                "PathTurn", "Turn Bore requires a LibLathe build containing the experimental BoreOP. "
                "Install it into FreeCAD's Python environment, then restart FreeCAD.")) from error
        operation = BoreOP()
        operation.setParams(self.getProps(obj))
        operation.add_containment(helpers.getContainment(obj))
        operation.addPartSegments(self.part_outline)
        operation.add_tool(turnTool)
        commands = operation.getGCode()
        if not operation.tool_paths and not operation.clearing_paths:
            raise RuntimeError(FreeCAD.Qt.translate(
                "PathTurn", "No boring cutting path was generated. Check containment, "
                "insert orientation and allowances."))
        self.commandlist.extend(
            Path.Command(command.get_movement(), command.getParams()) for command in commands)


def SetupProperties():
    return ["PassOffset", "FinishPasses", "CutDirection"]


def Create(name, obj=None, parentJob=None):
    if obj is None:
        obj = FreeCAD.ActiveDocument.addObject("Path::FeaturePython", name)
    obj.Proxy = ObjectTurnBore(obj, name, parentJob)
    return obj
