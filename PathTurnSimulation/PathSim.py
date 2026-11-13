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
import threading
import importlib
import traceback

from PySide import QtCore, QtGui

import FreeCAD

from .dexel.motion import sample_turning_path, move_duration


def isTurningOperation(operation):
	return hasattr(operation, "MinDiameter") and hasattr(operation, "MaxDiameter")


class ToolSetupError(RuntimeError):
	pass


def operationToolShape(operation):
	label = getattr(operation, "Label", operation.Name)
	controller = getattr(operation, "ToolController", None)
	if controller is None:
		raise ToolSetupError(
			"{}: no Tool Controller assigned. Edit the operation and select a Tool Controller.".format(label))
	tool = getattr(controller, "Tool", None)
	if tool is None:
		raise ToolSetupError(
			"{}: Tool Controller '{}' has no tool assigned. Edit the controller and select a ToolBit.".format(
				label, controller.Label))
	shape = getattr(tool, "Shape", None)
	if shape is None or shape.isNull():
		raise ToolSetupError(
			"{}: tool '{}' has no shape. Recompute or replace the ToolBit.".format(label, tool.Label))
	if not shape.isValid():
		raise ToolSetupError(
			"{}: tool '{}' has invalid geometry. Repair or replace the ToolBit.".format(label, tool.Label))
	return shape


