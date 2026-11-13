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

import os 
import time

from PySide import QtGui, QtCore

import FreeCAD
import FreeCADGui
import Mesh

import Path.Base.Util as PathUtil

from . import PathSim, PathSimTimelineGui

dir = os.path.dirname(__file__)
ui_name = "PathSimGui.ui"
path_to_ui = dir + os.sep + ui_name
path_to_engines = dir + os.sep + "engines"

# Operation ids start at 1; id 0 is untouched stock. Red is reserved for errors.
STOCK_COLOUR = (0.70, 0.72, 0.74)
OPERATION_COLOURS = [
	(0.20, 0.55, 0.90),
	(0.95, 0.75, 0.20),
	(0.35, 0.75, 0.40),
	(0.65, 0.40, 0.85),
	(0.95, 0.55, 0.15),
	(0.20, 0.75, 0.75),
	(0.25, 0.30, 0.65),
	(0.65, 0.80, 0.25),
]

class PathSimPanel:
	def __init__(self, obj=None):
		# self will create a Qt widget from the ui file
		self.form = FreeCADGui.PySideUic.loadUi(path_to_ui)
		self.preferences = FreeCAD.ParamGet("User parameter:BaseApp/Preferences/Mod/PathSim")

		self.document = FreeCAD.ActiveDocument
		self.tool = None
		self.sim = PathSim.PathSim()
		self.jobs = []
		self.meshView = None
		self.colourWarned = False
		self.meshesShown = 0
		self._resetMeshTiming()
		self.counter = 0
		self._closing = False
		self.cleanup()

		self.timeline = PathSimTimelineGui.timeline()
		showStock = self.preferences.GetBool("ShowStock", True)
		self.sim.showStock = showStock
		self.timeline.setStockVisible(showStock)

		# connect ui components
		self.form.comboJobs.currentIndexChanged.connect(self.onJobChange)
		self.form.listOperations.itemChanged.connect(self.updateTimeline)
		self.sim.updatePos.connect(self.setPos)
		self.sim.complete.connect(self.simComplete)
		self.sim.meshReady.connect(self.onMeshReady)
		self.sim.progress.connect(self.timeline.setProgress)
		self.sim.cleanup.connect(self.cleanup)
		self.sim.toolReady.connect(self.loadTool)
		self.sim.failed.connect(self.onSimulationFailed)
		self.sim.pathReady.connect(self.onPathReady)
		self.sim.finished.connect(self.onWorkerFinished)

		#self.timeline.quitSignal.connect(self.simStop)
		self.timeline.playSignal.connect(self.simPlay)
		self.timeline.stopSignal.connect(self.simStop)
		self.timeline.skipRequested.connect(self.simSeek)
		self.timeline.stepBackwardRequested.connect(self.simStepBackward)
		self.timeline.stepForwardRequested.connect(self.simStepForward)
		self.timeline.stockVisibilityChanged.connect(self.onStockVisibilityChanged)

		self.setupUi()
		self.form.comboEngines.currentTextChanged.connect(self.onEngineChange)

	def setupUi(self):
		jobList = self.document.findObjects("Path::FeaturePython", "Job.*")
		self.form.comboJobs.clear()
		self.jobs = []

		for j in jobList:
			self.jobs.append(j)
			self.form.comboJobs.addItem(j.ViewObject.Icon, j.Label)

		#show the timeline widget
		self.timeline.show()

		self.form.comboEngines.clear()
		engines = os.listdir(path_to_engines)
		for filename in engines:
			engine_str = "_engine.py"
			if filename.endswith(engine_str):
				engineName = filename.replace(".py", "")
				self.form.comboEngines.addItem(engineName)

		savedEngine = self.preferences.GetString("LastEngine", "")
		if savedEngine:
			index = self.form.comboEngines.findText(savedEngine)
			if index >= 0:
				self.form.comboEngines.setCurrentIndex(index)
			else:
				FreeCAD.Console.PrintWarning(
					"PathSim: Saved engine '{}' is unavailable; using '{}'.\n".format(
						savedEngine, self.form.comboEngines.currentText()))

	def onEngineChange(self, engine):
		if engine:
			self.preferences.SetString("LastEngine", engine)
			if not self.sim.isRunning():
				self.sim.reset()
				self.timeline.setPlaying(False)
				self.timeline.setProgress(0)

	def onStockVisibilityChanged(self, visible):
		''' hiding the stock shows only the tool motion and skips building stock meshes '''
		self.preferences.SetBool("ShowStock", visible)
		if self.meshView is not None:
			self.meshView.ViewObject.Visibility = visible
		self.sim.setShowStock(visible)
		if visible and self.sim.needsWork() and not self.sim.isRunning():
			self.startWorker()

	def reject(self):
		self.quit()

	def accept(self):
		FreeCAD.Console.PrintMessage("\nAccept Signal")
		self.quit()

	def clicked(self, button):
		if button == QtGui.QDialogButtonBox.Apply:
			FreeCAD.Console.PrintMessage("\nApply Signal")

	def quit(self):
		self._closing = True
		self.simStop()
		self.sim.wait()
		self.timeline.quit()
		self.cleanup()
		FreeCADGui.Control.closeDialog()
		
	def getStandardButtons(self):
		return QtGui.QDialogButtonBox.Ok | QtGui.QDialogButtonBox.Cancel

	def onJobChange(self):
		j = self.jobs[self.form.comboJobs.currentIndex()]
		self.job = j
		self.sim.job = j
		self.form.listOperations.clear()
		self.operations = []
		for op in j.Operations.OutList:
			if PathUtil.opProperty(op, 'Active'):
				colour = OPERATION_COLOURS[len(self.operations) % len(OPERATION_COLOURS)]
				swatch = QtGui.QPixmap(16, 16)
				swatch.fill(QtGui.QColor.fromRgbF(*colour))
				listItem = QtGui.QListWidgetItem(QtGui.QIcon(swatch), op.Label)
				listItem.setFlags(listItem.flags() | QtCore.Qt.ItemIsUserCheckable)
				listItem.setCheckState(QtCore.Qt.CheckState.Checked)
				self.operations.append(op)
				self.form.listOperations.addItem(listItem)
		self.updateTimeline()

	def getOperations(self):
		activeOps = []
		for i in range(self.form.listOperations.count()):
			if self.form.listOperations.item(i).checkState() == QtCore.Qt.CheckState.Checked:
				activeOps.append(self.operations[i])

		return activeOps

	def updateTimeline(self):
		if not self.sim.isRunning():
			operationIds = {op.Name: index + 1 for index, op in enumerate(self.operations)}
			self.sim.setOperations(self.getOperations(), operationIds)
			self.sim.pathPoints = self.sim.discretizePath()
			self.onPathReady(self.sim.getOperationRanges())
			self.timeline.setPlaying(False)
			self.timeline.setProgress(0)

	def onPathReady(self, ranges):
		self.timeline.setOperationRanges([
			(start, end, QtGui.QColor.fromRgbF(
				*OPERATION_COLOURS[(operationId - 1) % len(OPERATION_COLOURS)]))
			for start, end, operationId in ranges])

	def simPlay(self):
		if not self.sim.isRunning() and not self.prepareSimulation():
			return
		self.sim.play()
		self.timeline.setPlaying(True)
		if not self.sim.isRunning():
			self.startWorker()

	def simSeek(self, progress):
		if not self.sim.isRunning() and not self.prepareSimulation():
			return
		self.sim.skipTo(progress)
		self.timeline.setProgress(progress)
		if not self.sim.isRunning():
			self.startWorker()

	def simStepForward(self):
		if not self.sim.isRunning() and not self.prepareSimulation():
			return
		self.sim.stepForward()
		self.timeline.setPlaying(False)
		if not self.sim.isRunning():
			self.startWorker()

	def simStepBackward(self):
		if not self.sim.isRunning() and not self.prepareSimulation():
			return
		self.sim.stepBackward()
		self.timeline.setPlaying(False)
		if not self.sim.isRunning():
			self.startWorker()

	def prepareSimulation(self):
		if self.sim.initialised:
			return True
		operations = self.getOperations()
		if len(operations) == 0:
			print("No Operations active in selected job")
			return False
		
		self.cleanup()
		self.updateTimeline()
		self.colourWarned = False
		self.meshesShown = 0
		self._resetMeshTiming()
		if not self.sim.setupEngine(self.form.comboEngines.currentText()):
			return False
		if getattr(self.sim.engine, "turningOnly", False) is True:
			unsupported = [op.Label for op in operations if not PathSim.isTurningOperation(op)]
			if unsupported:
				message = "The {} engine supports turning operations only: {}".format(
					self.form.comboEngines.currentText(), ", ".join(unsupported))
				FreeCAD.Console.PrintError("PathSim: {}\n".format(message))
				QtGui.QMessageBox.warning(self.form, "Engine unavailable", message)
				return False
		omitted = [op.Label for op in operations
			if getattr(getattr(op, "Proxy", None), "stock_guide_skip_feeds", False)]
		if omitted:
			message = "Tool motion only; material removal is not simulated for: {}".format(", ".join(omitted))
			FreeCAD.Console.PrintWarning("PathSim: {}\n".format(message))
			QtGui.QMessageBox.warning(self.form, "Simulation limitations", message)
		self.meshView = self.document.addObject("Mesh::Feature", "Simulation_Cutshape")
		self.meshView.Label = "Simulation-Cutshape"
		self.meshView.addProperty("App::PropertyString", "PathSimObject", "PathSim")
		self.meshView.PathSimObject = "Cutshape"
		job = self.job
		self.meshView.Mesh = Mesh.Mesh(job.Stock.Shape.tessellate(0.1))
		self.meshView.ViewObject.Visibility = self.sim.showStock

		return True

	def startWorker(self):
		self.setSelectionEnabled(False)
		self.sim.start()

	def onWorkerFinished(self):
		if self._closing or self.sim.isRunning():
			return
		self.onMeshReady()
		self.reportMeshTiming()
		self.timeline.setPlaying(self.sim.running)
		if self.sim.needsWork():
			self.startWorker()
		else:
			self.setSelectionEnabled(True)

	def setSelectionEnabled(self, enabled):
		for widget in (self.form.comboJobs, self.form.comboEngines, self.form.listOperations):
			widget.setEnabled(enabled)
	
	def onSimulationFailed(self, message):
		if self._closing:
			return
		self.timeline.setPlaying(False)
		self.cleanupTool()
		QtGui.QMessageBox.warning(self.form, "Path simulation stopped", message)

	def loadTool(self, shape):
		''' display the validated tool shape supplied by the worker '''
		if self._closing:
			return
		if self.tool is None:
			self.tool = self.document.addObject("Part::FeaturePython", "Simulation_Tool")
			self.tool.Label = "Simulation-Tool"
			self.tool.addProperty("App::PropertyString", "PathSimObject", "PathSim")
			self.tool.PathSimObject = "Tool"
			self.tool.ViewObject.Proxy = 0
		self.tool.Shape = shape

	def simStop(self):
		self.sim.stop()
		self.timeline.setPlaying(False)

	def setPos(self, pos):
		# update tool position 
		if self.tool is not None:
			self.tool.Placement = pos

	def cleanup(self):
		self.cleanupStock()
		self.cleanupTool()

	def cleanupTool(self):
		''' Delete the tool created for the simulation '''
		self.cleanupObjects("Tool")
		self.tool = None

	def cleanupStock(self):
		''' Delete the stock created for the simulation '''
		self.cleanupObjects("Cutshape")
		self.meshView = None

	def cleanupObjects(self, kind):
		for obj in list(self.document.Objects):
			if getattr(obj, "PathSimObject", None) == kind:
				self.document.removeObject(obj.Name)

	def simComplete(self):
		''' slot called on simulation completion'''
		self.reportMeshTiming()
		self.cleanupTool()

	def onMeshReady(self):
		''' slot called when the simulation has a new mesh. Only the newest mesh is
		displayed, meshes that arrive while the view is busy are skipped '''
		if self._closing:
			return
		frame = self.sim.takeMesh()
		if frame is not None:
			self.updateMesh(*frame)

	def updateMesh(self, mesh, faceOperationIds=None):
		''' update the meshView '''
		if self.meshView is None:
			return

		start = time.perf_counter()
		self.meshView.Mesh = mesh
		assigned = time.perf_counter()
		self.document.recompute()
		recomputed = time.perf_counter()
		# recompute resets the view's materials, so colours are applied after it
		self.applyFaceColours(mesh, faceOperationIds)
		finished = time.perf_counter()

		self.meshesShown += 1
		self._meshTiming[0] += 1
		self._meshTiming[1] += assigned - start
		self._meshTiming[2] += recomputed - assigned
		self._meshTiming[3] += finished - recomputed
		if self._meshTiming[0] >= 20:
			self.reportMeshTiming()

	def _resetMeshTiming(self):
		self._meshTiming = [0, 0.0, 0.0, 0.0]  # meshes, assign, recompute and colour seconds

	def reportMeshTiming(self):
		''' report display timings since the last report '''
		shown, assign, recompute, colour = self._meshTiming
		if not shown:
			return

		published = self.sim.meshesPublished
		FreeCAD.Console.PrintMessage(
			"[PathSim display] meshes_shown={} meshes_skipped={} assign_avg_ms={:.3f} "
			"recompute_avg_ms={:.3f} colour_avg_ms={:.3f}\n".format(
				self.meshesShown, max(0, published - self.meshesShown),
				assign * 1000 / shown, recompute * 1000 / shown, colour * 1000 / shown))
		self._resetMeshTiming()

	def applyFaceColours(self, mesh, faceOperationIds):
		''' colour each face by the last operation that cut it '''
		if faceOperationIds is None:
			return

		if len(faceOperationIds) != mesh.CountFacets:
			if not self.colourWarned:
				self.colourWarned = True
				FreeCAD.Console.PrintWarning(
					"PathSim: {} operation ids for {} faces, colouring skipped\n".format(
						len(faceOperationIds), mesh.CountFacets))
			return

		if "FaceColors" not in self.meshView.PropertiesList:
			self.meshView.addProperty("App::PropertyColorList", "FaceColors", "PathSim")

		palette = [STOCK_COLOUR] + [
			OPERATION_COLOURS[(operationId - 1) % len(OPERATION_COLOURS)]
			for operationId in range(1, int(max(faceOperationIds, default=0)) + 1)
		]
		self.meshView.FaceColors = [palette[int(operationId)] for operationId in faceOperationIds]

		# the mesh was replaced, so the view needs to apply the colours again
		view = self.meshView.ViewObject
		view.Coloring = False
		view.Coloring = True

def Show():
	panel = PathSimPanel()
	FreeCADGui.Control.showDialog(panel)