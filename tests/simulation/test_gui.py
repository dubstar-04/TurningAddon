import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, call, patch


def load_panel():
    util = SimpleNamespace()
    base = SimpleNamespace(Util=util)
    path = Path(__file__).resolve().parents[2] / "PathTurnSimulation" / "PathSimGui.py"
    spec = importlib.util.spec_from_file_location("PathTurnSimulation.test_sim_gui", path)
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {
        "PySide": SimpleNamespace(QtGui=SimpleNamespace(), QtCore=SimpleNamespace()),
        "FreeCAD": SimpleNamespace(ActiveDocument=Mock()),
        "FreeCADGui": SimpleNamespace(Control=Mock()),
        "Mesh": SimpleNamespace(),
        "Path": SimpleNamespace(Base=base),
        "Path.Base": base,
        "Path.Base.Util": util,
        "PathTurnSimulation.PathSim": SimpleNamespace(),
        "PathTurnSimulation.PathSimTimelineGui": SimpleNamespace(),
    }):
        spec.loader.exec_module(module)
    return module


gui = load_panel()


def load_timeline():
    path = Path(__file__).resolve().parents[2] / "PathTurnSimulation" / "PathSimTimelineGui.py"
    spec = importlib.util.spec_from_file_location("PathTurnSimulation.test_sim_timeline", path)
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {
        "PySide": SimpleNamespace(
            QtGui=SimpleNamespace(QGraphicsObject=object),
            QtCore=SimpleNamespace(QObject=object, Signal=Mock())),
        "FreeCADGui": SimpleNamespace(getMainWindow=Mock()),
    }):
        spec.loader.exec_module(module)
    return module


class OperationSkipTests(unittest.TestCase):
    def setUp(self):
        timeline_class = load_timeline().timeline
        self.timeline = timeline_class.__new__(timeline_class)
        self.timeline.progressBarWidth = 100
        self.timeline.setProgress = Mock()
        self.timeline.skipRequested = Mock()
        self.timeline.operationRanges = [(0, 0.3, None), (0.3, 0.6, None),
                                         (0.6, 1, None)]

    def test_forward_skip_from_last_operation_reaches_end(self):
        for ranges in (self.timeline.operationRanges, [(0, 1, None)]):
            for progress in (ranges[-1][0], 0.9, 1.0):
                with self.subTest(ranges=ranges, progress=progress):
                    self.timeline.operationRanges = ranges
                    self.timeline.progress = progress
                    self.timeline.setProgress.reset_mock()
                    self.timeline.skipRequested.reset_mock()
                    self.timeline.jumpToNextOperation()
                    self.timeline.setProgress.assert_called_once_with(1.0)
                    self.timeline.skipRequested.emit.assert_called_once_with(1.0)

    def test_forward_skip_still_reaches_next_operation_start(self):
        self.timeline.progress = 0.1
        self.timeline.jumpToNextOperation()
        self.timeline.skipRequested.emit.assert_called_once_with(0.3)

    def test_forward_skip_without_operations_does_not_seek(self):
        self.timeline.operationRanges = []
        self.timeline.jumpToNextOperation()
        self.timeline.skipRequested.emit.assert_not_called()


class ToolShutdownTests(unittest.TestCase):
    def setUp(self):
        self.panel = gui.PathSimPanel.__new__(gui.PathSimPanel)
        self.panel._closing = False
        self.panel.tool = None
        self.document = Mock(Objects=[])
        self.panel.document = self.document
        self.document_patch = patch.object(gui.FreeCAD, "ActiveDocument", self.document)
        self.document_patch.start()
        self.addCleanup(self.document_patch.stop)

    def test_queued_tool_callback_after_quit_does_not_recreate_tool(self):
        self.panel.tool = SimpleNamespace(Name="Simulation_Tool", PathSimObject="Tool")
        self.document.Objects.append(self.panel.tool)
        self.panel.meshView = None
        self.panel.timeline = Mock()
        self.panel.sim = Mock()
        queued = []
        shape = object()
        self.panel.sim.wait.side_effect = lambda: queued.append(
            lambda: self.panel.loadTool(shape))
        self.panel.quit()
        self.document.removeObject.assert_called_once_with("Simulation_Tool")
        self.assertIsNone(self.panel.tool)
        for callback in queued:
            callback()
        self.document.addObject.assert_not_called()
        self.assertIsNone(self.panel.tool)

    def test_closing_does_not_modify_existing_tool(self):
        original_shape = object()
        self.panel.tool = SimpleNamespace(Shape=original_shape)
        self.panel._closing = True
        self.panel.loadTool(object())
        self.assertIs(self.panel.tool.Shape, original_shape)
        self.document.assert_not_called()
        self.document.addObject.assert_not_called()

    def test_open_panel_creates_and_updates_tool(self):
        shape = object()
        self.panel.loadTool(shape)
        self.document.addObject.assert_called_once_with("Part::FeaturePython", "Simulation_Tool")
        self.assertIs(self.panel.tool, self.document.addObject.return_value)
        self.assertEqual(self.panel.tool.Label, "Simulation-Tool")
        self.assertEqual(self.panel.tool.PathSimObject, "Tool")
        self.assertEqual(self.panel.tool.ViewObject.Proxy, 0)
        self.assertIs(self.panel.tool.Shape, shape)
        replacement = object()
        self.panel.loadTool(replacement)
        self.document.addObject.assert_called_once()
        self.assertIs(self.panel.tool.Shape, replacement)


