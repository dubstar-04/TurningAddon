"""Revolved milling tools and convex XZ turning insert profiles."""

import bisect
import math


def _convex_hull(points):
    points = sorted(set(points))
    if len(points) < 3:
        raise ValueError("A turning profile needs at least three distinct points")

    def cross(a, b, c):
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])

    def half(sequence):
        result = []
        for point in sequence:
            while len(result) >= 2 and cross(result[-2], result[-1], point) <= 0:
                result.pop()
            result.append(point)
        return result

    return half(points)[:-1] + half(reversed(points))[:-1]


class TurningTool:
    """A convex insert cross-section in local (radial X, axial Z) coordinates.

    Sweeping the profile along a straight move and revolving it about the
    spindle gives the cut volume. Concave or compound profiles are rejected,
    rather than silently filled by their convex hull.
    """

    def __init__(self, profile):
        points = [(float(x), float(z)) for x, z in profile]
        if not all(math.isfinite(value) for point in points for value in point):
            raise ValueError("Turning profile coordinates must be finite")
        if points and points[0] == points[-1]:
            points.pop()
        hull = _convex_hull(points)

        def area(polygon):
            return abs(sum(a[0] * b[1] - b[0] * a[1]
                           for a, b in zip(polygon, polygon[1:] + polygon[:1]))) / 2

        if area(hull) <= 1e-12:
            raise ValueError("Turning profile has no area")
        if not math.isclose(area(points), area(hull), rel_tol=1e-6, abs_tol=1e-8):
            raise ValueError("Only a single convex turning insert profile is supported")
        self.profile = hull

    def sweep(self, start, end):
        """Convex polygon occupied by the insert during a straight XZ move."""
        positions = [(float(x), float(z)) for x, z in (start, end)]
        if not all(math.isfinite(value) for point in positions for value in point):
            raise ValueError("Turning positions must be finite")
        return _convex_hull([
            (x + position[0], z + position[1])
            for position in positions for x, z in self.profile])

    @staticmethod
    def span(polygon, radius):
        """Axial interval at a radius, or None outside the swept profile."""
        heights = []
        for (x0, z0), (x1, z1) in zip(polygon, polygon[1:] + polygon[:1]):
            if min(x0, x1) <= radius <= max(x0, x1):
                if x0 == x1:
                    heights.extend((z0, z1))
                else:
                    heights.append(z0 + (z1 - z0) * (radius - x0) / (x1 - x0))
        if len(heights) < 2:
            return None
        return min(heights), max(heights)

    @staticmethod
    def spans(polygon, radii):
        """Slice a convex sweep at increasing radii without rescanning its edges."""
        right = max(range(len(polygon)), key=lambda i: polygon[i][0])
        chains = (polygon[:right + 1], polygon[:1] + list(reversed(polygon[right:])))
        edges = [
            [(a, b) for a, b in zip(chain, chain[1:]) if a[0] != b[0]]
            for chain in chains
        ]
        indices = [0, 0]
        for radius in radii:
            heights = []
            for side in (0, 1):
                while (indices[side] + 1 < len(edges[side])
                       and radius > edges[side][indices[side]][1][0]):
                    indices[side] += 1
                (x0, z0), (x1, z1) = edges[side][indices[side]]
                if side:
                    x0, z0, x1, z1 = x1, z1, x0, z0
                heights.append(z0 + (z1 - z0) * (radius - x0) / (x1 - x0))
                index = indices[side]
                if (index + 1 < len(edges[side])
                        and radius == edges[side][index][1][0]):
                    (x0, z0), (x1, z1) = edges[side][index + 1]
                    if side:
                        x0, z0, x1, z1 = x1, z1, x0, z0
                    heights.append(z0 + (z1 - z0) * (radius - x0) / (x1 - x0))
            if radius == polygon[0][0] or radius == polygon[right][0]:
                heights.extend(z for x, z in polygon if x == radius)
            yield min(heights), max(heights)


class RevolvedTool:
    """A tool whose lowest surface is a function of distance from its axis.

    ``profile`` is a sequence of ``(radius, bottom_z)`` points, with ``bottom_z``
    measured from the tool origin (normally the tip). The tool is assumed to
    occupy everything above that lower envelope, up to ``top``, for radii not
    larger than the outermost profile point.

    The envelope is made non-decreasing with radius (each point takes the lowest
    ``bottom_z`` found at its own or any larger radius). That is correct for
    flat, ball, bull-nose, conical and drill-style tools. It is not correct for
    tools whose bottom is lower toward the outside than the centre.
    """

    TABLE_STEPS = 512

    def __init__(self, profile, top=math.inf):
        points = sorted((float(r), float(z)) for r, z in profile)
        if not points:
            raise ValueError("A tool profile needs at least one point")
        if points[0][0] < 0:
            raise ValueError("Profile radii must not be negative")
        if points[-1][0] <= 0:
            raise ValueError("The tool radius must be positive")
        if points[0][0] > 0:
            points.insert(0, (0.0, points[0][1]))

        lowest = math.inf
        for index in range(len(points) - 1, -1, -1):
            radius, z = points[index]
            lowest = min(lowest, z)
            points[index] = (radius, lowest)

        self.profile = points
        self.radius = points[-1][0]
        self.top = float(top)
        self.flat_bottom = points[0][1]
        self.is_flat = all(z == self.flat_bottom for _, z in points)
        if self.top <= points[-1][1]:
            raise ValueError("The tool top must be above its lowest surface")

        radii = [r for r, _ in points]
        heights = [z for _, z in points]
        steps = self.TABLE_STEPS
        self.table = [
            self._interpolate(radii, heights, step * self.radius / steps)
            for step in range(steps + 1)
        ]
        self.table_scale = steps / self.radius

    @staticmethod
    def _interpolate(radii, heights, radius):
        index = bisect.bisect_right(radii, radius)
        if index == 0:
            return heights[0]
        if index >= len(radii):
            return heights[-1]
        r0, r1 = radii[index - 1], radii[index]
        z0, z1 = heights[index - 1], heights[index]
        return z0 + (z1 - z0) * (radius - r0) / (r1 - r0)

    def bottom(self, radius):
        """Height of the tool's lowest surface at ``radius`` from the axis."""
        if radius >= self.radius:
            return self.table[-1]
        return self.table[int(radius * self.table_scale + 0.5)]

    @classmethod
    def flat(cls, radius, length=math.inf):
        return cls([(0.0, 0.0), (radius, 0.0)], top=length)

    @classmethod
    def ball(cls, radius, length=math.inf, steps=32):
        points = []
        for step in range(steps + 1):
            r = radius * step / steps
            points.append((r, radius - math.sqrt(max(0.0, radius * radius - r * r))))
        return cls(points, top=length)

    @classmethod
    def from_points(cls, points, bin_width, top=None):
        """Estimate a tool from ``(x, y, z)`` points on its surface.

        Points are grouped by distance from the Z axis; the lowest point in each
        group defines the lower envelope. ``top`` defaults to the highest point.
        """
        if bin_width <= 0:
            raise ValueError("bin_width must be positive")
        lowest = {}
        highest = -math.inf
        for x, y, z in points:
            radius = math.hypot(x, y)
            key = int(radius / bin_width + 0.5)
            current = lowest.get(key)
            if current is None or z < current[1]:
                lowest[key] = (radius, z)
            highest = max(highest, z)
        if not lowest:
            raise ValueError("No points to build a tool from")
        return cls(lowest.values(), top=highest if top is None else top)
