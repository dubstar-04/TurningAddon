from collections import Counter
import importlib
import io
import math
import struct
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np


class MockMesh:
    def __init__(self):
        self.CountFacets = 0

    def read(self, stream, format):
        assert isinstance(stream, io.BytesIO) and format == "STL"
        self.data = stream.read()
        self.CountFacets = struct.unpack_from("<I", self.data, 80)[0]


def volume(triangles):
    a, b, c = triangles[:, 0:3], triangles[:, 3:6], triangles[:, 6:9]
    return np.einsum("ij,ij->i", a, np.cross(b, c)).sum() / 6


def unmatched_edges(triangles):
    edges = Counter()
    for triangle in np.round(triangles.reshape(-1, 3, 3), 9):
        for i in range(3):
            edges[tuple(triangle[i]), tuple(triangle[(i + 1) % 3])] += 1
    return sum(1 for (a, b), count in edges.items() if edges[b, a] != count)


class TurningProfileEngineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        console = SimpleNamespace(PrintMessage=lambda message: None)
        modules = {"FreeCAD": SimpleNamespace(Console=console),
                   "Mesh": SimpleNamespace(Mesh=MockMesh),
                   "Part": SimpleNamespace(Cylinder=type("Cylinder", (), {}),
                                           Plane=type("Plane", (), {}))}
        sys.modules.pop("PathTurnSimulation.engines.turning_profile_engine", None)
        with patch.dict(sys.modules, modules):
            cls.module = importlib.import_module("PathTurnSimulation.engines.turning_profile_engine")

    @classmethod
    def tearDownClass(cls):
        sys.modules.pop("PathTurnSimulation.engines.turning_profile_engine", None)

    def setUp(self):
        self.engine = self.module.Engine()
        self.engine.setCylinder(10, 0, 20)
        self.engine.setProfile([(0, 0), (2, 0), (2, 1), (0, 1)])
        n = self.engine.segments
        # volume of a revolved profile with an n-sided polygon section
        self.polygon = n / (2 * math.pi) * math.sin(2 * math.pi / n)

    def cut(self, operation, start, end):
        self.engine.setOperation(operation)
        return self.engine.cut(start, end)

    def test_turning_drilling_and_boring_give_closed_exact_volume(self):
        self.assertGreater(self.cut(1, (8, 25), (8, 10)), 0)   # outside diameter to r = 8 above z = 10
        self.assertGreater(self.cut(2, (-1, 25), (-1, 18)), 0)  # across the axis: r < 1 above z = 18
        self.assertGreater(self.cut(3, (4, 25), (4, 15)), 0)   # 4 < r < 6 above z = 15
        self.assertEqual(self.engine.intervals(int(16 / self.engine.dz)), [(0.0, 4.0), (6.0, 8.0)])

        triangles, owners = self.engine.extractSurface()
        expected = math.pi * (100 * 10 + 64 * 10 - 1 * 2 - (36 - 16) * 5)
        # shoulders are drawn across one slice, giving about pi * dr^2 * dz / 6 per shoulder
        self.assertAlmostEqual(volume(triangles), expected * self.polygon, delta=0.05)
        self.assertEqual(unmatched_edges(triangles), 0)
        self.assertEqual(sorted(set(owners.tolist())), [0, 1, 2, 3])
        self.assertEqual(len(owners), len(triangles))

    def test_unchanged_stock_keeps_mesh_and_new_cut_replaces_it(self):
        mesh = self.engine.getMesh()
        self.assertEqual(mesh.CountFacets, len(self.engine.faceOperationIds))
        self.engine.setOperation(1)
        self.engine.processPosition(SimpleNamespace(Base=SimpleNamespace(x=12, y=0, z=25)))
        self.engine.processPosition(SimpleNamespace(Base=SimpleNamespace(x=12, y=0, z=0)))
        self.assertIs(self.engine.getMesh(), mesh)
        self.engine.processPosition(SimpleNamespace(Base=SimpleNamespace(x=9, y=0, z=0)))
        self.assertIsNot(self.engine.getMesh(), mesh)

    def test_stream_contains_float32_facets_and_handles_empty(self):
        triangles = np.array([[0, 1, 2, 3, 4, 5, 6, 7, 8]], dtype=np.float64)
        mesh = self.module._buildMesh(triangles)
        self.assertEqual(mesh.CountFacets, 1)
        self.assertEqual(len(mesh.data), 134)
        self.assertEqual(struct.unpack_from("<9f", mesh.data, 96), tuple(triangles[0]))
        self.assertEqual(self.module._buildMesh(np.empty((0, 9))).CountFacets, 0)

    def test_invalid_streams_and_failed_import_are_explicit(self):
        with self.assertRaises(ValueError):
            self.module._buildMesh(np.array([[np.nan] * 9]))
        with self.assertRaises(ValueError):
            self.module._buildMesh(np.zeros((1, 3)))
        with self.assertRaises(FloatingPointError):
            self.module._buildMesh(np.full((1, 9), 1e300))
        with patch.object(MockMesh, "read"):
            with self.assertRaisesRegex(RuntimeError, "preserve"):
                self.module._buildMesh(np.zeros((1, 9)))


if __name__ == "__main__":
    unittest.main()
