"""Z-direction dexel grid: material stored as intervals along vertical rays.

Each (x, y) column holds ordered ``[lo, hi]`` material intervals. The common
case, a single interval, lives in flat typed arrays. Columns with several
intervals (for example after a tool passes through the middle of the material)
are kept in a sparse dictionary. Every interval end remembers the id of the
operation that created it. Removed Z ranges retain their operation ids so
side walls keep their original colours when a later cut changes the column.

Limitations of this first version: only Z rays, so vertical walls are as
accurate as the grid spacing.
"""

import math
from array import array
from bisect import bisect_left, bisect_right


class DexelGrid:
    def __init__(self, bounds, resolution, max_columns=2000000, tolerance=1e-4):
        """Create a solid block.

        ``bounds`` is ``(xmin, ymin, zmin, xmax, ymax, zmax)``. ``resolution`` is
        the largest allowed column size in X and Y; the actual sizes are chosen
        so the grid exactly spans the bounds. Heights closer than ``tolerance``
        are treated as equal: cuts that only skim a surface change nothing, no
        material thinner than the tolerance is kept, and no wall shorter than it
        is generated. This keeps floating-point noise in tool paths from
        producing slivers that mesh libraries then discard.
        """
        xmin, ymin, zmin, xmax, ymax, zmax = (float(v) for v in bounds)
        if resolution <= 0:
            raise ValueError("resolution must be positive")
        if tolerance <= 0:
            raise ValueError("tolerance must be positive")
        if xmax <= xmin or ymax <= ymin or zmax <= zmin:
            raise ValueError("bounds must have a positive size on every axis")

        self.tolerance = float(tolerance)
        self.nx = max(1, int(math.ceil((xmax - xmin) / resolution - 1e-9)))
        self.ny = max(1, int(math.ceil((ymax - ymin) / resolution - 1e-9)))
        if self.nx * self.ny > max_columns:
            raise ValueError(
                "{} x {} columns exceeds max_columns={}; use a coarser resolution".format(
                    self.nx, self.ny, max_columns
                )
            )

        self.xmin, self.ymin, self.zmin = xmin, ymin, zmin
        self.xmax, self.ymax, self.zmax = xmax, ymax, zmax
        self.dx = (xmax - xmin) / self.nx
        self.dy = (ymax - ymin) / self.ny

        count = self.nx * self.ny
        self.lo = array('d', [zmin]) * count
        self.hi = array('d', [zmax]) * count
        self.lo_id = array('H', [0]) * count
        self.hi_id = array('H', [0]) * count
        self.touch = array('H', [0]) * count
        self.multi = {}
        self.removed = {}

        self._rows = [None] * self.ny
        self._dirty = set(range(self.ny))
        self._radial_axis = None
        self._radial_radii = []
        self._radial_columns = []
        self._radial_bounds = []

    @classmethod
    def cylinder(cls, radius, height, resolution, origin=(0.0, 0.0, 0.0),
                 max_columns=2000000, tolerance=1e-4):
        """Create cylinder stock parallel to Z, centred on ``origin`` at its base.

        Columns whose centres lie outside the radius start empty. The round
        wall is therefore approximated to the same spacing as cut surfaces.
        """
        radius, height = float(radius), float(height)
        if not math.isfinite(radius) or radius <= 0:
            raise ValueError("radius must be finite and positive")
        if not math.isfinite(height) or height <= 0:
            raise ValueError("height must be finite and positive")
        cx, cy, zmin = (float(value) for value in origin)
        if not all(math.isfinite(value) for value in (cx, cy, zmin)):
            raise ValueError("origin must be finite")
        grid = cls(
            (cx - radius, cy - radius, zmin,
             cx + radius, cy + radius, zmin + height),
            resolution, max_columns, tolerance)
        radius2 = radius * radius
        for j in range(grid.ny):
            y2 = (grid.ymin + (j + 0.5) * grid.dy - cy) ** 2
            for i in range(grid.nx):
                x = grid.xmin + (i + 0.5) * grid.dx - cx
                if x * x + y2 > radius2:
                    c = j * grid.nx + i
                    grid.hi[c] = grid.lo[c]
        return grid

    # ------------------------------------------------------------------ cutting

    def cut_segment(self, tool, tool_id, start, end):
        """Remove the volume swept by ``tool`` moving from ``start`` to ``end``.

        Points are ``(x, y, z)`` of the tool origin. ``tool_id`` (1-65535) is
        recorded on the surfaces this cut creates; callers can use operation IDs
        instead of tool IDs. Returns the number of columns that changed.

        Z-changing moves combine midpoint-height XY sweeps with exact tool
        footprints at both endpoints.
        """
        if not 0 < tool_id < 65536:
            raise ValueError("tool_id must be between 1 and 65535")
        self._radial_axis = None
        x0, y0, z0 = start
        x1, y1, z1 = end
        dx, dy, dz = x1 - x0, y1 - y0, z1 - z0
        steps = max(
            1,
            int(math.ceil(math.hypot(dx, dy) / (2.0 * tool.radius))),
            int(math.ceil(abs(dz) / (0.25 * min(self.dx, self.dy)))),
        )
        steps = min(steps, 5000)

        changed = 0
        if dz != 0.0:
            changed += self._cut_piece(tool, tool_id, x0, y0, x0, y0, z0)
        for step in range(steps):
            t0 = step / steps
            t1 = (step + 1) / steps
            changed += self._cut_piece(
                tool, tool_id,
                x0 + dx * t0, y0 + dy * t0,
                x0 + dx * t1, y0 + dy * t1,
                z0 + dz * (t0 + t1) * 0.5,
            )
        if dz != 0.0:
            changed += self._cut_piece(tool, tool_id, x1, y1, x1, y1, z1)
        return changed

    def _cut_piece(self, tool, tool_id, ax, ay, bx, by, z):
        nx, ny = self.nx, self.ny
        dx, dy = self.dx, self.dy
        radius = tool.radius
        i0 = max(0, int(math.floor((min(ax, bx) - radius - self.xmin) / dx)))
        i1 = min(nx - 1, int(math.floor((max(ax, bx) + radius - self.xmin) / dx)))
        j0 = max(0, int(math.floor((min(ay, by) - radius - self.ymin) / dy)))
        j1 = min(ny - 1, int(math.floor((max(ay, by) + radius - self.ymin) / dy)))
        if i0 > i1 or j0 > j1:
            return 0

        sx, sy = bx - ax, by - ay
        seg2 = sx * sx + sy * sy
        r2 = radius * radius
        flat = tool.is_flat
        flat_bottom = z + tool.flat_bottom
        top = z + tool.top
        table = tool.table
        scale = tool.table_scale
        sqrt = math.sqrt

        touch = self.touch
        dirty = self._dirty
        xmin, ymin = self.xmin, self.ymin
        changed = 0

        for j in range(j0, j1 + 1):
            cy = ymin + (j + 0.5) * dy - ay
            base = j * nx
            row_changed = False
            for i in range(i0, i1 + 1):
                cx = xmin + (i + 0.5) * dx - ax
                if seg2 > 0.0:
                    t = (cx * sx + cy * sy) / seg2
                    if t < 0.0:
                        t = 0.0
                    elif t > 1.0:
                        t = 1.0
                    ex = cx - t * sx
                    ey = cy - t * sy
                    d2 = ex * ex + ey * ey
                else:
                    d2 = cx * cx + cy * cy
                if d2 > r2:
                    continue

                if flat:
                    bottom = flat_bottom
                else:
                    bottom = z + table[int(sqrt(d2) * scale + 0.5)]

                c = base + i
                if self._cut_column(c, bottom, top, tool_id):
                    touch[c] = tool_id
                    row_changed = True
                    changed += 1

            if row_changed:
                dirty.add(j)
                if j > 0:
                    dirty.add(j - 1)
        return changed

    def cut_turning(self, tool, tool_id, start, end, axis=(0.0, 0.0)):
        """Remove a convex insert sweep revolved around a Z-parallel spindle."""
        if not 0 < tool_id < 65536:
            raise ValueError("tool_id must be between 1 and 65535")
        axis = tuple(float(value) for value in axis)
        if len(axis) != 2 or not all(math.isfinite(value) for value in axis):
            raise ValueError("Spindle axis must have two finite XY coordinates")
        polygon = tool.sweep(start, end)
        rmin = min(x for x, _ in polygon)
        rmax = max(x for x, _ in polygon)
        if (max(z for _, z in polygon) <= self.zmin + self.tolerance
                or min(z for _, z in polygon) >= self.zmax - self.tolerance):
            return 0
        if axis != self._radial_axis:
            columns = {}
            for j in range(self.ny):
                y = self.ymin + (j + 0.5) * self.dy - axis[1]
                for i in range(self.nx):
                    x = self.xmin + (i + 0.5) * self.dx - axis[0]
                    # Share slices between symmetric columns despite floating-point noise.
                    radius = round(math.hypot(x, y), 12)
                    columns.setdefault(radius, []).append(j * self.nx + i)
            self._radial_radii = sorted(columns)
            self._radial_columns = [columns[r] for r in self._radial_radii]
            self._radial_bounds = [
                self._material_bounds(group) for group in self._radial_columns]
            self._radial_axis = axis
        polygons = [polygon] if rmax >= 0 else []
        if rmin < 0:
            reflected = [(-x, z) for x, z in reversed(polygon)]
            left = min(range(len(reflected)), key=lambda index: reflected[index])
            polygons.append(reflected[left:] + reflected[:left])
        # Revolution folds signed X onto radius. Keep both slices separate:
        # their axial intervals can be disjoint at the same physical radius.
        return sum(self._cut_turning_polygon(tool, tool_id, sweep) for sweep in polygons)

    def _cut_turning_polygon(self, tool, tool_id, polygon):
        changed = 0
        first = bisect_left(self._radial_radii, max(0, min(x for x, _ in polygon)))
        last = bisect_right(self._radial_radii, max(x for x, _ in polygon))
        spans = tool.spans(polygon, self._radial_radii[first:last])
        for index, (bottom, top) in zip(range(first, last), spans):
            if top - bottom <= self.tolerance:
                continue
            low, high = self._radial_bounds[index]
            if high - bottom <= self.tolerance or top - low <= self.tolerance:
                continue
            group_changed = False
            for c in self._radial_columns[index]:
                if self._cut_column(c, bottom, top, tool_id):
                    group_changed = True
                    self.touch[c] = tool_id
                    j = c // self.nx
                    self._dirty.add(j)
                    if j > 0:
                        self._dirty.add(j - 1)
                    changed += 1
            if group_changed:
                self._radial_bounds[index] = self._material_bounds(self._radial_columns[index])
        return changed

    def _material_bounds(self, columns):
        low, high = math.inf, -math.inf
        for c in columns:
            intervals = self.multi.get(c)
            bottom, top = (intervals[0][0], intervals[-1][1]) if intervals else (self.lo[c], self.hi[c])
            if top - bottom > self.tolerance:
                low = min(low, bottom)
                high = max(high, top)
        return low, high

    def _cut_column(self, c, bottom, top, tool_id):
        if c in self.multi:
            return self._cut_multi(c, bottom, top, tool_id)
        tol = self.tolerance
        low, high = self.lo[c], self.hi[c]
        if high - low <= tol or high - bottom <= tol or top - low <= tol:
            return False
        if bottom - low > tol:
            if high - top > tol:
                self.multi[c] = [
                    [low, bottom, self.lo_id[c], tool_id],
                    [top, high, tool_id, self.hi_id[c]],
                ]
            else:
                self.hi[c] = bottom
                self.hi_id[c] = tool_id
        elif high - top > tol:
            self.lo[c] = top
            self.lo_id[c] = tool_id
        else:
            self.hi[c] = low
        self._record_removed(c, [(max(low, bottom) if bottom - low > tol else low,
                                 min(high, top) if high - top > tol else high)], tool_id)
        return True

    def _cut_multi(self, c, bottom, top, tool_id):
        tol = self.tolerance
        changed = False
        result = []
        removed = []
        for low, high, low_id, high_id in self.multi[c]:
            if high - bottom <= tol or top - low <= tol:
                result.append([low, high, low_id, high_id])
                continue
            changed = True
            removed.append((bottom if bottom - low > tol else low,
                            top if high - top > tol else high))
            if bottom - low > tol:
                result.append([low, bottom, low_id, tool_id])
            if high - top > tol:
                result.append([top, high, tool_id, high_id])
        if changed:
            self._record_removed(c, removed, tool_id)
            if len(result) >= 2:
                self.multi[c] = result
            else:
                del self.multi[c]
                if result:
                    low, high, low_id, high_id = result[0]
                    self.lo[c], self.hi[c] = low, high
                    self.lo_id[c], self.hi_id[c] = low_id, high_id
                else:
                    self.hi[c] = self.lo[c]
        return changed

    def _record_removed(self, c, intervals, tool_id):
        """Remember only newly removed material, never overwrite earlier cuts."""
        spans = self.removed.get(c, []) + [(low, high, tool_id) for low, high in intervals]
        spans.sort()
        merged = []
        for low, high, owner in spans:
            if (merged and merged[-1][2] == owner
                    and low - merged[-1][1] <= self.tolerance):
                merged[-1] = (merged[-1][0], high, owner)
            else:
                merged.append((low, high, owner))
        self.removed[c] = merged

    def _wall_owners(self, c, low, high):
        """Split an exposed wall by the cuts that removed its neighbour."""
        tol = self.tolerance
        current = low
        for start, end, owner in self.removed.get(c, ()):
            if min(end, high) - max(current, start) <= tol:
                continue
            if start >= high - tol:
                break
            if start - current > tol:
                yield current, min(start, high), 0
                current = start
            stop = high if high - end <= tol else end
            yield current, stop, owner
            current = stop
            if current >= high:
                return
        if current < high:
            yield current, high, 0

    # ------------------------------------------------------------------ queries

    def volume(self):
        """Total material volume remaining."""
        total = sum(h - l for l, h in zip(self.lo, self.hi) if h > l)
        for c, intervals in self.multi.items():
            total -= max(0.0, self.hi[c] - self.lo[c])
            total += sum(h - l for l, h, _, _ in intervals)
        return total * self.dx * self.dy

    def stats(self):
        return {
            "columns": self.nx * self.ny,
            "columns_with_multiple_intervals": len(self.multi),
            "dirty_rows": len(self._dirty),
        }

    # --------------------------------------------------------------- extraction

    def extract(self):
        """Return ``(triangles, tool_ids)`` describing the current surface.

        Each triangle is a flat tuple of nine floats
        ``(x0, y0, z0, x1, y1, z1, x2, y2, z2)`` with counter-clockwise winding
        seen from outside the material. ``tool_ids[k]`` is the tool that created
        triangle ``k`` (0 is untouched stock). Only rows changed since the
        previous call are rebuilt.
        """
        for j in sorted(self._dirty):
            self._rows[j] = self._build_row(j)
        self._dirty.clear()

        triangles = []
        ids = []
        for row_triangles, row_ids in self._rows:
            triangles.extend(row_triangles)
            ids.extend(row_ids)
        return triangles, ids

    def _intervals(self, c):
        intervals = self.multi.get(c)
        if intervals is not None:
            return intervals
        low, high = self.lo[c], self.hi[c]
        if high > low:
            return ((low, high),)
        return ()

    @staticmethod
    def _exposed(a, b):
        """Z ranges where intervals ``a`` have material and ``b`` do not."""
        result = []
        for interval in a:
            low, high = interval[0], interval[1]
            current = low
            for other in b:
                if other[1] <= current:
                    continue
                if other[0] >= high:
                    break
                if other[0] > current:
                    result.append((current, other[0]))
                if other[1] > current:
                    current = other[1]
                if current >= high:
                    break
            if current < high:
                result.append((current, high))
        return result

    def _build_row(self, j):
        nx, ny = self.nx, self.ny
        dx, dy = self.dx, self.dy
        tol = self.tolerance
        xmin = self.xmin
        y0 = self.ymin + j * dy
        y1 = y0 + dy
        lo, hi = self.lo, self.hi
        lo_id, hi_id = self.lo_id, self.hi_id
        multi = self.multi
        base = j * nx
        tris = []
        ids = []

        def horizontal(i0, i1, z, tool_id, up):
            xa = xmin + i0 * dx
            xb = xmin + i1 * dx
            if up:
                tris.append((xa, y0, z, xb, y0, z, xb, y1, z))
                tris.append((xa, y0, z, xb, y1, z, xa, y1, z))
            else:
                tris.append((xa, y0, z, xb, y1, z, xb, y0, z))
                tris.append((xa, y0, z, xa, y1, z, xb, y1, z))
            ids.append(tool_id)
            ids.append(tool_id)

        # Top and bottom faces, merging neighbouring columns with equal heights.
        run_top = None
        run_bottom = None

        def continues(run, key):
            return (key is not None and run[1][1] == key[1]
                    and abs(run[1][0] - key[0]) <= tol)

        for i in range(nx + 1):
            c = base + i
            if i < nx and c not in multi:
                low, high = lo[c], hi[c]
                if high > low:
                    top_key = (high, hi_id[c])
                    bottom_key = (low, lo_id[c])
                else:
                    top_key = bottom_key = None
            else:
                top_key = bottom_key = None

            if run_top is not None and not continues(run_top, top_key):
                horizontal(run_top[0], i, run_top[1][0], run_top[1][1], True)
                run_top = None
            if run_top is None and top_key is not None:
                run_top = (i, top_key)

            if run_bottom is not None and not continues(run_bottom, bottom_key):
                horizontal(run_bottom[0], i, run_bottom[1][0], run_bottom[1][1], False)
                run_bottom = None
            if run_bottom is None and bottom_key is not None:
                run_bottom = (i, bottom_key)

            if i < nx and c in multi:
                for low, high, low_id, high_id in multi[c]:
                    horizontal(i, i + 1, high, high_id, True)
                    horizontal(i, i + 1, low, low_id, False)

        def wall_x(xw, z0, z1, positive, tool_id):
            if z1 - z0 <= tol:
                return
            if positive:
                tris.append((xw, y0, z0, xw, y1, z0, xw, y1, z1))
                tris.append((xw, y0, z0, xw, y1, z1, xw, y0, z1))
            else:
                tris.append((xw, y0, z0, xw, y1, z1, xw, y1, z0))
                tris.append((xw, y0, z0, xw, y0, z1, xw, y1, z1))
            ids.append(tool_id)
            ids.append(tool_id)

        def wall_y(yw, i, z0, z1, positive, tool_id):
            if z1 - z0 <= tol:
                return
            xa = xmin + i * dx
            xb = xa + dx
            if positive:
                tris.append((xa, yw, z0, xa, yw, z1, xb, yw, z1))
                tris.append((xa, yw, z0, xb, yw, z1, xb, yw, z0))
            else:
                tris.append((xa, yw, z0, xb, yw, z1, xa, yw, z1))
                tris.append((xa, yw, z0, xb, yw, z0, xb, yw, z1))
            ids.append(tool_id)
            ids.append(tool_id)

        exposed = self._exposed

        # Walls facing X between neighbouring columns, and at both grid edges.
        for i in range(-1, nx):
            a = base + i if i >= 0 else -1
            b = base + i + 1 if i + 1 < nx else -1
            if (a >= 0 and b >= 0 and a not in multi and b not in multi
                    and abs(lo[a] - lo[b]) <= tol and abs(hi[a] - hi[b]) <= tol):
                continue
            first = self._intervals(a) if a >= 0 else ()
            second = self._intervals(b) if b >= 0 else ()
            xw = xmin + (i + 1) * dx
            if first:
                for z0, z1 in exposed(first, second):
                    for low, high, owner in self._wall_owners(b, z0, z1):
                        wall_x(xw, low, high, True, owner)
            if second:
                for z0, z1 in exposed(second, first):
                    for low, high, owner in self._wall_owners(a, z0, z1):
                        wall_x(xw, low, high, False, owner)

        # Walls facing Y: the outer edge for the first row, then to the next row.
        if j == 0:
            for i in range(nx):
                c = base + i
                for z0, z1 in exposed(self._intervals(c), ()):
                    wall_y(y0, i, z0, z1, False, 0)
        for i in range(nx):
            a = base + i
            b = base + nx + i if j + 1 < ny else -1
            if (b >= 0 and a not in multi and b not in multi
                    and abs(lo[a] - lo[b]) <= tol and abs(hi[a] - hi[b]) <= tol):
                continue
            first = self._intervals(a)
            second = self._intervals(b) if b >= 0 else ()
            if first:
                for z0, z1 in exposed(first, second):
                    for low, high, owner in self._wall_owners(b, z0, z1):
                        wall_y(y1, i, low, high, True, owner)
            if second:
                for z0, z1 in exposed(second, first):
                    for low, high, owner in self._wall_owners(a, z0, z1):
                        wall_y(y1, i, low, high, False, owner)

        return tris, ids
