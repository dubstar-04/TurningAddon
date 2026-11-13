import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from PathTurnSimulation.dexel import DexelGrid, RevolvedTool, TurningTool


class Signal:
    def __init__(self, *args):
        self.calls = []
        self.callback = None

    def __set_name__(self, owner, name):
        self.name = name

    def __get__(self, instance, owner):
        if instance is None:
            return self
        return instance.__dict__.setdefault(self.name, Signal())

    def emit(self, *args):
        self.calls.append(args)
        if self.callback is not None:
            self.callback(*args)


class Placement:
    def __init__(self, position, rotation):
        self.Base = position


def load_worker():
    freecad = SimpleNamespace(
        Placement=Placement,
        Vector=lambda x=0, y=0, z=0: SimpleNamespace(x=x, y=y, z=z),
        Rotation=lambda *args: None)
    qt = SimpleNamespace(QtCore=SimpleNamespace(QThread=object, Signal=Signal), QtGui=None)
    path = Path(__file__).resolve().parents[2] / "PathTurnSimulation" / "PathSim.py"
    spec = importlib.util.spec_from_file_location("PathTurnSimulation.seek_worker", path)
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {"FreeCAD": freecad, "PySide": qt}):
        spec.loader.exec_module(module)
    return module


worker = load_worker()


class EngineLoadingTests(unittest.TestCase):
    def test_selected_engine_loads_matching_module(self):
        sim = worker.PathSim()
        engine = object()
        with patch.object(worker.importlib, "import_module",
                          return_value=SimpleNamespace(Engine=lambda: engine)) as load:
            self.assertTrue(sim.setupEngine("turning_profile_engine"))
        load.assert_called_once_with("PathTurnSimulation.engines.turning_profile_engine")
        self.assertIs(sim.engine, engine)

    def test_missing_engine_reports_error_in_dialog(self):
        sim = worker.PathSim()
        dialog = Mock()
        with patch.object(worker.importlib, "import_module",
                          side_effect=ImportError("Missing test dependency")), \
             patch.object(worker, "QtGui", SimpleNamespace(QMessageBox=lambda: dialog)), \
             patch.object(worker.FreeCAD, "Console", SimpleNamespace(PrintError=Mock()), create=True):
            self.assertFalse(sim.setupEngine("unavailable_engine"))
        self.assertIn("Missing test dependency", dialog.setText.call_args.args[0])
        self.assertEqual(sim.cleanup.calls, [()])
        self.assertIsNone(sim.engine)


class Clock:
    def __init__(self):
        self.now = 0.0

    def perf_counter(self):
        return self.now


class Engine:
    cutDuration = 0.05
    meshDuration = 0.4

    def __init__(self, clock):
        self.clock = clock
        self.positions = []
        self.meshes = []
        self.resets = 0
        self.on_position = None
        self.on_mesh = None

    def setStock(self, stock):
        self.resets += 1
        self.positions = []

    def setTool(self, tool):
        pass

    def processPosition(self, placement):
        self.positions.append(placement.Base.x)
        self.clock.now += self.cutDuration
        if self.on_position is not None:
            self.on_position()

    def getMesh(self):
        self.clock.now += self.meshDuration
        self.meshes.append(tuple(self.positions))
        if self.on_mesh is not None:
            self.on_mesh()
        return self.meshes[-1]


class CachedEngine(Engine):
    meshStableWhenUnchanged = True

    def __init__(self, clock):
        super().__init__(clock)
        self.mesh = None
        self.changed = False
        self.faceOperationIds = []

    def setStock(self, stock):
        super().setStock(stock)
        self.mesh = None
        self.changed = False

    def processPosition(self, placement):
        super().processPosition(placement)
        if placement.Base.x in (3, 7):
            self.changed = True

    def getMesh(self):
        if self.mesh is None or self.changed:
            self.mesh = super().getMesh()
            self.faceOperationIds = [len(self.positions)]
            self.changed = False
        return self.mesh


class SeekTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.sim = worker.PathSim()
        self.sim.initialised = True
        self.sim.stepDelay = 0
        self.sim.engine = Engine(self.clock)
        self.sim.operationSpeeds = lambda operation: {}
        shape = SimpleNamespace(isNull=lambda: False, isValid=lambda: True)
        controller = SimpleNamespace(Tool=SimpleNamespace(Shape=shape))
        self.operations = [SimpleNamespace(Name=name, ToolController=controller)
                           for name in ("first", "second")]
        self.sim.operationIds = {"first": 1, "second": 2}
        self.sim.pathPoints = [
            (SimpleNamespace(x=i, y=0, z=0), self.operations[i // 10])
            for i in range(20)]

    def run_worker(self):
        with patch.object(worker, "time", self.clock):
            self.sim.runSimulation()

    def test_initial_stock_comes_from_explicit_selected_job(self):
        stock = Mock()
        selected = SimpleNamespace(Stock=SimpleNamespace(Shape=Mock()))
        selected.Stock.Shape.copy.return_value = stock
        self.sim.job = selected
        self.sim.initialised = False
        self.sim.discretizePath = Mock(return_value=[])
        self.sim.engine.setStock = Mock()
        self.run_worker()
        self.sim.engine.setStock.assert_called_once_with(stock)

    def test_thread_playback_moves_tool_without_removing_material(self):
        for operation in self.operations:
            operation.Proxy = SimpleNamespace(stock_guide_skip_feeds=True)
            operation.MinDiameter = 0
            operation.MaxDiameter = 10
        self.sim.engine.setTurningTool = Mock()
        self.sim.engine.supportsTurningSweeps = True
        self.sim.turningCommandEnds = {10, 20}
        self.sim.running = True
        self.run_worker()
        self.assertTrue(self.sim.updatePos.calls)
        self.assertEqual(self.sim.engine.positions, [])

    def test_distance_steps_cut_and_display_interpolated_positions(self):
        self.sim.pathPoints = [
            (SimpleNamespace(x=x, y=0, z=0), self.operations[0])
            for x in (0, 2, 2.4, 3.8)]
        for expected in (1, 2, 3):
            self.sim.stepForward()
            self.run_worker()
            self.assertAlmostEqual(self.sim.updatePos.calls[-1][0].Base.x, expected)
            self.assertAlmostEqual(self.sim.engine.positions[-1], expected)
            self.assertFalse(self.sim.running)
        self.assertAlmostEqual(self.sim.engine.positions[-2], 2.4)
        self.assertAlmostEqual(self.sim._cutFraction, 0.6 / 1.4)
        self.sim.skipTo(0.25)
        self.run_worker()
        self.assertEqual(self.sim.engine.resets, 1)
        self.assertEqual(self.sim.engine.positions, [0])
        self.assertEqual(self.sim._cutFraction, 0)

    def test_queued_steps_cross_short_segments_and_operation_changes(self):
        self.sim.pathPoints = [
            (SimpleNamespace(x=x, y=0, z=0), self.operations[op])
            for x, op in ((0, 0), (0, 0), (0.4, 0),
                          (50, 1), (50.4, 1), (51.2, 1))]
        self.sim.stepForward()
        self.sim.stepForward()
        self.run_worker()
        self.assertAlmostEqual(self.sim.updatePos.calls[0][0].Base.x, 50.6)
        self.assertAlmostEqual(self.sim.updatePos.calls[-1][0].Base.x, 51.2)
        self.assertEqual(self.sim.idx, len(self.sim.pathPoints))
        self.assertFalse(self.sim.needsWork())

    def test_distance_step_follows_path_around_a_corner(self):
        self.sim.pathPoints = [
            (SimpleNamespace(x=x, y=y, z=0), self.operations[0])
            for x, y in ((0, 0), (0.6, 0), (0.6, 0.8))]
        self.sim.stepForward()
        self.run_worker()
        position = self.sim.updatePos.calls[-1][0].Base
        self.assertAlmostEqual(position.x, 0.6)
        self.assertAlmostEqual(position.y, 0.4)

    def test_distance_step_backward_reconstructs_to_interpolated_position(self):
        self.sim.pathPoints = [
            (SimpleNamespace(x=x, y=0, z=0), self.operations[0])
            for x in (0, 2, 4)]
        self.sim.skipTo(1)
        self.run_worker()
        self.sim.stepBackward()
        self.run_worker()
        self.assertAlmostEqual(self.sim.updatePos.calls[-1][0].Base.x, 3)
        self.assertEqual(self.sim.engine.positions, [0, 2, 3])
        self.assertFalse(self.sim.running)

    def test_distance_step_backward_skips_operation_repositioning(self):
        self.sim.pathPoints = [
            (SimpleNamespace(x=x, y=0, z=0), self.operations[op])
            for x, op in ((0, 0), (2, 0), (50, 1), (52, 1))]
        self.sim.skipTo(1)
        self.run_worker()
        self.sim.stepBackward()
        self.run_worker()
        self.assertAlmostEqual(self.sim.updatePos.calls[-1][0].Base.x, 51)
        self.sim.stepBackward()
        self.run_worker()
        self.assertAlmostEqual(self.sim.updatePos.calls[-1][0].Base.x, 50)
        self.sim.stepBackward()
        self.run_worker()
        self.assertAlmostEqual(self.sim.updatePos.calls[-1][0].Base.x, 1)

    def test_distance_step_backward_clamps_at_path_start(self):
        self.sim.stepBackward()
        self.run_worker()
        self.assertEqual(self.sim.updatePos.calls[-1][0].Base.x, 0)
        self.assertEqual(self.sim.idx, 1)

    def test_backward_step_interrupts_playback_from_the_displayed_position(self):
        self.configure_paced_turning()
        self.sim.pathPoints = [
            (SimpleNamespace(x=x, y=0, z=0), self.operations[0]) for x in (0, 4, 8)]
        self.sim.pathRapid = [False, False, False]
        self.sim.turningCommandEnds = {1, 2, 3}
        self.sim.engine.cutDuration = self.sim.engine.meshDuration = 0
        origin = []

        def step(placement):
            if placement.Base.x >= 2:
                origin.append(placement.Base.x)
                self.sim.updatePos.callback = None
                self.sim.stepBackward()

        self.sim.updatePos.callback = step
        self.sim.running = True
        self.run_worker()
        self.assertAlmostEqual(self.sim.updatePos.calls[-1][0].Base.x, origin[0] - 1)
        self.assertFalse(self.sim.running)

    def test_step_requested_during_reconstruction_runs_after_first_step(self):
        self.sim.pathPoints = [
            (SimpleNamespace(x=x, y=0, z=0), self.operations[0]) for x in (0, 2, 4)]

        def queue_another():
            self.sim.engine.on_position = None
            self.sim.stepForward()

        self.sim.engine.on_position = queue_another
        self.sim.stepForward()
        self.run_worker()
        self.assertAlmostEqual(self.sim.updatePos.calls[-1][0].Base.x, 2)
        self.assertFalse(self.sim.needsWork())

    def test_seeking_to_sample_before_partial_cut_reconstructs_stock(self):
        self.sim.pathPoints = [
            (SimpleNamespace(x=x, y=0, z=0), self.operations[0]) for x in (0, 2, 4)]
        self.sim.stepForward()
        self.run_worker()
        self.assertEqual(self.sim.idx, 1)
        self.sim.skipTo(1 / 3)
        self.run_worker()
        self.assertEqual(self.sim.engine.resets, 1)
        self.assertEqual(self.sim.engine.positions, [0])
        self.assertEqual(self.sim.updatePos.calls[-1][0].Base.x, 0)

    def test_playback_after_partial_step_cuts_remaining_path(self):
        self.sim.pathPoints = [
            (SimpleNamespace(x=x, y=0, z=0), self.operations[0])
            for x in (0, 2, 4)]
        self.sim.stepForward()
        self.run_worker()
        self.assertEqual(self.sim.engine.positions, [0, 1])
        self.sim.play()
        self.run_worker()
        self.assertEqual(self.sim.engine.positions, [0, 1, 2, 4])
        self.assertEqual(self.sim.idx, 3)
        self.assertEqual(self.sim._cutFraction, 0)

    def test_step_interrupts_playback_from_the_displayed_position(self):
        self.configure_paced_turning()
        self.sim.pathPoints = [
            (SimpleNamespace(x=x, y=0, z=0), self.operations[0]) for x in (0, 4)]
        self.sim.pathRapid = [False, False]
        self.sim.turningCommandEnds = {1, 2}
        self.sim.engine.cutDuration = self.sim.engine.meshDuration = 0
        origin = []

        def step(placement):
            if placement.Base.x >= 0.5:
                origin.append(placement.Base.x)
                self.sim.updatePos.callback = None
                self.sim.stepForward()

        self.sim.updatePos.callback = step
        self.sim.running = True
        self.run_worker()
        self.assertAlmostEqual(self.sim.updatePos.calls[-1][0].Base.x, origin[0] + 1)
        self.assertAlmostEqual(self.sim.engine.positions[-1], origin[0] + 1)
        self.assertFalse(self.sim.running)
        self.assertEqual(self.sim.complete.calls, [])

    def test_forward_seek_only_displays_destination(self):
        self.sim.skipTo(0.8)
        self.run_worker()
        self.assertEqual(self.sim.engine.positions, list(range(16)))
        self.assertEqual(len(self.sim.engine.meshes), 1)
        self.assertEqual({args[0] for args in self.sim.progress.calls}, {0.8})
        self.assertEqual({args[0].Base.x for args in self.sim.updatePos.calls}, {15})
        self.assertTrue(all(args[0] is self.operations[1]
                            for args in self.sim.changedOp.calls))
        self.assertLess(self.clock.now, 1.21)
        self.assertFalse(self.sim.running)

    def test_backward_seek_reconstructs_original_path(self):
        self.sim.idx = 18
        self.sim.skipTo(0.3)
        self.run_worker()
        self.assertEqual(self.sim.engine.resets, 1)
        self.assertEqual(self.sim.engine.positions, list(range(6)))
        self.assertEqual(len(self.sim.engine.meshes), 1)
        self.assertEqual({args[0] for args in self.sim.progress.calls}, {0.3})

    def test_new_seek_supersedes_reconstruction(self):
        def retarget():
            if self.sim.idx == 4:
                self.sim.skipTo(0.1)

        self.sim.engine.on_position = retarget
        self.sim.skipTo(0.8)
        self.run_worker()
        self.assertEqual(self.sim.engine.positions, [0, 1])
        self.assertEqual(len(self.sim.engine.meshes), 1)
        self.assertEqual({args[0] for args in self.sim.progress.calls}, {0.1})

    def test_seek_during_endpoint_meshing_does_not_show_old_position(self):
        def retarget():
            self.sim.engine.on_mesh = None
            self.sim.skipTo(0.2)

        self.sim.engine.on_mesh = retarget
        self.sim.skipTo(0.8)
        self.run_worker()
        self.assertEqual({args[0] for args in self.sim.progress.calls}, {0.2})
        self.assertEqual(self.sim.takeMesh()[0], (0, 1, 2, 3))

    def test_seek_keeps_playing_from_destination(self):
        self.sim.running = True
        self.sim.skipTo(0.6)
        self.run_worker()
        self.assertEqual(self.sim.engine.positions, list(range(20)))
        self.assertEqual(self.sim.progress.calls[0], (0.6,))
        self.assertEqual(self.sim.progress.calls[-1], (1.0,))
        self.assertEqual(len(self.sim.complete.calls), 1)

    def test_stop_interrupts_seek(self):
        def stop():
            if self.sim.idx == 3:
                self.sim.stop()

        self.sim.engine.on_position = stop
        self.sim.skipTo(0.8)
        self.run_worker()
        self.assertEqual(self.sim.idx, 4)
        self.assertFalse(self.sim.needsWork())
        self.assertEqual(self.sim.progress.calls[-1], (0.2,))

    def test_normal_playback_still_displays_intermediate_frames(self):
        self.sim.running = True
        self.run_worker()
        self.assertGreater(len(self.sim.engine.meshes), 1)
        self.assertGreater(len(self.sim.progress.calls), 1)
        self.assertEqual(len(self.sim.complete.calls), 1)

    def test_pause_during_periodic_meshing_retries_paused_stock(self):
        def pause():
            if len(self.sim.engine.meshes) == 2:
                self.sim.engine.on_mesh = None
                self.sim.stop()

        self.sim.meshInterval = 0
        self.sim.engine.on_mesh = pause
        self.sim.running = True
        self.run_worker()
        self.assertEqual(self.sim.idx, 2)
        self.assertEqual(self.sim.engine.positions, [0, 1])
        self.assertEqual(self.sim.engine.meshes, [(0,), (0, 1), (0, 1)])
        self.assertEqual(self.sim.meshesPublished, 2)
        self.assertEqual(self.sim.takeMesh()[0], (0, 1))
        self.assertEqual(self.sim.updatePos.calls[-1][0].Base.x, 1)
        self.assertEqual(self.sim.progress.calls[-1], (0.1,))
        self.assertFalse(self.sim.needsWork())
        self.assertEqual(self.sim.complete.calls, [])

    def configure_paced_turning(self):
        """Set up two long straight passes with deferred cuts and a fake wait."""
        self.clock.now = 1
        for operation in self.operations:
            operation.MinDiameter = 0
            operation.MaxDiameter = 100
        self.sim.engine.supportsTurningSweeps = True
        self.sim.engine.setTurningTool = self.sim.engine.setTool
        self.sim.pathPoints = [
            (SimpleNamespace(x=i, y=0, z=0), self.operations[i // 40])
            for i in range(80)]
        self.sim.pathRapid = [False] * 80
        self.sim.turningCommandEnds = {1, 40, 41, 80}
        self.sim.stepDelay = 0.05
        self.sim.operationSpeeds = lambda operation: {
            "HorizFeed": 20, "VertFeed": 20, "HorizRapid": 40, "VertRapid": 40}

        def wait(duration):
            self.clock.now += duration

        self.sim._wake.wait = wait

    def test_slow_mesh_does_not_fast_forward_turning_playback(self):
        self.configure_paced_turning()
        poses = []
        frames = []
        self.sim.updatePos.callback = lambda placement: poses.append(self.sim.idx)
        self.sim.engine.on_mesh = lambda: frames.append(self.sim.idx)
        self.sim.running = True
        self.run_worker()
        self.assertGreater(len(frames), 4)
        self.assertLessEqual(max(b - a for a, b in zip(poses, poses[1:])), 2)
        self.assertLessEqual(max(b - a for a, b in zip(frames, frames[1:])), 7)
        self.assertEqual(self.sim.idx, 80)
        self.assertIsNone(self.sim._pendingCut)

    def test_fast_turning_playback_preserves_controller_timing(self):
        self.configure_paced_turning()
        self.sim.engine.cutDuration = 0
        self.sim.engine.meshDuration = 0
        self.sim.running = True
        self.run_worker()
        # Two 39 mm feed passes at 20 mm/s; each starts with a locating point.
        self.assertAlmostEqual(self.clock.now - 1, 2 * 39 / 20)
        self.assertEqual(self.sim.idx, 80)
        self.assertEqual(len(self.sim.complete.calls), 1)

    def test_animation_interpolates_without_extra_cuts_or_future_stock(self):
        self.configure_paced_turning()
        self.sim.pathPoints = [
            (SimpleNamespace(x=x, y=0, z=0), self.operations[0]) for x in (0, 2)]
        self.sim.pathRapid = [False, False]
        self.sim.turningCommandEnds = {1, 2}
        self.sim.operationSpeeds = lambda operation: {
            "HorizFeed": 2 / 0.24, "VertFeed": 2 / 0.24,
            "HorizRapid": 20, "VertRapid": 20}
        self.sim.engine.cutDuration = self.sim.engine.meshDuration = 0
        samples = []

        def capture(placement):
            samples.append((self.clock.now, placement.Base.x,
                            list(self.sim.engine.positions)))

        self.sim.updatePos.callback = capture
        self.sim.running = True
        self.run_worker()
        intermediate = [(time, x, cuts) for time, x, cuts in samples if 0 < x < 2]
        self.assertGreaterEqual(len(intermediate), 6)
        self.assertTrue(all(cuts == [0] for _, _, cuts in intermediate))
        self.assertTrue(all(b[1] > a[1] for a, b in zip(intermediate, intermediate[1:])))
        self.assertAlmostEqual(self.clock.now - 1, 0.24)
        self.assertEqual(self.sim.engine.positions, [0, 2])
        self.assertEqual(self.sim.updatePos.calls[-1][0].Base.x, 2)

    def test_pause_resume_preserves_partial_move_and_remaining_duration(self):
        self.configure_paced_turning()
        self.sim.pathPoints = [
            (SimpleNamespace(x=x, y=0, z=0), self.operations[0]) for x in (0, 2)]
        self.sim.pathRapid = [False, False]
        self.sim.turningCommandEnds = {1, 2}
        self.sim.operationSpeeds = lambda operation: {
            "HorizFeed": 2, "VertFeed": 2, "HorizRapid": 20, "VertRapid": 20}
        self.sim.engine.cutDuration = self.sim.engine.meshDuration = 0

        def pause(placement):
            if placement.Base.x >= 0.5:
                self.sim.updatePos.callback = None
                self.sim.stop()

        self.sim.updatePos.callback = pause
        self.sim.running = True
        self.run_worker()
        paused = self.sim.updatePos.calls[-1][0].Base.x
        self.assertGreaterEqual(paused, 0.5)
        self.assertLess(paused, 2)
        self.assertEqual(self.sim.idx, 1)
        self.assertEqual(self.sim.engine.positions, [0])
        self.assertAlmostEqual(self.sim.progress.calls[-1][0], (1 + paused / 2) / 2)
        paused_at = self.clock.now
        self.clock.now += 10
        self.sim.running = True
        self.run_worker()
        self.assertAlmostEqual(self.clock.now - paused_at - 10, 1 - paused / 2)
        self.assertEqual(self.sim.engine.positions, [0, 2])
        self.assertEqual(self.sim.idx, 2)

    def test_seek_to_last_completed_sample_discards_paused_interpolation(self):
        self.configure_paced_turning()
        self.sim.engine.cutDuration = self.sim.engine.meshDuration = 0

        def pause(placement):
            if placement.Base.x > 0.4:
                self.sim.updatePos.callback = None
                self.sim.stop()

        self.sim.updatePos.callback = pause
        self.sim.running = True
        self.run_worker()
        self.assertGreater(self.sim._motionFraction, 0)
        self.assertEqual(self.sim.idx, 1)
        self.sim.skipTo(1 / len(self.sim.pathPoints))
        self.run_worker()
        self.assertEqual(self.sim._motionFraction, 0)
        self.assertEqual(self.sim.updatePos.calls[-1][0].Base.x, 0)
        self.assertEqual(self.sim.engine.positions, [0])

    def test_rapid_animation_uses_rapid_speed(self):
        self.configure_paced_turning()
        self.sim.pathPoints = [
            (SimpleNamespace(x=x, y=0, z=0), self.operations[0]) for x in (0, 2)]
        self.sim.pathRapid = [False, True]
        self.sim.turningCommandEnds = {1, 2}
        self.sim.operationSpeeds = lambda operation: {
            "HorizFeed": 1, "VertFeed": 1, "HorizRapid": 10, "VertRapid": 10}
        self.sim.engine.cutDuration = self.sim.engine.meshDuration = 0
        self.sim.running = True
        self.run_worker()
        self.assertAlmostEqual(self.clock.now - 1, 0.2)
        self.assertEqual(self.sim.engine.positions, [0, 2])

    def test_seek_during_interpolation_discards_partial_move(self):
        self.configure_paced_turning()
        self.sim.engine.cutDuration = self.sim.engine.meshDuration = 0

        def seek(placement):
            if placement.Base.x > 0.4:
                self.sim.updatePos.callback = None
                self.sim.skipTo(0.1)

        self.sim.updatePos.callback = seek
        self.sim.running = True
        self.run_worker()
        self.assertEqual(self.sim.idx, 80)
        self.assertEqual(self.sim.progress.calls[-1], (1.0,))
        self.assertEqual(self.sim.engine.positions[-1], 79)
        self.assertEqual(self.sim._motionFraction, 0)

    def test_paced_animation_matches_unpaced_milling_and_turning_geometry(self):
        class GridEngine(Engine):
            supportsTurningSweeps = True

            def __init__(self, clock, turning):
                super().__init__(clock)
                self.turning = turning
                self.grid = DexelGrid.cylinder(5, 10, 0.5)
                self.tool = (TurningTool([(0, 0), (1, 0), (1, 1), (0, 1)])
                             if turning else RevolvedTool.flat(1, length=2))
                self.previous = None

            def setTurningTool(self, tool):
                self.previous = None

            def setTool(self, tool):
                self.previous = None

            def setOperation(self, operation_id):
                self.operation_id = operation_id
                self.previous = None

            def processPosition(self, placement):
                super().processPosition(placement)
                p = placement.Base
                position = (p.x, p.z) if self.turning else (p.x, p.y, p.z)
                cut = self.grid.cut_turning if self.turning else self.grid.cut_segment
                cut(self.tool, self.operation_id, self.previous or position, position)
                self.previous = position

            def getMesh(self):
                super().getMesh()
                mesh, self.faceOperationIds = self.grid.extract()
                return mesh

        for turning in (False, True):
            results = []
            for paced, stepped in ((False, False), (True, False), (False, True)):
                with self.subTest(turning=turning, paced=paced, stepped=stepped):
                    self.setUp()
                    if turning:
                        self.operations[0].MinDiameter = 0
                        self.operations[0].MaxDiameter = 10
                    self.sim.engine = GridEngine(self.clock, turning)
                    self.sim.engine.cutDuration = self.sim.engine.meshDuration = 0
                    self.sim.pathPoints = [
                        (SimpleNamespace(x=x, y=0, z=z), self.operations[0])
                        for x, z in ((6, 8), (4, 8), (3, 6), (3, 4))]
                    self.sim.pathRapid = [True, True, False, False]
                    self.sim.turningCommandEnds = {1, 2, 3, 4} if turning else set()
                    self.sim.stepDelay = 0.05 if paced else 0
                    self.sim.meshInterval = 1000
                    self.sim.operationSpeeds = lambda operation: {
                        "HorizFeed": 10, "VertFeed": 5,
                        "HorizRapid": 20, "VertRapid": 20}
                    self.sim._wake.wait = lambda seconds: setattr(
                        self.clock, "now", self.clock.now + seconds)
                    if stepped:
                        self.sim.stepForward()
                        self.run_worker()
                        expected = DexelGrid.cylinder(5, 10, 0.5)
                        cut = expected.cut_turning if turning else expected.cut_segment
                        a, b = ((6, 8), (5, 8)) if turning else ((6, 0, 8), (5, 0, 8))
                        cut(self.sim.engine.tool, 1, a, a)
                        cut(self.sim.engine.tool, 1, a, b)
                        self.assertEqual(self.sim.engine.grid.extract(), expected.extract())
                    self.sim.running = True
                    self.run_worker()
                    results.append((self.sim.engine.grid.extract(),
                                    self.sim.engine.grid.volume(),
                                    self.sim.engine.positions))
            self.assertEqual(results[0], results[1])
            self.assertEqual(results[0][:2], results[2][:2])

    def test_stop_during_paced_turning_flushes_only_the_current_position(self):
        self.configure_paced_turning()

        def stop(placement):
            if self.sim.idx >= 8:
                self.sim.updatePos.callback = None
                self.sim.stop()

        self.sim.updatePos.callback = stop
        self.sim.running = True
        self.run_worker()
        self.assertLess(self.sim.idx, 40)
        self.assertEqual(self.sim.engine.positions[-1], self.sim.idx - 1)
        self.assertIsNone(self.sim._pendingCut)
        self.assertFalse(self.sim.needsWork())

    def test_turning_seek_stays_unpaced_with_slow_meshes(self):
        self.configure_paced_turning()
        waits = []
        self.sim._wake.wait = waits.append
        self.sim.skipTo(1)
        self.run_worker()
        self.assertEqual(waits, [])
        self.assertEqual(len(self.sim.engine.positions), 4)
        self.assertEqual(len(self.sim.engine.meshes), 1)
        self.assertAlmostEqual(self.clock.now - 1, 4 * 0.05 + 0.4)
        self.assertEqual(self.sim.idx, 80)

    def test_seek_discards_queued_mesh(self):
        self.sim.publishMesh()
        self.sim.skipTo(0.8)
        self.assertIsNone(self.sim.takeMesh())
        self.run_worker()
        self.assertEqual(self.sim.takeMesh()[0], tuple(range(16)))

    def test_superseded_endpoint_mesh_is_not_published(self):
        def retarget():
            self.sim.engine.on_mesh = None
            self.sim.skipTo(0.9)

        self.sim.engine.on_mesh = retarget
        self.sim.skipTo(0.8)
        self.run_worker()
        self.assertEqual(self.sim.meshesPublished, 1)
        self.assertEqual(self.sim.takeMesh()[0], tuple(range(18)))
        self.assertEqual({args[0] for args in self.sim.progress.calls}, {0.9})

    def test_unchanged_mesh_is_not_republished_after_delivery(self):
        self.sim.engine = CachedEngine(self.clock)
        self.assertTrue(self.sim.publishMesh())
        first = self.sim.takeMesh()
        self.assertTrue(self.sim.publishMesh())
        self.assertIsNone(self.sim.takeMesh())
        self.assertEqual(self.sim.meshesPublished, 1)
        self.assertEqual(len(self.sim.engine.meshes), 1)
        self.assertEqual(first[1], [0])

    def test_seek_republishes_discarded_queued_mesh_without_rebuilding(self):
        self.sim.engine = CachedEngine(self.clock)
        self.assertTrue(self.sim.publishMesh())
        self.sim.skipTo(0.1)
        self.run_worker()
        frame = self.sim.takeMesh()
        self.assertEqual(frame, ((), [0]))
        self.assertEqual(self.sim.meshesPublished, 2)
        self.assertEqual(len(self.sim.engine.meshes), 1)

    def test_seek_to_unchanged_delivered_stock_does_not_republish(self):
        self.sim.engine = CachedEngine(self.clock)
        self.sim.publishMesh()
        self.sim.takeMesh()
        self.sim.skipTo(0.1)
        self.run_worker()
        self.assertIsNone(self.sim.takeMesh())
        self.assertEqual(self.sim.meshesPublished, 1)
        self.assertEqual(len(self.sim.engine.meshes), 1)
        self.assertEqual(self.sim.progress.calls[-1], (0.1,))

    def test_superseded_cached_mesh_is_reused_when_seek_retargets(self):
        self.sim.engine = CachedEngine(self.clock)

        def retarget():
            self.sim.engine.on_mesh = None
            self.sim.skipTo(0.2)

        self.sim.engine.on_mesh = retarget
        self.sim.skipTo(0.2)
        self.run_worker()
        self.assertEqual(len(self.sim.engine.meshes), 1)
        self.assertEqual(self.sim.meshesPublished, 1)
        self.assertEqual(self.sim.takeMesh(), ((0, 1, 2, 3), [4]))

    def test_pending_turning_cut_is_flushed_before_cache_check(self):
        self.sim.engine = CachedEngine(self.clock)
        self.sim.publishMesh()
        self.sim.takeMesh()
        self.sim._pendingCut = Placement(SimpleNamespace(x=3), None)
        self.sim.publishMesh()
        self.assertIsNone(self.sim._pendingCut)
        self.assertEqual(self.sim.takeMesh(), ((3,), [1]))
        self.assertEqual(len(self.sim.engine.meshes), 2)

    def test_backward_seek_rebuilds_stock_even_when_no_cuts_change_it(self):
        self.sim.engine = CachedEngine(self.clock)
        self.sim.skipTo(0.1)
        self.run_worker()
        first = self.sim.takeMesh()
        self.sim.skipTo(0)
        self.run_worker()
        self.assertEqual(self.sim.engine.resets, 1)
        self.assertEqual(len(self.sim.engine.meshes), 2)
        self.assertIsNot(self.sim.takeMesh()[0], first[0])

    def test_legacy_engine_returning_same_object_is_still_published(self):
        mesh = []
        self.sim.engine.getMesh = lambda: mesh
        self.sim.publishMesh()
        self.sim.takeMesh()
        mesh.append("changed")
        self.sim.publishMesh()
        self.assertIs(self.sim.takeMesh()[0], mesh)
        self.assertEqual(self.sim.meshesPublished, 2)

    def test_hidden_stock_cuts_without_meshing_and_refreshes_when_shown(self):
        self.sim.showStock = False
        self.sim.running = True
        self.run_worker()
        self.assertEqual(self.sim.engine.positions, list(range(20)))
        self.assertEqual(self.sim.engine.meshes, [])
        self.assertIsNone(self.sim.takeMesh())
        toolLoads = len(self.sim.toolReady.calls)

        self.sim.setShowStock(True)
        self.assertTrue(self.sim.needsWork())
        self.run_worker()
        self.assertEqual(self.sim.engine.positions, list(range(20)))
        self.assertEqual(self.sim.takeMesh()[0], tuple(range(20)))
        self.assertEqual(len(self.sim.toolReady.calls), toolLoads)
        self.assertFalse(self.sim.needsWork())

    def test_far_side_turning_matches_near_side_including_axis_crossing(self):
        profiles = (
            [(0, 0), (2, 0), (2, 2), (0, 2)],
            [(0, 0), (2, 1), (1, 3)],
            [(-0.2, 0), (1.5, -0.5), (2, 1), (0, 2)],
        )
        moves = (
            ((9, -12), (9, -8)),
            ((9, -12), (8, -8)),
            ((9, -12), (9, -12)),
            ((12, -10), (10, -10)),
            ((-4, -12), (4, -8)),
            ((0, -12), (0, -8)),
        )
        for profile in profiles:
            axis_moves = (((0, -12), (0, -8)), ((-0.00005, -12), (-0.00005, -8)))
            for start, end in moves + (axis_moves if min(x for x, _ in profile) == 0 else ()):
                with self.subTest(profile=profile, start=start, end=end):
                    near = DexelGrid.cylinder(10, 20, 0.5, origin=(0, 0, -20))
                    far = DexelGrid.cylinder(10, 20, 0.5, origin=(0, 0, -20))
                    near_tool = TurningTool(profile)
                    far_tool = TurningTool([(-x, z) for x, z in profile])
                    original = list(far_tool.profile)
                    near_count = near.cut_turning(near_tool, 1, start, end)
                    far_count = far.cut_turning(
                        far_tool, 1, (-start[0], start[1]), (-end[0], end[1]))
                    self.assertEqual(near_count, far_count)
                    for name in ("lo", "hi", "lo_id", "hi_id", "touch", "multi"):
                        self.assertEqual(getattr(near, name), getattr(far, name))
                    self.assertEqual(near.extract(), far.extract())
                    self.assertEqual(far_tool.profile, original)

    def test_turning_seek_matches_original_geometry_and_face_colours(self):
        class TurningEngine(Engine):
            def setStock(self, stock):
                super().setStock(stock)
                self.grid = DexelGrid.cylinder(5, 10, 0.25)
                self.tool = TurningTool([(0, 0), (1, 0), (1, 1), (0, 1)])
                self.previous = None

            def setTurningTool(self, tool):
                self.previous = None

            def setOperation(self, operation_id):
                self.operation_id = operation_id
                self.previous = None

            def processPosition(self, placement):
                super().processPosition(placement)
                position = (placement.Base.x, placement.Base.z)
                self.grid.cut_turning(
                    self.tool, self.operation_id, self.previous or position, position)
                self.previous = position

            def getMesh(self):
                super().getMesh()
                mesh, self.faceOperationIds = self.grid.extract()
                return mesh

        self.sim.engine = TurningEngine(self.clock)
        self.sim.engine.setStock(None)
        for operation in self.operations:
            operation.MinDiameter = 0
            operation.MaxDiameter = 10
        for index, (position, _) in enumerate(self.sim.pathPoints):
            position.x = 3.0 + 0.05 * index
            position.z = 2.0 + 0.2 * index
        self.sim.skipTo(0.8)
        self.run_worker()
        grid = self.sim.engine.grid
        expected_mesh, expected_ids = grid.extract()
        expected_volume = grid.volume()
        self.assertTrue(grid.multi)
        self.assertIn(1, expected_ids)
        self.assertIn(2, expected_ids)

        self.sim.skipTo(0.2)
        self.run_worker()
        self.sim.skipTo(0.8)
        self.run_worker()
        actual_mesh, actual_ids = self.sim.engine.grid.extract()
        self.assertEqual(actual_mesh, expected_mesh)
        self.assertEqual(actual_ids, expected_ids)
        self.assertEqual(self.sim.engine.grid.volume(), expected_volume)

    def assert_tool_error(self, operation, expected):
        with self.assertRaises(worker.ToolSetupError) as context:
            self.sim.loadOperation(operation)
        self.assertIn(expected, str(context.exception))
        self.assertIsNone(self.sim._operation)

    def test_missing_tool_setup_reports_operation(self):
        operation = SimpleNamespace(Name="op", Label="Rough outside", ToolController=None)
        self.assert_tool_error(operation, "Rough outside: no Tool Controller assigned")

        operation.ToolController = SimpleNamespace(Label="TC1", Tool=None)
        self.assert_tool_error(operation, "Tool Controller 'TC1' has no tool assigned")

        empty = SimpleNamespace(isNull=lambda: True, isValid=lambda: False)
        operation.ToolController.Tool = SimpleNamespace(Label="Bit", Shape=empty)
        self.assert_tool_error(operation, "tool 'Bit' has no shape")

    def test_tool_setup_error_stops_playback_with_message(self):
        self.operations[1].Label = "Finish"
        self.operations[1].ToolController = None
        self.sim.running = True
        with patch.object(worker, "time", self.clock), \
                patch.object(worker.FreeCAD, "Console", SimpleNamespace(
                    PrintError=lambda message: None), create=True):
            self.sim.run()
        self.assertEqual(self.sim.engine.positions, list(range(10)))
        self.assertFalse(self.sim.needsWork())
        self.assertFalse(self.sim.initialised)
        self.assertEqual(len(self.sim.failed.calls), 1)
        self.assertIn("Finish: no Tool Controller assigned", self.sim.failed.calls[0][0])

    def configured_speed_operation(self):
        return SimpleNamespace(
            Name="rough", Label="Rough outside", ToolController=SimpleNamespace(
                Label="TC1", HorizFeed=SimpleNamespace(Value=10), VertFeed=2,
                HorizRapid=50, VertRapid=25, SpindleSpeed=1200))

    def test_configured_controller_speeds_are_preserved(self):
        operation = self.configured_speed_operation()
        self.assertEqual(worker.PathSim.operationSpeeds(self.sim, operation), {
            "HorizFeed": 10, "VertFeed": 2, "HorizRapid": 50,
            "VertRapid": 25, "SpindleSpeed": 1200})
        self.assertEqual(self.sim.spindleRPM, 1200)

    def test_feeds_and_spindle_speed_must_be_configured_and_positive(self):
        for name in ("HorizFeed", "VertFeed", "SpindleSpeed"):
            for value in (None, 0, -1, float("nan"), float("inf")):
                with self.subTest(name=name, value=value):
                    operation = self.configured_speed_operation()
                    setattr(operation.ToolController, name, value)
                    with self.assertRaises(worker.ToolSetupError) as context:
                        worker.PathSim.operationSpeeds(self.sim, operation)
                    self.assertIn("TC1", str(context.exception))
                    self.assertIn(name, str(context.exception))
                    self.assertIn("Set ", str(context.exception))
            operation = self.configured_speed_operation()
            delattr(operation.ToolController, name)
            with self.assertRaisesRegex(worker.ToolSetupError, name):
                worker.PathSim.operationSpeeds(self.sim, operation)

    def test_unset_rapids_default_to_1000_mm_per_minute(self):
        for name in ("HorizRapid", "VertRapid"):
            for value in (None, 0, SimpleNamespace(Value=0)):
                with self.subTest(name=name, value=value):
                    operation = self.configured_speed_operation()
                    setattr(operation.ToolController, name, value)
                    speeds = worker.PathSim.operationSpeeds(self.sim, operation)
                    self.assertEqual(speeds[name], 1000 / 60)
                    self.assertEqual(speeds["HorizFeed"], 10)
                    self.assertEqual(speeds["VertFeed"], 2)
                    self.assertEqual(speeds["SpindleSpeed"], 1200)
            operation = self.configured_speed_operation()
            delattr(operation.ToolController, name)
            self.assertEqual(
                worker.PathSim.operationSpeeds(self.sim, operation)[name], 1000 / 60)

        operation = self.configured_speed_operation()
        operation.ToolController.HorizRapid = operation.ToolController.VertRapid = 0
        speeds = worker.PathSim.operationSpeeds(self.sim, operation)
        for end in ((100, 0, 0), (0, 0, 100), (100, 0, 100)):
            self.assertEqual(worker.move_duration(
                (0, 0, 0), end, speeds["HorizRapid"], speeds["VertRapid"], rapid=True), 6)

    def test_invalid_rapids_are_rejected_instead_of_defaulted(self):
        for name in ("HorizRapid", "VertRapid"):
            for value in (-1, float("nan"), float("inf")):
                with self.subTest(name=name, value=value):
                    operation = self.configured_speed_operation()
                    setattr(operation.ToolController, name, value)
                    with self.assertRaisesRegex(worker.ToolSetupError, name):
                        worker.PathSim.operationSpeeds(self.sim, operation)

    def test_missing_speeds_stop_playback_with_actionable_message(self):
        del self.sim.operationSpeeds
        self.operations[0].Label = "Rough outside"
        controller = self.operations[0].ToolController
        controller.Label = "TC1"
        for name in ("HorizFeed", "VertFeed", "HorizRapid", "VertRapid", "SpindleSpeed"):
            setattr(controller, name, 0)
        self.sim.running = True
        with patch.object(worker, "time", self.clock), \
                patch.object(worker.FreeCAD, "Console", SimpleNamespace(
                    PrintError=lambda message: None), create=True):
            self.sim.run()
        self.assertEqual(self.sim.engine.positions, [])
        self.assertFalse(self.sim.needsWork())
        self.assertFalse(self.sim.initialised)
        self.assertEqual(len(self.sim.failed.calls), 1)
        message = self.sim.failed.calls[0][0]
        self.assertEqual(
            message,
            "Rough outside: Set HorizFeed, VertFeed, SpindleSpeed "
            "in Tool Controller 'TC1'.")


if __name__ == "__main__":
    unittest.main()
