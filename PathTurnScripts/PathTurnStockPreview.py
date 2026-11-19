"""Advisory 2D stock calculated only from already-generated turning paths."""

import math

import FreeCAD

from liblathe.base.segmentgroup import StockPreview

from . import PathTurnAddonHelpers as helpers
from .PathTurnToolBit import post_from_parameters


def insert_polygon(segments, tolerance=0.005):
    points = []
    for edge in segments:
        if not edge.bulge:
            points.append((edge.start.X, edge.start.Z))
            continue
        centre = edge.getCentrePoint()
        radius = edge.getRadius()
        angle = math.atan2(edge.start.Z - centre.Z, edge.start.X - centre.X)
        sweep = -4 * math.atan(edge.bulge)
        step = 2 * math.acos(max(-1, 1 - tolerance / radius))
        count = max(1, math.ceil(abs(sweep) / step))
        for i in range(count):
            a = angle + sweep * i / count
            points.append((centre.X + radius * math.cos(a), centre.Z + radius * math.sin(a)))
    return points


def stock_polygon(stock):
    if getattr(stock, "StockType", None) == "CreateCylinder" and stock.Axis == "Z":
        axis = stock.Placement.Rotation.multVec(FreeCAD.Vector(0, 0, 1))
        if abs(axis.x) < 1e-12 and abs(axis.y) < 1e-12:
            origin = stock.Placement.Base
            radius = stock.Radius.Value + math.hypot(origin.x, origin.y)
            end_z = origin.z + axis.z * stock.Height.Value
            zmin, zmax = sorted((origin.z, end_z))
            return [(0, zmin), (radius, zmin), (radius, zmax), (0, zmax)]

    outline = helpers.getPartOutline((stock.Shape,))
    vertices = insert_polygon(outline)
    start, end = outline[0].start, outline[-1].end
    if not end.isSame(start):
        vertices.extend(((end.X, end.Z), (0, end.Z), (0, start.Z)))
    return vertices


def feeds(commands, sign):
    previous = None
    result = []
    for command in commands:
        name, params = command.Name, command.Parameters
        if name in ("G18", "G21", "G90", "G94"):
            continue
        if name in ("G17", "G19", "G20", "G91", "G92", "G92.1"):
            raise ValueError("Stock guide requires absolute millimetre X/Z coordinates")
        if not any(axis in params for axis in ("X", "Y", "Z", "I", "J", "K")):
            continue
        if name not in ("G0", "G00", "G1", "G01") or params.get("Y", 0):
            raise ValueError("Stock guide supports straight X/Z turning moves only")
        if previous is None and not all(axis in params for axis in ("X", "Z")):
            raise ValueError("Stock guide requires a known starting X/Z position")
        current = (sign * params.get("X", previous[0] / sign if previous else 0),
                   params.get("Z", previous[1] if previous else 0))
        if previous is not None and name in ("G1", "G01"):
            result.append((*previous, *current))
        previous = current
    return result


class StockGuide:
    def __init__(self):
        self.key = None
        self.stock = None
        self.complete = False
        self.omitted_operations = ()

    def calculate(self, obj, *, path_current=True):
        """Return the stock after obj when its path is current, otherwise the stock before it.

        The caller decides whether obj's path is current: opening the task panel
        reassigns obj's expression-bound properties, touching it with a valid path.
        """
        from .PathTurnBase import ObjectOp
        from PathScripts import PathUtils

        job = PathUtils.findParentJob(obj)
        if job is None:
            raise ValueError("Stock guide requires a parent CAM job")
        operations = list(job.Operations.Group)
        if obj not in operations:
            raise ValueError("Stock guide cannot resolve operation order")
        if "Touched" in job.Stock.State:
            raise ValueError("Stock guide is stale; recompute the stock first")
        vertices = stock_polygon(job.Stock)
        records = []
        complete = False
        for operation in operations[:operations.index(obj) + 1]:
            current = operation == obj
            if not getattr(operation, "Active", True):
                continue
            if not isinstance(getattr(operation, "Proxy", None), ObjectOp):
                raise ValueError("Stock guide cannot model preceding non-turning operations")
            if not getattr(operation.Proxy, "supports_stock_guide", True):
                raise ValueError("Stock guide does not support this operation")
            commands = list(operation.Path.Commands)
            if current and not (path_current and commands):
                break
            if not current and "Touched" in operation.State:
                raise ValueError("Stock guide is stale; apply/recompute the operations first")
            if not commands:
                raise ValueError("Stock guide requires a valid path for every preceding operation")
            if getattr(operation.Proxy, "stock_guide_skip_feeds", False):
                records.append((operation.Name, None, ()))
                complete = current
                continue
            tool = operation.ToolController.Tool
            if "Touched" in tool.State or "Touched" in operation.ToolController.State:
                raise ValueError("Stock guide is stale; recompute the tool and operations first")
            if getattr(operation.Proxy, "centreline_drilling", False):
                from .PathTurnDrill import getDrill

                sign = 1
                polygon = insert_polygon(getDrill(tool).get_segmentgroup().getSegments())
            else:
                sign = -1 if post_from_parameters({"ToolPost": tool.ToolPost}) == "Rear" else 1
                polygon = insert_polygon(helpers.getToolSegments(tool.Shape))
                polygon = [(sign * x, z) for x, z in polygon]
            moves = feeds(commands, sign)
            if not moves:
                raise ValueError("Stock guide found no generated cutting feeds")
            records.append((operation.Name, polygon, moves))
            complete = current
        omitted_operations = tuple(name for name, tool, moves in records if tool is None)
        key = (tuple(vertices), tuple((name, None if tool is None else tuple(tool), tuple(moves))
                                     for name, tool, moves in records), complete)
        if key == self.key:
            return self.stock, self.complete
        try:
            stock = StockPreview(vertices)
        except ValueError as error:
            raise ValueError(f"Invalid stock outline: {error}") from error
        for name, tool, moves in records:
            if tool is not None:
                try:
                    stock.remove_feeds(tool, moves)
                except ValueError as error:
                    raise ValueError(f"Invalid tool or cutting moves for {name}: {error}") from error
        area = math.fsum((x0 * z1 - x1 * z0) / 2 for x0, z0, x1, z1 in stock.edges())
        if not math.isclose(area, stock.area, rel_tol=1e-7, abs_tol=1e-7):
            raise ValueError("Stock guide boundary is numerically unresolved")
        self.key, self.stock, self.complete = key, stock, complete
        self.omitted_operations = omitted_operations
        return stock, complete