class PathSim (QtCore.QThread):

	updatePos = QtCore.Signal(FreeCAD.Placement)
	meshReady = QtCore.Signal()
	complete = QtCore.Signal()
	progress = QtCore.Signal(float)
	cleanup = QtCore.Signal()
	changedOp = QtCore.Signal(object)
	toolReady = QtCore.Signal(object)
	failed = QtCore.Signal(str)
	pathReady = QtCore.Signal(object)

	# Legacy benchmark override: 0 runs unpaced; otherwise use controller speeds.
	stepDelay = 0.05
	# minimum seconds between meshes sent to the display
	meshInterval = 0.2
	# minimum seconds between tool position and progress updates sent to the display
	displayInterval = 1 / 30

	def __init__(self):
		QtCore.QThread.__init__(self)
		self.operations = []
		self.job = None
		self.operationIds = {}
		self.pathPoints = []
		self.pathRapid = []
		self.turningCommandEnds = set()
		self._pendingCut = None
		self._motionFraction = 0.0
		self._cutFraction = 0.0  # committed cut may lag the displayed motion fraction
		self._stepRequests = 0
		self._stepBackRequests = 0
		self.stepDistance = 2
		# self.skippedDistance = 0
		self.running = False
		self.idx = 0  # index of current position
		self.engine = None
		self.showStock = True
		self._meshRequested = False
		self.meshesPublished = 0
		self._meshLock = threading.Lock()
		self._latestMesh = None
		self._meshSignalled = False
		self._publishedMesh = None
		self._stateLock = threading.Lock()
		self._wake = threading.Event()
		self._seekTarget = None
		self._seekSerial = 0
		self.initialised = False
		self._stock = None
		self._operation = None
		self._toolShape = None
		self._speeds = None
		self.spindleRPM = 0.0

	def setupEngine(self, engine):
		# from engines import nativeEngine
		print("PathSim: Setup Engine:", engine)
		importstring = "{}.engines.{}".format(__package__, engine)
		self.engine = None

		try:
			# try to load the selected engine
			engineModule = importlib.import_module(importstring)
			eng = engineModule.Engine()
			self.engine = eng
			return True
		except Exception as error:
			self.cleanup.emit()
			FreeCAD.Console.PrintError("PathSim: Cannot load {}: {}\n".format(importstring, error))
			msgBox = QtGui.QMessageBox()
			msgBox.setText("Cannot load {}: {}".format(engine, error))
			msgBox.exec_()
			return False

	def setOperations(self, operations, operationIds=None):
		self.reset()
		self.operations = operations
		self.operationIds = (
			{op.Name: index + 1 for index, op in enumerate(operations)}
			if operationIds is None else dict(operationIds))

	def reset(self):
		self.initialised = False
		self._pendingCut = None
		self._motionFraction = 0.0
		self._cutFraction = 0.0
		self.idx = 0
		self._operation = None
		self._toolShape = None
		self._speeds = None
		self.spindleRPM = 0.0
		with self._stateLock:
			self.running = False
			self._seekTarget = None
			self._stepRequests = 0
			self._stepBackRequests = 0
			self._meshRequested = False

	def play(self):
		with self._stateLock:
			if self.initialised and self.idx >= len(self.pathPoints) and self._seekTarget is None:
				self._seekTarget = 0
			self.running = True
			self._wake.set()

	def stop(self):
		with self._stateLock:
			self.running = False
			self._seekTarget = None
			self._stepRequests = 0
			self._stepBackRequests = 0
			self._seekSerial += 1
			self._wake.set()

	def needsWork(self):
		with self._stateLock:
			return (self.running or self._seekTarget is not None
				or self._stepRequests > 0 or self._stepBackRequests > 0
				or self._meshRequested)

	def setShowStock(self, show):
		''' building stock meshes is skipped while the stock is hidden; material removal
		continues so the stock is up to date when shown again '''
		with self._stateLock:
			self.showStock = show
			if show and self.initialised:
				self._meshRequested = True
				self._wake.set()

	def run(self):
		try:
			self.runSimulation()
		except ToolSetupError as error:
			self.stop()
			self.initialised = False
			FreeCAD.Console.PrintError("PathSim: Simulation stopped: {}\n".format(error))
			self.failed.emit(str(error))
		except Exception:
			self.stop()
			self.initialised = False
			FreeCAD.Console.PrintError("PathSim: Simulation failed:\n" + traceback.format_exc())

	def runSimulation(self):

		if self.engine is None:
			print("engine not set")
			return

		if not self.initialised:
			with self._meshLock:
				self._latestMesh = None
				self._meshSignalled = False
				self._publishedMesh = None
				self.meshesPublished = 0
			job = self.job
			if job is None:
				raise ToolSetupError("Select a CAM job before starting simulation.")
			self._stock = job.Stock.Shape.copy()
			self._pendingCut = None
			self._cutFraction = 0.0
			self.engine.setStock(self._stock)
			self.pathPoints = self.discretizePath()
			self.pathReady.emit(self.getOperationRanges())
			self.initialised = True
		elif self._operation is not None:
			self._speeds = self.operationSpeeds(self._operation)
		rot = FreeCAD.Rotation(FreeCAD.Vector(0, 0, 1), 0)
		meshPending = False
		lastMesh = time.perf_counter()
		self._lastDisplay = -math.inf
		completed = False
		moved = False

		while True:
			with self._stateLock:
				self._wake.clear()
				target = self._seekTarget
				seekSerial = self._seekSerial
				playing = self.running
				meshRequested = self._meshRequested
				self._meshRequested = False
				if target is None and self._stepRequests:
					self._stepRequests -= 1
					target = self._distanceTarget(1.0)
					self._seekTarget = target
				elif target is None and self._stepBackRequests:
					self._stepBackRequests -= 1
					target = self._distanceTargetBackward(1.0)
					self._seekTarget = target

			if meshRequested and target is None and self.publishMesh(seekSerial):
				meshPending = False
				lastMesh = time.perf_counter()

			if target is not None and target < self.idx + self._cutFraction:
				self._pendingCut = None
				self.engine.setStock(self._stock)
				self.idx = 0
				self._motionFraction = 0.0
				self._cutFraction = 0.0
				self._operation = None
				self._toolShape = None
				meshPending = True

			if target is not None and int(target) == self.idx:
				fraction = target - self.idx
				if fraction > self._cutFraction:
					self.flushPendingCut()
					start = self.pathPoints[self.idx - 1][0]
					end = self.pathPoints[self.idx][0]
					self._motionFraction = fraction
					self.processPosition(FreeCAD.Placement(
						self.interpolatedPosition(start, end), rot))
					self._cutFraction = fraction
				self._motionFraction = fraction
				if not self.publishMesh(seekSerial):
					continue
				meshPending = False
				with self._stateLock:
					if self._seekSerial != seekSerial:
						continue
					self._seekTarget = None
				self.showCurrentPosition(rot)
				lastMesh = time.perf_counter()
				continue

			if target is not None:
				self._motionFraction = 0.0

			if not playing and target is None:
				break
			moved = True
			if self.idx >= len(self.pathPoints):
				with self._stateLock:
					if self._seekTarget is not None:
						continue
					self.running = False
				completed = playing
				break

			pntData = self.pathPoints[self.idx]
			pos = pntData[0]
			operation = pntData[1]
			if self._operation is not operation:
				self.loadOperation(operation, notify=target is None)
				self._lastDisplay = -math.inf

			duration = 0.0
			if target is None and self.stepDelay != 0 and self.idx > 0:
				previous, previousOperation = self.pathPoints[self.idx - 1]
				if previousOperation is operation:
					rapid = self.pathRapid[self.idx]
					horizontal, vertical = (
						("HorizRapid", "VertRapid") if rapid else ("HorizFeed", "VertFeed"))
					duration = move_duration(
						(previous.x, previous.y, previous.z), (pos.x, pos.y, pos.z),
						self._speeds[horizontal], self._speeds[vertical],
						rapid=rapid, turning=isTurningOperation(operation))

			if duration and not self.animateMove(previous, pos, duration, rot, seekSerial):
				continue
			with self._stateLock:
				if self._seekSerial != seekSerial:
					continue

			placement = FreeCAD.Placement(pos, rot)
			if (isTurningOperation(operation) and self.turningCommandEnds
					and getattr(self.engine, "supportsTurningSweeps", False)):
				self._pendingCut = placement
				if self.idx + 1 in self.turningCommandEnds:
					self.flushPendingCut()
			else:
				self.processPosition(placement)
			self.idx += 1
			self._motionFraction = 0.0
			self._cutFraction = 0.0
			meshPending = True

			# Reconstruct all cuts without rendering the path to the seek target.
			if target is not None:
				continue
			with self._stateLock:
				if self._seekSerial != seekSerial:
					continue

			meshDue = time.perf_counter() - lastMesh >= self.meshInterval
			self.showPlaybackPosition(pos, rot, self.idx / len(self.pathPoints), force=meshDue)
			if meshDue:
				if self.publishMesh():
					lastMesh = time.perf_counter()
					meshPending = False

		if meshPending:
			self.publishMesh()
		with self._stateLock:
			seeking = self._seekTarget is not None
		if moved and not seeking:
			self.showCurrentPosition(rot)

		reportPerformance = getattr(self.engine, "reportPerformance", None)
		if reportPerformance is not None:
			reportPerformance()

		if completed:
			self.complete.emit()

	def animateMove(self, start, end, duration, rot, seekSerial):
		'''Display a paced move without cutting beyond the displayed position.'''
		startTime = time.perf_counter() - self._motionFraction * duration
		while True:
			with self._stateLock:
				if not self.running or self._seekSerial != seekSerial:
					return False
				self._wake.clear()
				now = time.perf_counter()
				self._motionFraction = min(1.0, max(0.0, (now - startTime) / duration))
			if self._motionFraction >= 1.0:
				return True
			self.showPlaybackPosition(
				self.interpolatedPosition(start, end), rot,
				(self.idx + self._motionFraction) / len(self.pathPoints))
			remaining = max(0.0, startTime + duration - time.perf_counter())
			if remaining <= 1e-9:
				self._motionFraction = 1.0
				return True
			self._wake.wait(min(self.displayInterval, remaining))

	def showPlaybackPosition(self, pos, rot, progress, force=False):
		now = time.perf_counter()
		if force or now - self._lastDisplay >= self.displayInterval:
			self._lastDisplay = now
			self.updateToolPosition(pos, rot)
			self.progress.emit(progress)

	def interpolatedPosition(self, start, end):
		fraction = self._motionFraction
		return FreeCAD.Vector(
			start.x + (end.x - start.x) * fraction,
			start.y + (end.y - start.y) * fraction,
			start.z + (end.z - start.z) * fraction)

	def loadOperation(self, operation, notify=True):
		if self._operation is operation:
			return
		self.flushPendingCut()
		shape = operationToolShape(operation)
		if isTurningOperation(operation):
			setTool = getattr(self.engine, "setTurningTool", None)
			if setTool is None:
				raise ToolSetupError(
					"{}: the selected engine does not support turning. Select dexel_engine "
					"or turning_profile_engine.".format(
						getattr(operation, "Label", operation.Name)))
		else:
			setTool = self.engine.setTool
		try:
			setTool(shape)
		except ValueError as error:
			raise ToolSetupError("{}: cannot load the tool: {}".format(
				getattr(operation, "Label", operation.Name), error)) from error
		setOperation = getattr(self.engine, "setOperation", None)
		if setOperation is not None:
			setOperation(self.operationIds[operation.Name])
		self._operation = operation
		self._toolShape = shape
		self._speeds = self.operationSpeeds(operation)
		if notify:
			self.changedOp.emit(operation)
			self.toolReady.emit(shape)

	def operationSpeeds(self, operation):
		controller = operation.ToolController
		operationLabel = getattr(operation, "Label", operation.Name)
		controllerLabel = getattr(controller, "Label", operationLabel)
		speeds = {}
		invalid = []
		for name in ("HorizFeed", "VertFeed", "HorizRapid", "VertRapid", "SpindleSpeed"):
			value = getattr(controller, name, None)
			value = float(getattr(value, "Value", value)) if value is not None else 0.0
			if value == 0 and name in ("HorizRapid", "VertRapid"):
				value = 1000.0 / 60.0
			if not math.isfinite(value) or value <= 0:
				invalid.append(name)
			speeds[name] = value
		if invalid:
			raise ToolSetupError(
				"{}: Set {} in Tool Controller '{}'.".format(
					operationLabel, ", ".join(invalid), controllerLabel))
		self.spindleRPM = speeds["SpindleSpeed"]
		return speeds

	def showCurrentPosition(self, rot):
		if self.pathPoints:
			pos, operation = self.pathPoints[max(0, self.idx - 1)]
			if self._motionFraction and self.idx < len(self.pathPoints):
				pos = self.interpolatedPosition(pos, self.pathPoints[self.idx][0])
			if self._operation is operation:
				self.changedOp.emit(operation)
				self.toolReady.emit(self._toolShape)
			else:
				self.loadOperation(operation)
			self.updateToolPosition(pos, rot)
			self.progress.emit((self.idx + self._motionFraction) / len(self.pathPoints))
		else:
			self.progress.emit(0)

	def getOperationRanges(self):
		''' timeline ranges use the same sampled positions as playback progress '''
		ranges = []
		count = len(self.pathPoints)
		for index, (_, operation) in enumerate(self.pathPoints):
			operationId = self.operationIds[operation.Name]
			if ranges and ranges[-1][2] == operationId:
				ranges[-1][1] = index + 1
			else:
				ranges.append([index, index + 1, operationId])
		return [(start / count, end / count, operationId)
			for start, end, operationId in ranges]

	def flushPendingCut(self):
		''' apply deferred straight turning motion before changing tools or showing stock '''
		if self._pendingCut is not None:
			self.processPosition(self._pendingCut)
			self._pendingCut = None

	def processPosition(self, placement):
		# Thread passes are display-only until synchronized spindle geometry is supported.
		if not getattr(getattr(self._operation, "Proxy", None), "stock_guide_skip_feeds", False):
			self.engine.processPosition(placement)

	def publishMesh(self, seekSerial=None):
		''' make the engine mesh available to the display, with the operation id of each face if
		the engine tracks it. Only the newest mesh is kept, so a slow display skips meshes
		instead of building up a backlog. Engines must replace faceOperationIds for each mesh,
		not modify it, so the list is safe to hand to the gui thread. Engines that
		set meshStableWhenUnchanged must return the same mesh and face ids until the
		stock changes, and a new mesh when it changes.'''
		with self._stateLock:
			if seekSerial is None:
				if self._seekTarget is not None:
					return False
				seekSerial = self._seekSerial
			elif seekSerial != self._seekSerial:
				return False
		self.flushPendingCut()
		if not self.showStock:
			return True
		mesh = self.engine.getMesh()
		frame = (mesh, getattr(self.engine, "faceOperationIds", None))
		with self._stateLock:
			if seekSerial != self._seekSerial:
				return False
			with self._meshLock:
				if (getattr(self.engine, "meshStableWhenUnchanged", False)
						and mesh is self._publishedMesh):
					return True
				self._latestMesh = frame
				self._publishedMesh = mesh
				self.meshesPublished += 1
				notify = not self._meshSignalled
				self._meshSignalled = True
		if notify:
			self.meshReady.emit()
		return True

	def takeMesh(self):
		''' return the newest (mesh, faceOperationIds) not yet displayed, or None '''
		with self._meshLock:
			frame = self._latestMesh
			self._latestMesh = None
			self._meshSignalled = False
		return frame

	def skipTo(self, progress):
		''' request a reconstructed state; only the worker changes the processed index '''
		if not math.isfinite(progress):
			raise ValueError("Seek progress must be finite")
		with self._stateLock:
			self._seekTarget = int(max(0.0, min(1.0, progress)) * len(self.pathPoints))
			self._stepRequests = 0
			self._stepBackRequests = 0
			self._seekSerial += 1
			with self._meshLock:
				if self._latestMesh is not None:
					self._publishedMesh = None
				self._latestMesh = None
			self._wake.set()

	def stepForward(self):
		''' pause and queue one 1 mm advance along the sampled toolpath '''
		with self._stateLock:
			self.running = False
			self._stepBackRequests = 0
			self._stepRequests += 1
			self._seekSerial += 1
			with self._meshLock:
				if self._latestMesh is not None:
					self._publishedMesh = None
				self._latestMesh = None
			self._wake.set()

	def stepBackward(self):
		''' pause and queue one 1 mm reverse advance along the sampled toolpath '''
		with self._stateLock:
			self.running = False
			self._stepRequests = 0
			self._stepBackRequests += 1
			self._seekSerial += 1
			with self._meshLock:
				if self._latestMesh is not None:
					self._publishedMesh = None
				self._latestMesh = None
			self._wake.set()

	def _distanceTarget(self, distance):
		''' return a fractional sample index after travelling distance along the path '''
		count = len(self.pathPoints)
		if not count:
			return 0
		position = min(float(count), max(1.0, self.idx + self._motionFraction))
		while position < count:
			index = int(position)
			fraction = position - index
			start, startOperation = self.pathPoints[index - 1]
			end, endOperation = self.pathPoints[index]
			if startOperation is not endOperation:
				# Playback locates the new tool without traversing the gap.
				position = float(index + 1)
				continue
			length = math.dist((start.x, start.y, start.z), (end.x, end.y, end.z))
			remaining = length * (1.0 - fraction)
			if remaining > distance + 1e-12:
				return position + distance / length
			distance -= remaining
			position = float(index + 1)
			if distance <= 1e-12:
				break
		return position

	def _distanceTargetBackward(self, distance):
		''' return a fractional sample index after travelling backwards along the path '''
		count = len(self.pathPoints)
		if not count:
			return 0
		position = min(float(count), max(1.0, self.idx + self._motionFraction))
		while position > 1.0:
			index = math.ceil(position) - 1
			fraction = position - index
			start, startOperation = self.pathPoints[index - 1]
			end, endOperation = self.pathPoints[index]
			if startOperation is not endOperation:
				# Playback locates the new tool without traversing the gap.
				position = float(index)
				continue
			length = math.dist((start.x, start.y, start.z), (end.x, end.y, end.z))
			remaining = length * fraction
			if remaining > distance + 1e-12:
				return position - distance / length
			distance -= remaining
			position = float(index)
			if distance <= 1e-12:
				break
		return position

	def updateToolPosition(self, pos, rot):
		self.updatePos.emit(FreeCAD.Placement(pos, rot))

	def discretizePath(self):
		''' split the path in to discrete points'''
		pathPoints = []
		pathRapid = []
		turningCommandEnds = set()
		currentPos = FreeCAD.Vector(0, 0, 0)
		pos = FreeCAD.Vector(0, 0, 0)
		centrePos = FreeCAD.Vector()

		for op in self.operations:
			if isTurningOperation(op):
				samples, commandEnds = sample_turning_path(
					((command.Name, command.Parameters) for command in op.Path.Commands),
					self.stepDistance, (currentPos.x, currentPos.y, currentPos.z))
				offset = len(pathPoints)
				turningCommandEnds.update(offset + end for end in commandEnds)
				pathPoints.extend([FreeCAD.Vector(*point), op] for point, _ in samples)
				pathRapid.extend(rapid for _, rapid in samples)
				if samples:
					currentPos = FreeCAD.Vector(*samples[-1][0])
					pos = FreeCAD.Vector(*samples[-1][0])
				continue
			for command in op.Path.Commands:
				name = command.Name

				centrePos.x = currentPos.x
				centrePos.y = currentPos.y
				centrePos.z = currentPos.z

				if name in ["G0", "G00", "G1", "G01", "G2", "G02","G3", "G03"]:
					parameters = command.Parameters
					for param in parameters:
						if param == 'X':
							pos.x = parameters['X']
						if param == 'Y':
							pos.y = parameters['Y']
						if param == 'Z':
							pos.z = parameters['Z']
						if param == 'I':
							i = parameters['I']  # x offset to centre
							centrePos.x += i
						if param == 'J':
							j = parameters['J']  # y offset to centre
							centrePos.y += j

					if name in ["G2", "G02", "G3", "G03"]:
						radius = round(centrePos.sub(currentPos).Length, 2)

						aX = currentPos.x - centrePos.x
						aY = currentPos.y - centrePos.y
						bX = pos.x - centrePos.x
						bY = pos.y - centrePos.y

						startAng = math.atan2(aY, aX)
						# endAng = math.atan2(bY, bX)
						totalAng = math.atan2(aX * bY - aY * bX, aX * bX + aY * bY)

						if round(totalAng, 2) == 0.0:
							totalAng = math.pi * 2

						if name in ["G2", "G02"]:
							totalAng = -abs(totalAng)

						if name in ["G3", "G03"]:
							totalAng = abs(totalAng)

						arcLen = abs(totalAng) * radius
						segments = math.ceil(arcLen / self.stepDistance)
						stepAng = totalAng / segments
						stepZ = (pos.z - currentPos.z) / segments

						#print("Final Angles: start", startAng, " end: ", endAng, "total: ", totalAng, " segments: ", segments)

						for seg in range(segments):
							angle = startAng + seg * stepAng
							segX = centrePos.x + math.cos(angle) * radius
							segY = centrePos.y + math.sin(angle) * radius
							segZ = currentPos.z + stepZ * seg
							pathPoints.append([FreeCAD.Vector(segX, segY, segZ), op])
							pathRapid.append(False)


						currentPos.x = pos.x
						currentPos.y = pos.y
						currentPos.z = pos.z

						### END OF ARC ###


					if name in ["G0", "G00", "G1", "G01"]:
						distance = currentPos.distanceToPoint(pos)
						# distance = self.calculateDistance(currentPos, pos)
						# print("pos", pos)
						# print("distance", distance, "skippedDistance", self.skippedDistance)

						'''
						if distance < self.stepDistance:
							# update the cutsim
							# dont move the tool
							self.skippedDistance += distance
						'''

						if distance >= self.stepDistance:  # or self.skippedDistance >= self.stepDistance:
							# calculate the position for the stepDistance
							# update the cutsim
							# update the tool position
							normal = pos.sub(currentPos).normalize()
							# print("normal:", normal, "pos", pos)
							_stepDistance = normal * self.stepDistance
							steps = int(distance / self.stepDistance)

							for i in range(steps):
								# print("step ", i, "of", steps, "POS:", pos)
								pos = currentPos.add(_stepDistance)
								pathPoints.append([FreeCAD.Vector(pos.x, pos.y, pos.z), op])
								pathRapid.append(name in ("G0", "G00"))
								currentPos.x = pos.x
								currentPos.y = pos.y
								currentPos.z = pos.z
								#self.skippedDistance = 0
		self.pathRapid = pathRapid
		self.turningCommandEnds = turningCommandEnds
		return pathPoints