"""Standalone dexel material-removal library.

Standard library only: nothing in this package imports FreeCAD, so it can be
used, tested and distributed independently of the FreeCAD add-in.

Typical use::

    from dexel import DexelGrid, RevolvedTool

    grid = DexelGrid((0, 0, 0, 100, 100, 20), resolution=0.25)
    tool = RevolvedTool.flat(radius=3.0, length=30.0)
    grid.cut_segment(tool, 1, (10, 10, 12), (40, 10, 12))
    triangles, tool_ids = grid.extract()

For round stock parallel to Z, use ``DexelGrid.cylinder(radius, height,
resolution, origin=(cx, cy, zmin))``. The cylinder wall follows the grid spacing.

``TurningTool(profile)`` accepts one convex insert outline as local XZ points.
``grid.cut_turning(tool, operation_id, (x0, z0), (x1, z1))`` removes its straight
sweep revolved about the spindle. This models continuous stock rotation, not
individual spindle revolutions or threading.
"""

from .grid import DexelGrid
from .tools import RevolvedTool, TurningTool

__all__ = ["DexelGrid", "RevolvedTool", "TurningTool"]
__version__ = "0.1.0"
