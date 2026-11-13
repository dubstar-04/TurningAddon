import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from PathTurnSimulation.dexel import DexelGrid, RevolvedTool, TurningTool


def load_engine():
    console = SimpleNamespace(PrintMessage=lambda message: None,
                              PrintWarning=lambda message: None)
    freecad = SimpleNamespace(Console=console)
    mesh = SimpleNamespace(Mesh=Mock(side_effect=lambda triangles: tuple(triangles)))
    part = SimpleNamespace(Cylinder=type("Cylinder", (), {}),
                           Plane=type("Plane", (), {}))
    path = Path(__file__).resolve().parents[2] / "PathTurnSimulation" / "engines" / "dexel_engine.py"
    spec = importlib.util.spec_from_file_location("PathTurnSimulation.engines.test_dexel_adapter", path)
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {"FreeCAD": freecad, "Mesh": mesh, "Part": part}):
        spec.loader.exec_module(module)
    return module


adapter = load_engine()


def placement(x, y, z):
    return SimpleNamespace(Base=SimpleNamespace(x=x, y=y, z=z))


class MeshCacheTests(unittest.TestCase):
    def setUp(self):
        adapter.Mesh.Mesh.reset_mock(side_effect=True)
        adapter.Mesh.Mesh.side_effect = lambda triangles: object()
        self.engine = adapter.Engine()
        self.engine.grid = DexelGrid((-4, -4, 0, 4, 4, 8), 1)
        self.engine.tool = RevolvedTool.flat(1, length=2)
        self.engine.operationId = 1

    def test_milling_air_moves_reuse_mesh_until_material_changes(self):
        engine = self.engine
        initial = engine.getMesh()
        initial_ids = engine.faceOperationIds
        engine.processPosition(placement(0, 0, 10))
        self.assertIs(engine.getMesh(), initial)
        self.assertIs(engine.faceOperationIds, initial_ids)
        self.assertEqual(adapter.Mesh.Mesh.call_count, 1)

        engine.processPosition(placement(0, 0, 4))
        changed = engine.getMesh()
        self.assertIsNot(changed, initial)
        self.assertIsNot(engine.faceOperationIds, initial_ids)
        self.assertIn(1, engine.faceOperationIds)
        expected_triangles, expected_ids = engine.grid.extract()
        self.assertEqual(adapter.Mesh.Mesh.call_args.args[0], expected_triangles)
        self.assertEqual(engine.faceOperationIds, expected_ids)
        self.assertIs(engine.getMesh(), changed)
        self.assertEqual(adapter.Mesh.Mesh.call_count, 2)

    def test_turning_noop_and_changed_sweeps_invalidate_correctly(self):
        engine = self.engine
        engine.grid = DexelGrid.cylinder(4, 8, 1)
        engine.tool = TurningTool([(0, 0), (1, 0), (1, 1), (0, 1)])
        engine._turning = True
        engine._spindleAxis = (0, 0)
        initial = engine.getMesh()
        engine.processPosition(placement(8, 0, 4))
        self.assertIs(engine.getMesh(), initial)
        engine.processPosition(placement(2, 0, 4))
        changed = engine.getMesh()
        self.assertIsNot(changed, initial)
        self.assertIn(1, engine.faceOperationIds)
        expected_triangles, expected_ids = engine.grid.extract()
        self.assertEqual(adapter.Mesh.Mesh.call_args.args[0], expected_triangles)
        self.assertEqual(engine.faceOperationIds, expected_ids)
        self.assertIs(engine.getMesh(), changed)

    def test_stock_reset_invalidates_cached_mesh(self):
        engine = self.engine
        initial = engine.getMesh()
        box = SimpleNamespace(XLength=8, YLength=8, ZLength=8,
                              XMin=-4, YMin=-4, ZMin=0,
                              XMax=4, YMax=4, ZMax=8)
        stock = SimpleNamespace(BoundBox=box, Solids=[], Faces=[], Volume=512)
        engine.resolution = 1
        engine.setStock(stock)
        self.assertIsNot(engine.getMesh(), initial)
        self.assertEqual(adapter.Mesh.Mesh.call_count, 2)

    def test_surface_cache_preserves_triangles_and_owners_without_mesh_build(self):
        engine = self.engine
        first = engine.getSurface()
        self.assertIs(engine.getSurface(), first)
        self.assertEqual(adapter.Mesh.Mesh.call_count, 0)
        engine.processPosition(placement(0, 0, 10))
        self.assertIs(engine.getSurface(), first)
        engine.processPosition(placement(0, 0, 4))
        second = engine.getSurface()
        self.assertIsNot(second, first)
        self.assertEqual(second, engine.grid.extract())
        self.assertIn(1, second[1])
        self.assertIs(engine.getSurface(), second)
        self.assertEqual(adapter.Mesh.Mesh.call_count, 0)
        engine.getMesh()
        self.assertEqual(adapter.Mesh.Mesh.call_args.args[0], second[0])

    def test_failed_mesh_build_retries_without_publishing_new_face_ids(self):
        engine = self.engine
        initial = engine.getMesh()
        initial_ids = engine.faceOperationIds
        engine.processPosition(placement(0, 0, 4))
        adapter.Mesh.Mesh.side_effect = [RuntimeError("mesh failed"), object()]
        with self.assertRaisesRegex(RuntimeError, "mesh failed"):
            engine.getMesh()
        self.assertIs(engine._mesh, initial)
        self.assertIs(engine.faceOperationIds, initial_ids)
        retried = engine.getMesh()
        self.assertIsNot(retried, initial)
        self.assertIn(1, engine.faceOperationIds)
        self.assertIs(engine.getMesh(), retried)


if __name__ == "__main__":
    unittest.main()