class SeekFeedbackTests(unittest.TestCase):
    def setUp(self):
        self.panel = gui.PathSimPanel.__new__(gui.PathSimPanel)
        self.panel.tool = None
        self.panel.meshView = None
        self.panel.operations = [SimpleNamespace(Name="operation")]
        self.panel.getOperations = Mock(return_value=self.panel.operations)
        self.panel.onPathReady = Mock()
        self.panel.form = Mock()
        self.panel.timeline = Mock(progress=0)
        self.panel.timeline.setProgress.side_effect = lambda progress: setattr(
            self.panel.timeline, "progress", progress)
        self.panel.sim = Mock(initialised=False)
        self.panel.sim.isRunning.return_value = False
        self.panel.sim.setupEngine.return_value = True
        self.marker_at_start = []
        self.panel.startWorker = Mock(side_effect=lambda: self.marker_at_start.append(
            self.panel.timeline.progress))
        self.panel.document = Mock(Objects=[])
        self.panel.document.findObjects.return_value = [Mock()]
        self.panel.job = self.panel.document.findObjects.return_value[0]
        self.document_patch = patch.object(gui.FreeCAD, "ActiveDocument", self.panel.document)
        self.document_patch.start()
        self.addCleanup(self.document_patch.stop)
        mesh_patch = patch.object(gui.Mesh, "Mesh", Mock(), create=True)
        mesh_patch.start()
        self.addCleanup(mesh_patch.stop)

    def assert_first_seek_feedback(self, progress):
        self.panel.timeline.progress = progress
        self.panel.simSeek(progress)
        self.panel.sim.setupEngine.assert_called_once()
        self.panel.sim.skipTo.assert_called_once_with(progress)
        self.assertEqual(
            [call.args[0] for call in self.panel.timeline.setProgress.call_args_list],
            [0, progress])
        self.assertEqual(self.marker_at_start, [progress])

    def test_first_seek_restores_marker_before_starting_reconstruction(self):
        self.assert_first_seek_feedback(0.6)

    def test_first_jump_to_end_restores_marker_before_starting_reconstruction(self):
        self.assert_first_seek_feedback(1)

    def test_seek_during_playback_updates_marker_without_preparing_or_restarting(self):
        self.panel.sim.isRunning.return_value = True
        self.panel.prepareSimulation = Mock()
        self.panel.simSeek(0.6)
        self.panel.prepareSimulation.assert_not_called()
        self.panel.startWorker.assert_not_called()
        self.panel.sim.skipTo.assert_called_once_with(0.6)
        self.assertEqual(self.panel.timeline.progress, 0.6)

    def test_failed_preparation_does_not_submit_seek(self):
        self.panel.prepareSimulation = Mock(return_value=False)
        self.panel.simSeek(0.6)
        self.panel.sim.skipTo.assert_not_called()
        self.panel.startWorker.assert_not_called()
        self.panel.timeline.setProgress.assert_not_called()

    def test_step_prepares_simulation_and_pauses_playback(self):
        self.panel.prepareSimulation = Mock(return_value=True)
        self.panel.simStepForward()
        self.panel.sim.stepForward.assert_called_once_with()
        self.panel.timeline.setPlaying.assert_called_once_with(False)
        self.panel.startWorker.assert_called_once_with()

    def test_step_during_playback_uses_existing_worker(self):
        self.panel.sim.isRunning.return_value = True
        self.panel.simStepForward()
        self.panel.sim.stepForward.assert_called_once_with()
        self.panel.timeline.setPlaying.assert_called_once_with(False)
        self.panel.startWorker.assert_not_called()

    def test_step_backward_prepares_simulation_and_pauses_playback(self):
        self.panel.prepareSimulation = Mock(return_value=True)
        self.panel.simStepBackward()
        self.panel.sim.stepBackward.assert_called_once_with()
        self.panel.timeline.setPlaying.assert_called_once_with(False)
        self.panel.startWorker.assert_called_once_with()

    def test_step_backward_during_playback_uses_existing_worker(self):
        self.panel.sim.isRunning.return_value = True
        self.panel.simStepBackward()
        self.panel.sim.stepBackward.assert_called_once_with()
        self.panel.timeline.setPlaying.assert_called_once_with(False)
        self.panel.startWorker.assert_not_called()

    def test_turning_only_engine_rejects_mixed_operations_before_display(self):
        self.panel.operations[0].Label = "Pocket"
        self.panel.sim.engine.turningOnly = True
        with patch.object(gui.PathSim, "isTurningOperation", return_value=False, create=True), \
             patch.object(gui.FreeCAD, "Console", SimpleNamespace(PrintError=Mock()), create=True), \
             patch.object(gui.QtGui, "QMessageBox", create=True) as message:
            self.assertFalse(self.panel.prepareSimulation())
        message.warning.assert_called_once()
        self.assertIn("Pocket", message.warning.call_args.args[2])
        self.panel.document.addObject.assert_not_called()

    def test_unavailable_saved_engine_falls_back_to_available_choice(self):
        self.panel.document.findObjects.return_value = []
        self.panel.preferences = Mock()
        self.panel.preferences.GetString.return_value = "removed_engine"
        self.panel.form.comboEngines.findText.return_value = -1
        self.panel.form.comboEngines.currentText.return_value = "dexel_engine"
        console = SimpleNamespace(PrintWarning=Mock())
        with patch.object(gui.os, "listdir", return_value=[
                "dexel_engine.py", "turning_profile_engine.py"]), \
             patch.object(gui.FreeCAD, "Console", console, create=True):
            self.panel.setupUi()
        self.assertEqual(self.panel.form.comboEngines.addItem.call_args_list,
                         [call("dexel_engine"), call("turning_profile_engine")])
        self.panel.form.comboEngines.setCurrentIndex.assert_not_called()
        console.PrintWarning.assert_called_once_with(
            "PathSim: Saved engine 'removed_engine' is unavailable; using 'dexel_engine'.\n")

    def test_selection_is_disabled_during_work(self):
        self.panel.setSelectionEnabled(False)
        for widget in (self.panel.form.comboJobs, self.panel.form.comboEngines,
                       self.panel.form.listOperations):
            widget.setEnabled.assert_called_once_with(False)

    def test_hiding_stock_hides_mesh_and_skips_meshing(self):
        self.panel.preferences = Mock()
        self.panel.meshView = SimpleNamespace(ViewObject=SimpleNamespace(Visibility=True))
        self.panel.sim.needsWork.return_value = False
        self.panel.onStockVisibilityChanged(False)
        self.assertFalse(self.panel.meshView.ViewObject.Visibility)
        self.panel.sim.setShowStock.assert_called_once_with(False)
        self.panel.preferences.SetBool.assert_called_once_with("ShowStock", False)
        self.panel.startWorker.assert_not_called()

    def test_showing_stock_while_paused_starts_worker_to_refresh_mesh(self):
        self.panel.preferences = Mock()
        self.panel.meshView = SimpleNamespace(ViewObject=SimpleNamespace(Visibility=False))
        self.panel.sim.needsWork.return_value = True
        self.panel.onStockVisibilityChanged(True)
        self.assertTrue(self.panel.meshView.ViewObject.Visibility)
        self.panel.sim.setShowStock.assert_called_once_with(True)
        self.panel.startWorker.assert_called_once()


