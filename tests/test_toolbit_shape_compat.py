import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch
from xml.etree import ElementTree
from zipfile import ZipFile


class ToolBitShapeCompatibilityTests(unittest.TestCase):
    def load_toolbit_module(self, *, factory_api=False):
        path = Path(__file__).resolve().parents[1] / "PathTurnScripts" / "PathTurnToolBit.py"
        spec = importlib.util.spec_from_file_location("test_path_turn_tool_bit", path)
        module = importlib.util.module_from_spec(spec)

        class ToolBitShape:
            name = "Base"
            aliases = ()
            subtypes = ()

            @classmethod
            def schema(cls):
                return {}

            @classmethod
            def get_subclass_by_name(cls, name):
                name = name.lower()
                for subclass in cls.__subclasses__():
                    if (subclass.name.lower() == name
                            or name in subclass.aliases
                            or name in subclass.subtypes):
                        return subclass
                return None

            @classmethod
            def get_expected_shape_parameters(cls):
                return list(cls.schema())

        class ToolBitShapeCustom(ToolBitShape):
            name = "Custom"
            aliases = ()
            subtypes = ()

            @classmethod
            def schema(cls):
                return {
                    "CuttingEdgeHeight": None,
                    "Diameter": None,
                    "Flutes": None,
                    "Length": None,
                    "ShankDiameter": None,
                }

        class ToolBit:
            pass

        path_module = ModuleType("Path")
        path_module.__path__ = []
        tool_module = ModuleType("Path.Tool")
        tool_module.__path__ = []
        bit_module = ModuleType("Path.Tool.Bit")
        bit_module.ToolBit = ToolBit
        shape_module = ModuleType("Path.Tool.shape")
        shape_module.__path__ = []
        models_module = ModuleType("Path.Tool.shape.models")
        models_module.__path__ = []
        base_module = ModuleType("Path.Tool.shape.models.base")
        base_module.ToolBitShape = ToolBitShape
        freecad_module = SimpleNamespace()
        if factory_api:
            bit_module.Factory = object()

        with patch.dict(sys.modules, {
            "FreeCAD": freecad_module,
            "Path": path_module,
            "Path.Tool": tool_module,
            "Path.Tool.Bit": bit_module,
            "Path.Tool.shape": shape_module,
            "Path.Tool.shape.models": models_module,
            "Path.Tool.shape.models.base": base_module,
        }):
            spec.loader.exec_module(module)
        return module, ToolBitShape, ToolBitShapeCustom

    def test_bundled_turning_shapes_resolve_without_milling_schema(self):
        module, base, custom = self.load_toolbit_module()
        shape_dir = Path(__file__).resolve().parents[1] / "Tools" / "Shape"
        for path in sorted(shape_dir.glob("*.fcstd")):
            with self.subTest(shape=path.name), ZipFile(path) as archive:
                document = ElementTree.fromstring(archive.read("Document.xml"))
                label = document.find(
                    './/Object[@name="Body"]//Property[@name="Label"]/String'
                ).get("value")
                shape_class = base.get_subclass_by_name(label)
                self.assertIs(shape_class, module.ToolBitShapeTurningCustom)
                self.assertEqual(shape_class.get_expected_shape_parameters(), [])
                self.assertIsNot(shape_class, custom)

    def test_legacy_turning_shape_labels_are_not_registered(self):
        _, base, _ = self.load_toolbit_module()
        for label in ("Centreline drill", "Grooving tool", "ISO C rhombic 80° insert",
                      "ISO T triangle insert", "Threading", "custom-left"):
            with self.subTest(label=label):
                self.assertIsNone(base.get_subclass_by_name(label))

    def test_turning_shape_registration_also_applies_to_factory_api(self):
        module, base, _ = self.load_toolbit_module(factory_api=True)

        self.assertIs(
            base.get_subclass_by_name("Turn ISO C"),
            module.ToolBitShapeTurningCustom,
        )
