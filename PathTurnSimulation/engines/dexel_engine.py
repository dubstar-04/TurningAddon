# -*- coding: utf-8 -*-

# ***************************************************************************
# *                                                                         *
# *   Copyright (c) 2020 Daniel Wood <s.d.wood.82@googlemail.com>            *
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
import time

import FreeCAD
import Mesh
import Part

from .. import dexel


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


class Engine:
	''' Material removal using the standalone dexel library.

	This adapter only converts between FreeCAD objects and the library: the stock
	becomes a box or Z-aligned cylinder grid. Milling tools become revolved
	profiles; turning tools use their convex XZ insert section. The surface is
	returned as a FreeCAD mesh. Tool positions are
	cut as segments from the previous position so material between the sampled
	positions is removed too. Turning supports complete straight-command sweeps
	without intermediate samples.
	'''

	supportsTurningSweeps = True
	meshStableWhenUnchanged = True

	def __init__(self):
		self.grid = None
		self.tool = None
		self.operationId = 0
		self.faceOperationIds = []  # replaced for each mesh, never modified
		self._mesh = None
		self._meshDirty = True
		self._surface = None
		self._surfaceDirty = True
		self.resolution = None  # model units; None chooses it from the stock size
		self.targetColumns = 100000
		self.toolTessellation = 0.1
		self._lastPosition = None
		self._spindleAxis = None
		self._turning = False
		self._resetPerformance()

	def _resetPerformance(self):
		self._positions = 0
		self._resetWindow()
		self._triangles = 0

	def _resetWindow(self):
		self._cuts = 0
		self._cutTime = 0.0
		self._columnsChanged = 0
		self._meshUpdates = 0
		self._surfaceUpdates = 0
		self._extractTime = 0.0
		self._meshTime = 0.0

	def setStock(self, stock):
		''' set the starting stock definition. stock is a freecad shape object'''
		box = stock.BoundBox
		if box.XLength <= 0 or box.YLength <= 0 or box.ZLength <= 0:
			raise ValueError("Stock has no volume")

		boxVolume = box.XLength * box.YLength * box.ZLength
		resolution = self.resolution
		if resolution is None:
			resolution = max(0.01, math.sqrt(box.XLength * box.YLength / self.targetColumns))

		radius = _cylinderRadius(stock)
		self._spindleAxis = None
		self._turning = False
		if radius is not None:
			self._spindleAxis = ((box.XMin + box.XMax) / 2, (box.YMin + box.YMax) / 2)
			self.grid = dexel.DexelGrid.cylinder(
				radius, box.ZLength, resolution,
				origin=((box.XMin + box.XMax) / 2, (box.YMin + box.YMax) / 2, box.ZMin))
			FreeCAD.Console.PrintMessage(
				"[PathSim dexel] cylindrical stock: radius {:.3f}, height {:.3f}\n".format(
					radius, box.ZLength))
		else:
			if abs(stock.Volume - boxVolume) > 0.01 * boxVolume:
				FreeCAD.Console.PrintWarning(
					"[PathSim dexel] Stock is not a box or Z-aligned cylinder; "
					"its bounding box will be used.\n")
			self.grid = dexel.DexelGrid(
				(box.XMin, box.YMin, box.ZMin, box.XMax, box.YMax, box.ZMax), resolution)
		self.tool = None
		self.operationId = 0
		self.faceOperationIds = []
		self._mesh = None
		self._meshDirty = True
		self._surface = None
		self._surfaceDirty = True
		self._lastPosition = None
		self._resetPerformance()
		FreeCAD.Console.PrintMessage(
			"[PathSim dexel] grid {} x {} columns, resolution {:.3f}\n".format(
				self.grid.nx, self.grid.ny, resolution))

	def setTool(self, tool):
		''' set the tool definition. tool is a freecad shape object

		The tool origin is expected at the tip, with the axis along +Z.
		'''
		points = [(p.x, p.y, p.z) for p in tool.tessellate(self.toolTessellation)[0]]
		binWidth = 0.5 * min(self.grid.dx, self.grid.dy) if self.grid else 0.05
		self.tool = dexel.RevolvedTool.from_points(points, binWidth)
		self._turning = False
		self._lastPosition = None
		FreeCAD.Console.PrintMessage(
			"[PathSim dexel] tool: radius {:.3f}, length {:.3f}, {}\n".format(
				self.tool.radius, self.tool.top,
				"flat" if self.tool.is_flat else "profiled"))

	def setTurningTool(self, tool):
		if self._spindleAxis is None:
			raise ValueError("Turning requires complete cylinder stock with its spindle parallel to Z")
		if any(abs(value) > 1e-7 for value in self._spindleAxis):
			raise ValueError("Turning currently requires the spindle on X = Y = 0")
		wires = tool.slice(FreeCAD.Vector(0, 1, 0), tool.BoundBox.Center.y)
		if len(wires) != 1 or not wires[0].isClosed():
			raise ValueError("Turning tool must have one closed insert profile in its XZ section")
		deflection = min(self.toolTessellation, min(self.grid.dx, self.grid.dy) / 4)
		points = wires[0].discretize(Deflection=deflection)
		self.tool = dexel.TurningTool([(point.x, point.z) for point in points])
		self._turning = True
		self._lastPosition = None
		FreeCAD.Console.PrintMessage(
			"[PathSim dexel] turning insert: {} profile points, deflection {:.3f}\n".format(
				len(self.tool.profile), deflection))

	def setOperation(self, operationId):
		if not 0 < operationId < 65536:
			raise ValueError("Operation id must be between 1 and 65535")
		self.operationId = operationId
		self._lastPosition = None

	def processPosition(self, placement):
		''' process the new tool position. placement is a freecad placement object'''
		if self.grid is None or self.tool is None or not self.operationId:
			raise RuntimeError("The dexel engine needs a stock, tool and operation before cutting")

		base = placement.Base
		position = (base.x, base.y, base.z)
		start = time.perf_counter()
		if self._turning:
			if abs(base.y) > 1e-7:
				raise ValueError("Turning tool positions must be in the XZ plane")
			position = (base.x, base.z)
			changed = self.grid.cut_turning(
				self.tool, self.operationId, self._lastPosition or position, position,
				axis=self._spindleAxis)
		else:
			changed = self.grid.cut_segment(
				self.tool, self.operationId, self._lastPosition or position, position)
		self._columnsChanged += changed
		self._meshDirty = self._meshDirty or changed > 0
		self._surfaceDirty = self._surfaceDirty or changed > 0
		self._cutTime += time.perf_counter() - start
		self._lastPosition = position
		self._cuts += 1
		self._positions += 1
		if self._positions % 50 == 0:
			self.reportPerformance()

	def getSurface(self):
		'''Return cached triangles and face owners, replacing them after a cut.'''
		if self._surfaceDirty:
			start = time.perf_counter()
			triangles, owners = self.grid.extract()
			self._extractTime += time.perf_counter() - start
			self._surface = (triangles, owners)
			self._surfaceDirty = False
			self._triangles = len(triangles)
			self._surfaceUpdates += 1
		return self._surface

	def getMesh(self):
		'''Return a new mesh only when the material or its ownership has changed.'''
		if not self._meshDirty:
			return self._mesh
		triangles, faceOperationIds = self.getSurface()
		extracted = time.perf_counter()
		mesh = Mesh.Mesh(triangles)
		finished = time.perf_counter()
		self._mesh = mesh
		self.faceOperationIds = faceOperationIds
		self._meshDirty = False
		self._meshTime += finished - extracted
		self._meshUpdates += 1
		self._triangles = len(triangles)
		return mesh

	def reportPerformance(self):
		''' report averages since the previous report, excluding playback delay '''
		if not self._cuts and not self._meshUpdates and not self._surfaceUpdates:
			return

		def average(total, count):
			return "{:.3f}".format(total * 1000 / count) if count else "n/a"

		FreeCAD.Console.PrintMessage(
			"[PathSim dexel] positions={} cuts={} cut_avg_ms={} columns_changed={} "
			"surface_updates={} mesh_updates={} triangles={} extract_avg_ms={} mesh_build_avg_ms={}\n".format(
				self._positions, self._cuts, average(self._cutTime, self._cuts),
				self._columnsChanged, self._surfaceUpdates, self._meshUpdates, self._triangles,
				average(self._extractTime, self._surfaceUpdates),
				average(self._meshTime, self._meshUpdates)))
		self._resetWindow()
