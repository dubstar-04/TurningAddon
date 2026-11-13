"""Turning simulation on the 2D radius/Z profile of a solid of revolution.

Every turning move removes a convex insert section translated in XZ and revolved
through a full spindle revolution. The stock therefore remains a solid of
revolution and is stored as radial intervals on thin Z slices instead of as a
3D grid. The display mesh revolves the simplified profile, so its size depends
on the profile detail rather than on the stock area.

Threading needs synchronized spindle angle and is not represented here.
"""

import io
import math
import struct
import time

import FreeCAD
import Mesh
import numpy as np
import Part


def _cylinderRadius(stock):
	''' recognise a complete cylinder parallel to Z, not a bore or partial cylinder '''
	if len(stock.Solids) != 1 or len(stock.Faces) != 3:
		return None
	cylinders = [face.Surface for face in stock.Faces if isinstance(face.Surface, Part.Cylinder)]
	planes = [face.Surface for face in stock.Faces if isinstance(face.Surface, Part.Plane)]
	if len(cylinders) != 1 or len(planes) != 2:
		return None
	cylinder = cylinders[0]
	if math.hypot(cylinder.Axis.x, cylinder.Axis.y) > 1e-8:
		return None
	box = stock.BoundBox
	radius = cylinder.Radius
	if (not math.isclose(box.XLength, 2 * radius, rel_tol=1e-7, abs_tol=1e-6)
			or not math.isclose(box.YLength, 2 * radius, rel_tol=1e-7, abs_tol=1e-6)
			or not math.isclose(stock.Volume, math.pi * radius ** 2 * box.ZLength,
				rel_tol=1e-7, abs_tol=1e-6)):
		return None
	return radius


_STL_RECORD = np.dtype([
	("normal", "<f4", (3,)),
	("vertices", "<f4", (9,)),
	("attribute", "<u2"),
])


def _buildMesh(triangles):
	'''Build a FreeCAD mesh from an (N, 9) triangle array through binary STL.'''
	count = len(triangles)
	if count > 0xffffffff:
		raise ValueError("Too many triangles for a binary STL mesh")
	if triangles.shape != (count, 9):
		raise ValueError("Expected triangle coordinates with shape (N, 9)")
	if not np.isfinite(triangles).all():
		raise ValueError("Triangle coordinates must be finite")
	records = np.zeros(count, dtype=_STL_RECORD)
	with np.errstate(over="raise", invalid="raise"):
		records["vertices"] = triangles
	stream = io.BytesIO(bytes(80) + struct.pack("<I", count) + records.tobytes())
	mesh = Mesh.Mesh()
	mesh.read(stream, "STL")
	if mesh.CountFacets != count:
		raise RuntimeError("FreeCAD did not preserve all streamed mesh facets")
	return mesh


def _hull(points):
	points = sorted(set(points))
	if len(points) < 3:
		raise ValueError("A profile needs at least three distinct points")

	def cross(o, a, b):
		return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

	lower, upper = [], []
	for point in points:
		while len(lower) >= 2 and cross(lower[-2], lower[-1], point) <= 0:
			lower.pop()
		lower.append(point)
	for point in reversed(points):
		while len(upper) >= 2 and cross(upper[-2], upper[-1], point) <= 0:
			upper.pop()
		upper.append(point)
	return lower[:-1] + upper[:-1]


def _area(points):
	return abs(sum(a[0] * b[1] - b[0] * a[1]
		for a, b in zip(points, points[1:] + points[:1]))) / 2


def _simplify(r, z, tolerance):
	''' Douglas-Peucker indices of a profile polyline, always keeping both ends '''
	keep = np.zeros(len(r), dtype=bool)
	keep[0] = keep[-1] = True
	stack = [(0, len(r) - 1)]
	while stack:
		first, last = stack.pop()
		if last - first < 2:
			continue
		dr, dz = r[last] - r[first], z[last] - z[first]
		length = math.hypot(dr, dz)
		segment = slice(first + 1, last)
		if length == 0:
			distance = np.hypot(r[segment] - r[first], z[segment] - z[first])
		else:
			distance = np.abs((r[segment] - r[first]) * dz - (z[segment] - z[first]) * dr) / length
		index = int(np.argmax(distance))
		if distance[index] > tolerance:
			index += first + 1
			keep[index] = True
			stack.append((first, index))
			stack.append((index, last))
	return np.flatnonzero(keep)


