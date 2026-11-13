"""Advisory 2D stock calculated only from already-generated turning paths."""

import math

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
        self.before = None
        self.after = None
        self.complete = False
        self.omitted_operations = ()

    def calculate(self, obj, *, include_current=True):
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
        stock = helpers.getPartOutline((job.Stock.Shape,))
        # A convex stock is validated in C++; no rectangular-envelope substitution.
        vertices = insert_polygon(stock)
        start, end = stock[0].start, stock[-1].end
        if not end.isSame(start):
            vertices.extend(((end.X, end.Z), (0, end.Z), (0, start.Z)))
        records = []
        complete = False
        for operation in operations[:operations.index(obj) + 1]:
            if operation == obj and not include_current:
                break
            if not getattr(operation, "Active", True):
                if operation == obj:
                    complete = False
                continue
            if not isinstance(getattr(operation, "Proxy", None), ObjectOp):
                raise ValueError("Stock guide cannot model preceding non-turning operations")
            if not getattr(operation.Proxy, "supports_stock_guide", True):
                raise ValueError("Stock guide does not support this operation")
            if "Touched" in operation.State:
                raise ValueError("Stock guide is stale; apply/recompute the operations first")
            commands = list(operation.Path.Commands)
            if not commands:
                if operation != obj:
                    raise ValueError("Stock guide requires a valid path for every preceding operation")
                break
            if getattr(operation.Proxy, "stock_guide_skip_feeds", False):
                records.append((operation.Name, None, ()))
                if operation == obj:
                    complete = True
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
            if operation == obj:
                complete = True
        omitted_operations = tuple(name for name, tool, moves in records if tool is None)
        key = (tuple(vertices), tuple((name, None if tool is None else tuple(tool), tuple(moves))
                                     for name, tool, moves in records), complete)
        if key == self.key:
            return self.before, self.after, self.complete
        state = StockPreview(vertices)
        before = state.copy()
        for name, tool, moves in records:
            if name == obj.Name:
                before = state.copy()
            if tool is None:
                continue
            state.remove_feeds(tool, moves)
        if not complete:
            before = state.copy()
        after = state
        for snapshot in (before, after):
            edges = snapshot.edges()
            area = math.fsum((x0 * z1 - x1 * z0) / 2 for x0, z0, x1, z1 in edges)
            if not math.isclose(area, snapshot.area, rel_tol=1e-7, abs_tol=1e-7):
                raise ValueError("Stock guide boundary is numerically unresolved")
        self.key, self.before, self.after, self.complete = key, before, after, complete
        self.omitted_operations = omitted_operations
        return before, after, complete
