import importlib.util
import math
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from liblathe.base.boundbox import BoundBox
from liblathe.base.point import Point
from liblathe.base.segment import Segment
from liblathe.op.base import Direction, MachiningMode
from liblathe.tool.tool import Tool


class ChamferOperationTests(unittest.TestCase):
    def setUp(self):
        class ObjectOp:
            uses_pass_offset = True
            supports_direction_control = False

            def getProps(self, obj):
                return {
                    "mode": MachiningMode(obj.Mode),
                    "hfeed": 100,
                    "vfeed": 50,
                    "clearance": 3,
                    "pass_offset": obj.PassOffset.Value,
                }

            def opOnDocumentRestored(self, obj):
                pass

            def opFeatures(self, obj):
                return 0

            def setEditorModes(self, obj, features):
                pass

            @staticmethod
            def _addEnumeration(obj, name, enum, default, tooltip):
                values = [member.value for member in enum]
                if not hasattr(obj, name):
                    obj.addProperty("App::PropertyEnumeration", name, "Turn Path", tooltip)
                current = getattr(obj, name, default.value)
                obj.enums[name] = values
                setattr(obj, name, current if current in values else default.value)

        path_module = ModuleType("Path")
        path_module.__path__ = []
        path_module.Command = lambda name, params: SimpleNamespace(Name=name, Parameters=params)
        path_module.Op = ModuleType("Path.Op")
        path_module.Op.__path__ = []
        path_module.Op.Base = ModuleType("Path.Op.Base")
        self.helpers = SimpleNamespace(
            getContainment=self.get_containment,
            getStock=Mock(return_value=BoundBox(Point(0, -20), Point(12, 0))))
        toolbit = ModuleType("PathTurnScripts.PathTurnToolBit")
        toolbit.post_from_parameters = lambda parameters: parameters.get("ToolPost") or "Front"
        self.modules = {
            "FreeCAD": SimpleNamespace(Qt=SimpleNamespace(translate=lambda context, text: text)),
            "Path": path_module,
            "Path.Op": path_module.Op,
            "Path.Op.Base": path_module.Op.Base,
            "PathTurnScripts.PathTurnBase": SimpleNamespace(ObjectOp=ObjectOp),
            "PathTurnScripts.PathTurnAddonHelpers": self.helpers,
            "PathTurnScripts.PathTurnToolBit": toolbit,
        }
        path = Path(__file__).resolve().parents[1] / "PathTurnScripts/PathTurnChamfer.py"
        spec = importlib.util.spec_from_file_location("PathTurnScripts.test_chamfer", path)
        self.module = importlib.util.module_from_spec(spec)
        self.module_patch = patch.dict(sys.modules, self.modules)
        self.module_patch.start()
        self.addCleanup(self.module_patch.stop)
        spec.loader.exec_module(self.module)
        vertices = [(0, 0), (10, 0), (10, -20), (0, -20)]
        self.outline = [Segment(Point(*start), Point(*end))
                        for start, end in zip(vertices, vertices[1:])]

    def get_containment(self, obj):
        custom = getattr(getattr(obj, "Proxy", None), "getContainment", None)
        if custom is not None:
            return custom(obj)
        return BoundBox(
            Point(obj.MinDiameter.Value / 2, obj.FinalDepth.Value),
            Point(obj.MaxDiameter.Value / 2, obj.StartDepth.Value))

    def operation_object(self, *, mode="External", side="-Z"):
        return SimpleNamespace(
            ChamferSize=SimpleNamespace(Value=1),
            PassOffset=SimpleNamespace(Value=1),
            Mode=mode,
            ChamferSide=side,
            MinDiameter=SimpleNamespace(Value=0),
            MaxDiameter=SimpleNamespace(Value=20),
            StartDepth=SimpleNamespace(Value=0),
            FinalDepth=SimpleNamespace(Value=-20),
            ToolController=SimpleNamespace(Tool=SimpleNamespace(ToolPost="Front")),
        )

    def tool(self, internal=False):
        tool = Tool()
        vertices = ([(-2, 0), (0, 0), (0, 2), (-2, 2), (-2, 0)] if internal else
                    [(0, 0), (2, 0), (2, 2), (0, 2), (0, 0)])
        tool.set_tool_from_segments([
            Segment(Point(*start), Point(*end)) for start, end in zip(vertices, vertices[1:])])
        return tool

    def test_containment_corner_selects_each_mode_and_axial_side(self):
        cases = (
            ("External", "-Z", self.outline, 1),
            ("External", "+Z", self.outline, 2),
            ("Internal", "-Z", [
                Segment(Point(5, 0), Point(5, -20)),
                Segment(Point(5, -20), Point(0, -20)),
            ], 0),
            ("Internal", "+Z", [
                Segment(Point(5, 0), Point(5, -20)),
                Segment(Point(5, -20), Point(0, -20)),
            ], 1),
        )
        for mode, side, outline, expected in cases:
            with self.subTest(mode=mode, side=side):
                obj = self.operation_object(mode=mode, side=side)
                if mode == "Internal":
                    obj.MinDiameter.Value = 10
                self.assertEqual(
                    self.module.containment_corner_index(obj, outline), expected)

    def test_inactive_containment_limits_follow_chamfer_size(self):
        cases = (
            ("External", "-Z", 9, 10, -1, 0),
            ("External", "+Z", 9, 10, -20, -19),
            ("Internal", "-Z", 5, 6, -1, 0),
            ("Internal", "+Z", 5, 6, -20, -19),
        )
        for mode, side, x_min, x_max, z_min, z_max in cases:
            with self.subTest(mode=mode, side=side):
                obj = self.operation_object(mode=mode, side=side)
                if mode == "Internal":
                    obj.MinDiameter.Value = 10
                bounds = self.module.chamfer_containment(obj)
                self.assertEqual(
                    (bounds.XMin, bounds.XMax, bounds.ZMin, bounds.ZMax),
                    (x_min, x_max, z_min, z_max))

    def test_rear_containment_expands_with_signed_radial_order(self):
        obj = self.operation_object(mode="Internal")
        obj.MinDiameter.Value = 10
        obj.ToolController.Tool.ToolPost = "Rear"
        bounds = self.module.chamfer_containment(obj)
        expanded = self.module.expanded_cutting_containment(
            bounds, self.tool(internal=True), 3, internal=True, rear=True)
        self.assertEqual((bounds.XMin, bounds.XMax), (-6, -5))
        self.assertLess(expanded.XMin, bounds.XMin)
        self.assertEqual(expanded.XMax, 0)

    def test_active_axial_limit_can_move_past_stored_inactive_depth(self):
        for side, start, final in (("-Z", -25, -20), ("+Z", 0, 5)):
            with self.subTest(side=side):
                obj = self.operation_object(side=side)
                obj.StartDepth.Value, obj.FinalDepth.Value = start, final
                self.assertTrue(self.module.ObjectTurnChamfer().checkDepths(obj))

    def test_containment_must_identify_exactly_one_profile_corner(self):
        obj = self.operation_object()
        obj.MaxDiameter.Value = 18
        with self.assertRaisesRegex(ValueError, "active radial and axial limits"):
            self.module.containment_corner_index(obj, self.outline)

    def test_addon_generates_path_without_selected_base_edges(self):
        obj = self.operation_object()
        proxy = self.module.ObjectTurnChamfer()
        proxy.part_outline = self.outline
        proxy.commandlist = []
        proxy.op_generate_gcode(obj, self.tool())
        self.assertTrue(any(command.Name == "G1" for command in proxy.commandlist))

    def test_chamfer_feeds_stay_near_the_corner_with_a_long_grooving_insert(self):
        obj = self.operation_object()
        obj.StartDepth.Value = 10
        obj.PassOffset.Value = 0.25
        vertices = [
            (0, 50), (3, 50), (5, 48), (5, 14), (4, 14),
            (4, 10), (10, 10), (10, 0), (0, 0)]
        proxy = self.module.ObjectTurnChamfer()
        proxy.part_outline = [
            Segment(Point(*start), Point(*end))
            for start, end in zip(vertices, vertices[1:])]
        proxy.commandlist = []
        tool = Tool()
        radius = 0.2
        bulge = math.tan(math.pi / 8)
        tool.set_tool_from_segments([
            Segment(Point(radius, 0), Point(0, radius), bulge),
            Segment(Point(0, radius), Point(0, 2 - radius)),
            Segment(Point(0, 2 - radius), Point(radius, 2), bulge),
            Segment(Point(radius, 2), Point(12, 2)),
            Segment(Point(12, 2), Point(12, 0)),
            Segment(Point(12, 0), Point(radius, 0)),
        ])
        self.helpers.getStock.return_value = BoundBox(Point(0, 0), Point(12, 50))
        proxy.op_generate_gcode(obj, tool)
        previous = None
        feeds = []
        for command in proxy.commandlist:
            if command.Name == "G0" and previous is not None:
                point = command.Parameters
                self.assertLessEqual(point["X"], 15.001)
                self.assertTrue(
                    min(previous["X"], point["X"]) >= 12
                    or min(previous["Z"], point["Z"]) >= 50
                    or max(previous["Z"], point["Z"]) <= 0)
            if command.Name == "G1":
                feeds.extend((previous, command.Parameters))
            if "X" in command.Parameters and "Z" in command.Parameters:
                previous = command.Parameters
        self.assertTrue(feeds)
        for point in feeds:
            self.assertLessEqual(point["X"], 12.001)
            self.assertGreaterEqual(point["X"], 8.9)
            self.assertGreaterEqual(point["Z"], 8.9)
            self.assertLessEqual(point["Z"], 10.001)

    def test_external_and_internal_sides_generate_paths_from_containment(self):
        internal_outline = [
            Segment(Point(5, 0), Point(5, -20)),
            Segment(Point(5, -20), Point(0, -20)),
        ]
        cases = (
            ("External", "-Z", self.outline),
            ("External", "+Z", self.outline),
            ("Internal", "-Z", internal_outline),
            ("Internal", "+Z", internal_outline),
        )
        for mode, side, outline in cases:
            with self.subTest(mode=mode, side=side):
                obj = self.operation_object(mode=mode, side=side)
                if mode == "Internal":
                    obj.MinDiameter.Value = 10
                proxy = self.module.ObjectTurnChamfer()
                proxy.part_outline = outline
                proxy.commandlist = []
                proxy.op_generate_gcode(obj, self.tool(mode == "Internal"))
                self.assertTrue(any(command.Name == "G1" for command in proxy.commandlist))

    def test_chamfer_side_is_sent_as_radial_strategy_and_separate_side(self):
        obj = self.operation_object(side="+Z")
        proxy = self.module.ObjectTurnChamfer()
        proxy.part_outline = self.outline
        proxy.commandlist = []
        captured = {}

        class Chamfer:
            def setParams(self, params):
                captured.update(params)

            def add_containment(self, bounds):
                pass

            def add_stock(self, bounds):
                pass

            def addPartSegments(self, segments):
                pass

            def add_tool(self, tool):
                pass

            def getGCode(self):
                return []

        with patch("liblathe.op.chamfer.ChamferOP", Chamfer):
            proxy.op_generate_gcode(obj, self.tool())
        self.assertEqual(captured["direction"], Direction.RADIAL)
        self.assertEqual(captured["chamfer_side"], Direction.POSITIVE_Z)

    def test_restoring_a_legacy_operation_adds_side_without_overwriting_existing_value(self):
        class LegacyObject:
            def __init__(self):
                self.enums = {}
                self.editor_modes = {}
                self.Direction = "-Z"

            def addProperty(self, prop_type, name, group, tooltip):
                self.enums[name] = []

            def getEnumerationsOfProperty(self, name):
                return self.enums[name]

            def setEditorMode(self, name, mode):
                self.editor_modes[name] = mode

        proxy = self.module.ObjectTurnChamfer()
        obj = LegacyObject()
        proxy.opOnDocumentRestored(obj)
        self.assertEqual(obj.ChamferSide, "-Z")
        self.assertEqual(obj.editor_modes["Direction"], 2)
        obj.ChamferSide = "+Z"
        proxy.opOnDocumentRestored(obj)
        self.assertEqual(obj.ChamferSide, "+Z")

    def test_invalid_pass_offset_clears_existing_operation_path(self):
        log = SimpleNamespace(Level=SimpleNamespace(INFO=1), setLevel=Mock(),
                              thisModule=lambda: "test", track=Mock())
        self.modules["Path"].Log = log
        self.modules["Path.Op.Base"].ObjectOp = object
        scripts = ModuleType("PathScripts")
        scripts.__path__ = []
        scripts.PathUtils = ModuleType("PathScripts.PathUtils")
        qt = SimpleNamespace(QCoreApplication=SimpleNamespace(
            translate=lambda context, text, disambig=None: text))
        extra_modules = {
            "Path.Log": log,
            "PathScripts": scripts,
            "PathScripts.PathUtils": scripts.PathUtils,
            "PySide": SimpleNamespace(QtCore=qt),
        }
        path = Path(__file__).resolve().parents[1] / "PathTurnScripts/PathTurnBase.py"
        spec = importlib.util.spec_from_file_location("test_turn_base", path)
        base = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, extra_modules):
            spec.loader.exec_module(base)
            operation = base.ObjectOp()
            obj = SimpleNamespace(
                MinDiameter=SimpleNamespace(Value=0), MaxDiameter=SimpleNamespace(Value=20),
                StartDepth=SimpleNamespace(Value=5), FinalDepth=SimpleNamespace(Value=-20),
                PassOffset=SimpleNamespace(Value=0), Path=SimpleNamespace(Commands=["stale"]))
            with self.assertRaisesRegex(RuntimeError, "Pass Offset"):
                operation.opExecute(obj)
            self.assertEqual(obj.Path.Commands, [])