def _subtract(intervals, other):
	''' parts of sorted disjoint intervals not covered by other sorted disjoint intervals '''
	result = []
	for low, high in intervals:
		for otherLow, otherHigh in other:
			if otherHigh <= low or otherLow >= high:
				continue
			if otherLow > low:
				result.append((low, otherLow))
			low = max(low, otherHigh)
			if low >= high:
				break
		if low < high:
			result.append((low, high))
	return result


class Engine:
	''' Full-revolution turning on a 2D stock profile.

	The stock must be a complete cylinder on the Z spindle at X = Y = 0. Each Z
	slice stores sorted radial material intervals with the operation that
	created their inner and outer faces.
	'''

	supportsTurningSweeps = True
	meshStableWhenUnchanged = True
	turningOnly = True
	engineLabel = "turning_profile"

	def __init__(self):
		self.axialResolution = 0.01  # slice thickness in model units
		self.maxSlices = 50000
		self.displayTolerance = 0.01  # profile and chord deviation of the display mesh
		self.minSegments = 24
		self.maxSegments = 360
		self.tolerance = 1e-6
		self.tool = None
		self.operationId = 0
		self.faceOperationIds = []
		self._lastPosition = None
		self._clear()

	def _clear(self):
		self.slices = 0
		self._mesh = None
		self._meshDirty = True
		self._surface = None
		self._surfaceDirty = True
		self._positions = 0
		self._resetWindow()

	def _resetWindow(self):
		self._cuts = 0
		self._cutTime = 0.0
		self._slicesChanged = 0
		self._surfaceUpdates = 0
		self._extractTime = 0.0
		self._meshUpdates = 0
		self._meshTime = 0.0
		self._triangles = 0

	def setStock(self, stock):
		radius = _cylinderRadius(stock)
		if radius is None:
			raise ValueError("Turning requires complete cylinder stock with its spindle parallel to Z")
		box = stock.BoundBox
		axis = ((box.XMin + box.XMax) / 2, (box.YMin + box.YMax) / 2)
		if any(abs(value) > 1e-7 for value in axis):
			raise ValueError("Turning currently requires the spindle on X = Y = 0")
		self.setCylinder(radius, box.ZMin, box.ZMax)
		FreeCAD.Console.PrintMessage(
			"[PathSim {}] cylindrical stock: radius {:.3f}, {} slices of {:.4f}\n".format(
				self.engineLabel, radius, self.slices, self.dz))

	def setCylinder(self, radius, zMin, zMax):
		if not (radius > 0 and zMax > zMin and math.isfinite(radius) and math.isfinite(zMax - zMin)):
			raise ValueError("Cylinder dimensions must be finite and positive")
		self._clear()
		self.radius = radius
		self.z0 = zMin
		self.slices = min(self.maxSlices, max(1, math.ceil((zMax - zMin) / self.axialResolution - 1e-9)))
		self.dz = (zMax - zMin) / self.slices
		self.low = np.zeros((self.slices, 1))
		self.high = np.full((self.slices, 1), float(radius))
		self.lowOwner = np.zeros((self.slices, 1), dtype=np.uint16)
		self.highOwner = np.zeros((self.slices, 1), dtype=np.uint16)
		self.removedBy = np.zeros(self.slices, dtype=np.uint16)
		segments = math.pi / math.acos(max(-1.0, 1 - self.displayTolerance / radius))
		self.segments = int(min(self.maxSegments, max(self.minSegments, math.ceil(segments))))
		angles = np.arange(self.segments + 1) * (2 * math.pi / self.segments)
		self._cos, self._sin = np.cos(angles), np.sin(angles)
		self._cos[-1], self._sin[-1] = 1.0, 0.0
		self._lastPosition = None

	def setTool(self, tool):
		raise ValueError("The turning_profile engine supports turning operations only")

	def setTurningTool(self, tool):
		if not self.slices:
			raise ValueError("Set the stock before the turning tool")
		wires = tool.slice(FreeCAD.Vector(0, 1, 0), tool.BoundBox.Center.y)
		if len(wires) != 1 or not wires[0].isClosed():
			raise ValueError("Turning tool must have one closed insert profile in its XZ section")
		deflection = min(0.1, self.dz / 4)
		points = wires[0].discretize(Deflection=deflection)
		self.setProfile([(point.x, point.z) for point in points])
		FreeCAD.Console.PrintMessage(
			"[PathSim {}] turning insert: {} hull points, deflection {:.4f}\n".format(
				self.engineLabel, len(self.tool), deflection))

	def setProfile(self, points):
		points = [(float(x), float(z)) for x, z in points]
		if not all(math.isfinite(value) for point in points for value in point):
			raise ValueError("Coordinates must be finite")
		if len(points) > 1 and points[0] == points[-1]:
			points.pop()
		convex = _hull(points)
		original, hull = _area(points), _area(convex)
		if hull <= 1e-12:
			raise ValueError("Profile has no area")
		if abs(original - hull) > max(1e-8, 1e-6 * max(original, hull)):
			raise ValueError("Only a single convex profile is supported")
		self.tool = np.array(convex)
		self._lastPosition = None

	def setOperation(self, operationId):
		if not 0 < operationId < 65536:
			raise ValueError("Operation id must be between 1 and 65535")
		self.operationId = operationId
		self._lastPosition = None

	def processPosition(self, placement):
		if not self.slices or self.tool is None or not self.operationId:
			raise RuntimeError("The turning profile engine needs a stock, tool and operation before cutting")
		base = placement.Base
		if abs(base.y) > 1e-7:
			raise ValueError("Turning tool positions must be in the XZ plane")
		position = (base.x, base.z)
		start = time.perf_counter()
		changed = self.cut(self._lastPosition or position, position)
		self._slicesChanged += changed
		if changed:
			self._meshDirty = self._surfaceDirty = True
		self._cutTime += time.perf_counter() - start
		self._lastPosition = position
		self._cuts += 1
		self._positions += 1
		if self._positions % 50 == 0:
			self.reportPerformance()

	def cut(self, start, end):
		''' remove the revolved convex hull of the tool at start and end; returns changed slices '''
		polygon = np.array(_hull([tuple(p) for p in np.vstack((self.tool + start, self.tool + end))]))
		first = max(0, math.ceil((polygon[:, 1].min() - self.z0) / self.dz - 0.5))
		last = min(self.slices - 1, math.floor((polygon[:, 1].max() - self.z0) / self.dz - 0.5))
		if last < first:
			return 0
		rows = np.arange(first, last + 1)
		z = self.z0 + (rows + 0.5) * self.dz

		a, b = polygon, np.roll(polygon, -1, axis=0)
		edges = a[:, 1] != b[:, 1]
		a, b = a[edges], b[edges]
		t = (z[:, None] - a[:, 1]) / (b[:, 1] - a[:, 1])
		inside = (t >= 0) & (t <= 1)
		x = a[:, 0] + t * (b[:, 0] - a[:, 0])
		xMin = np.where(inside, x, np.inf).min(axis=1)
		xMax = np.where(inside, x, -np.inf).max(axis=1)
		hit = xMin <= xMax
		rows, xMin, xMax = rows[hit], xMin[hit], xMax[hit]
		if not len(rows):
			return 0
		bottom = np.where(xMin >= 0, xMin, np.where(xMax <= 0, -xMax, 0.0))[:, None]
		top = np.maximum(np.abs(xMin), np.abs(xMax))[:, None]

		low, high = self.low[rows], self.high[rows]
		lowOwner, highOwner = self.lowOwner[rows], self.highOwner[rows]
		valid = ~np.isnan(low)
		tolerance = self.tolerance
		with np.errstate(invalid="ignore"):
			overlap = valid & (high - bottom > tolerance) & (top - low > tolerance)
			if not overlap.any():
				return 0
			keepLeft = valid & (~overlap | (bottom - low > tolerance))
			keepRight = overlap & (high - top > tolerance)
		# each interval leaves a piece below the cut and a piece above it
		owner = np.uint16(self.operationId)
		count = len(rows)

		def interleave(below, above):
			return np.stack(np.broadcast_arrays(below, above), axis=2).reshape(count, -1)

		pieceLow = interleave(low, top)
		pieceHigh = interleave(np.where(overlap, bottom, high), high)
		pieceLowOwner = interleave(lowOwner, owner)
		pieceHighOwner = interleave(np.where(overlap, owner, highOwner), highOwner)
		keep = interleave(keepLeft, keepRight)
		order = np.argsort(~keep, axis=1, kind="stable")
		needed = int(keep.sum(axis=1).max())
		width = max(needed, 1)
		if width > self.low.shape[1]:
			extra = width - self.low.shape[1]
			self.low = np.pad(self.low, ((0, 0), (0, extra)), constant_values=np.nan)
			self.high = np.pad(self.high, ((0, 0), (0, extra)), constant_values=np.nan)
			self.lowOwner = np.pad(self.lowOwner, ((0, 0), (0, extra)))
			self.highOwner = np.pad(self.highOwner, ((0, 0), (0, extra)))
		width = self.low.shape[1]

		def compact(values, fill):
			values = np.take_along_axis(values, order, axis=1)
			sorted_keep = np.take_along_axis(keep, order, axis=1)
			values = np.where(sorted_keep, values, fill)
			if values.shape[1] < width:
				values = np.pad(values, ((0, 0), (0, width - values.shape[1])), constant_values=fill)
			return values[:, :width]

		changed = overlap.any(axis=1)
		target = rows[changed]
		self.low[target] = compact(pieceLow, np.nan)[changed]
		self.high[target] = compact(pieceHigh, np.nan)[changed]
		self.lowOwner[target] = compact(pieceLowOwner, 0)[changed]
		self.highOwner[target] = compact(pieceHighOwner, 0)[changed]
		self.removedBy[target] = owner
		return int(changed.sum())

	def intervals(self, row):
		valid = ~np.isnan(self.low[row])
		return list(zip(self.low[row][valid].tolist(), self.high[row][valid].tolist()))

	def extractSurface(self):
		''' return (N, 9) triangles and their operation ids for the revolved profile '''
		valid = ~np.isnan(self.low)
		counts = valid.sum(axis=1)
		with np.errstate(invalid="ignore"):
			overlap = np.where(valid[1:] & valid[:-1],
				(self.low[1:] < self.high[:-1]) & (self.low[:-1] < self.high[1:]), True)
		connected = (counts[1:] == counts[:-1]) & overlap.all(axis=1)
		breaks = np.flatnonzero(~connected) + 1
		starts = np.concatenate(([0], breaks))
		ends = np.concatenate((breaks, [self.slices])) - 1

		segments = []  # (r0, z0, r1, z1, owner); material is on the left of travel
		centres = self.z0 + (np.arange(self.slices) + 0.5) * self.dz
		for first, last in zip(starts.tolist(), ends.tolist()):
			count = int(counts[first])
			z = np.concatenate(([self.z0 + first * self.dz], centres[first:last + 1],
				[self.z0 + (last + 1) * self.dz]))
			for column in range(count):
				for radii, owners, reverse in ((self.high, self.highOwner, False),
						(self.low, self.lowOwner, True)):
					r = radii[first:last + 1, column]
					if reverse and not r.any():
						continue
					r = np.concatenate((r[:1], r, r[-1:]))
					o = owners[first:last + 1, column]
					o = np.concatenate((o[:1], o, o[-1:]))
					self._profileSegments(r, z, o, reverse, segments)

		for boundary in range(self.slices + 1):
			if 0 < boundary < self.slices and connected[boundary - 1]:
				continue
			below = self.intervals(boundary - 1) if boundary > 0 else []
			above = self.intervals(boundary) if boundary < self.slices else []
			zPlane = self.z0 + boundary * self.dz
			upOwner = int(self.removedBy[boundary]) if boundary < self.slices else 0
			downOwner = int(self.removedBy[boundary - 1]) if boundary > 0 else 0
			for low, high in _subtract(below, above):
				segments.append((high, zPlane, low, zPlane, upOwner))
			for low, high in _subtract(above, below):
				segments.append((low, zPlane, high, zPlane, downOwner))
		return self._revolve(segments)

	def _profileSegments(self, r, z, owners, reverse, segments):
		changes = np.flatnonzero(owners[1:] != owners[:-1])
		cuts = np.unique(np.concatenate(([0], changes, changes + 1, [len(r) - 1])))
		kept = []
		for first, last in zip(cuts[:-1].tolist(), cuts[1:].tolist()):
			indices = _simplify(r[first:last + 1], z[first:last + 1], self.displayTolerance) + first
			kept.extend(indices.tolist() if not kept else indices[1:].tolist())
		kept = np.array(kept)
		r0, z0, r1, z1 = r[kept[:-1]], z[kept[:-1]], r[kept[1:]], z[kept[1:]]
		owner = owners[kept[1:]]
		if reverse:
			r0, z0, r1, z1 = r1, z1, r0, z0
		segments.extend(zip(r0.tolist(), z0.tolist(), r1.tolist(), z1.tolist(), owner.tolist()))

	def _revolve(self, segments):
		if not segments:
			return np.empty((0, 9)), np.empty(0, dtype=np.uint16)
		data = np.array(segments, dtype=float)
		data = data[(data[:, 0] != data[:, 2]) | (data[:, 1] != data[:, 3])]
		data = data[(data[:, 0] > 0) | (data[:, 2] > 0)]
		r0, z0, r1, z1, owner = data.T
		cos, sin = self._cos, self._sin
		count = len(data)
		n = self.segments

		def ring(r, z):
			points = np.empty((count, n + 1, 3))
			points[:, :, 0] = r[:, None] * cos
			points[:, :, 1] = r[:, None] * sin
			points[:, :, 2] = z[:, None]
			return points

		a, b = ring(r0, z0), ring(r1, z1)
		first = np.concatenate((a[:, :-1], a[:, 1:], b[:, 1:]), axis=2)
		second = np.concatenate((a[:, :-1], b[:, 1:], b[:, :-1]), axis=2)
		triangles = np.stack((first, second), axis=2)  # (segments, n, 2, 9)
		keep = np.stack((np.broadcast_to((r0 > 0)[:, None], (count, n)),
			np.broadcast_to((r1 > 0)[:, None], (count, n))), axis=2)
		owners = np.broadcast_to(owner.astype(np.uint16)[:, None, None], keep.shape)
		return triangles[keep], owners[keep]

	def getSurface(self):
		if self._surfaceDirty:
			start = time.perf_counter()
			self._surface = self.extractSurface()
			self._extractTime += time.perf_counter() - start
			self._surfaceDirty = False
			self._surfaceUpdates += 1
			self._triangles = len(self._surface[0])
		return self._surface

	def getMesh(self):
		if not self._meshDirty:
			return self._mesh
		triangles, owners = self.getSurface()
		start = time.perf_counter()
		self._mesh = _buildMesh(triangles)
		self._meshTime += time.perf_counter() - start
		self.faceOperationIds = owners
		self._meshDirty = False
		self._meshUpdates += 1
		return self._mesh

	def reportPerformance(self):
		if not self._cuts and not self._surfaceUpdates:
			return

		def average(total, count):
			return "{:.3f}".format(total * 1000 / count) if count else "n/a"

		FreeCAD.Console.PrintMessage(
			"[PathSim {}] positions={} cuts={} cut_avg_ms={} slices_changed={} "
			"surface_updates={} mesh_updates={} triangles={} extract_avg_ms={} mesh_build_avg_ms={}\n".format(
				self.engineLabel, self._positions, self._cuts, average(self._cutTime, self._cuts),
				self._slicesChanged, self._surfaceUpdates, self._meshUpdates, self._triangles,
				average(self._extractTime, self._surfaceUpdates),
				average(self._meshTime, self._meshUpdates)))
		self._resetWindow()