class Document:
    def __init__(self):
        self.Objects = []
        self.removed = []

    def addObject(self, type_id, name):
        existing = {obj.Name for obj in self.Objects}
        base = name
        suffix = 1
        while name in existing:
            name = "{}{:03d}".format(base, suffix)
            suffix += 1
        obj = SimpleNamespace(
            Name=name, Label=name, TypeId=type_id, ViewObject=SimpleNamespace(),
            addProperty=Mock())
        self.Objects.append(obj)
        return obj

    def findObjects(self, type_id, pattern):
        return [SimpleNamespace(Stock=SimpleNamespace(
            Shape=SimpleNamespace(tessellate=lambda tolerance: ([], []))))]

    def removeObject(self, name):
        obj = next(obj for obj in self.Objects if obj.Name == name)
        self.Objects.remove(obj)
        self.removed.append(name)


class SimulationObjectTests(unittest.TestCase):
    def setUp(self):
        self.document = Document()
        self.document_patch = patch.object(gui.FreeCAD, "ActiveDocument", self.document)
        self.document_patch.start()
        self.addCleanup(self.document_patch.stop)

    def add_simulation_objects(self):
        stock = self.document.addObject("Mesh::Feature", "Simulation_Cutshape")
        stock.PathSimObject = "Cutshape"
        tool = self.document.addObject("Part::FeaturePython", "Simulation_Tool")
        tool.PathSimObject = "Tool"
        return stock, tool

    def open_panel(self):
        with patch.object(gui.FreeCADGui, "PySideUic", SimpleNamespace(
                loadUi=lambda path: Mock()), create=True), \
                patch.object(gui.FreeCAD, "ParamGet", return_value=Mock(), create=True), \
                patch.object(gui.PathSim, "PathSim", return_value=Mock(), create=True), \
                patch.object(gui.PathSimTimelineGui, "timeline", return_value=Mock(), create=True), \
                patch.object(gui.PathSimPanel, "setupUi"):
            return gui.PathSimPanel()

    def test_opening_removes_only_identifiable_simulation_objects(self):
        legacy_stock = self.document.addObject("Mesh::Feature", "cutshape")
        legacy_tool = self.document.addObject("Part::FeaturePython", "Tool")
        unrelated = self.document.addObject("Part::Feature", "Simulation_Cutshape")
        self.add_simulation_objects()
        self.add_simulation_objects()
        panel = self.open_panel()
        self.assertEqual(self.document.Objects, [legacy_stock, legacy_tool, unrelated])
        self.assertEqual(len(self.document.removed), 4)
        self.assertIsNone(panel.tool)
        self.assertIsNone(panel.meshView)

    def test_preparation_creates_named_marked_stock_and_cleans_stale_objects(self):
        panel = self.open_panel()
        panel.job = Mock()
        self.add_simulation_objects()
        panel.sim.initialised = False
        panel.getOperations = Mock(return_value=[object()])
        panel.updateTimeline = Mock()
        panel.sim.showStock = False
        with patch.object(gui.Mesh, "Mesh", lambda data: data, create=True):
            self.assertTrue(panel.prepareSimulation())
        self.assertFalse(panel.meshView.ViewObject.Visibility)
        self.assertEqual(self.document.Objects, [panel.meshView])
        self.assertEqual(panel.meshView.Name, "Simulation_Cutshape")
        self.assertEqual(panel.meshView.Label, "Simulation-Cutshape")
        self.assertEqual(panel.meshView.PathSimObject, "Cutshape")
        panel.meshView.addProperty.assert_called_once_with(
            "App::PropertyString", "PathSimObject", "PathSim")
        panel.loadTool(object())
        self.assertEqual(panel.tool.Name, "Simulation_Tool")
        self.assertEqual(panel.tool.Label, "Simulation-Tool")
        self.assertEqual(panel.tool.PathSimObject, "Tool")
        panel.quit()
        self.assertEqual(self.document.Objects, [])
        self.assertIsNone(panel.tool)
        self.assertIsNone(panel.meshView)

    def test_closing_cleans_original_document_even_if_references_are_missing(self):
        panel = self.open_panel()
        self.add_simulation_objects()
        other_document = Document()
        other_stock = other_document.addObject("Mesh::Feature", "Simulation_Cutshape")
        other_stock.PathSimObject = "Cutshape"
        with patch.object(gui.FreeCAD, "ActiveDocument", other_document):
            panel.quit()
        self.assertEqual(self.document.Objects, [])
        self.assertEqual(other_document.Objects, [other_stock])
        panel.cleanup()
        self.assertEqual(len(self.document.removed), 2)

    def test_cleanup_tolerates_objects_already_deleted_from_document(self):
        panel = self.open_panel()
        panel.meshView, panel.tool = self.add_simulation_objects()
        self.document.removeObject(panel.meshView.Name)
        self.document.removeObject(panel.tool.Name)
        panel.cleanup()
        self.assertIsNone(panel.meshView)
        self.assertIsNone(panel.tool)
        self.assertEqual(len(self.document.removed), 2)


if __name__ == "__main__":
    unittest.main()
