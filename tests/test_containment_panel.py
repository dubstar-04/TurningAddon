"""GUI tests for the unified turning containment panel."""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

import FreeCAD
import FreeCADGui
import Part

from PathTurnScripts.PathTurnContainmentGui import TaskPanelContainment


@unittest.skipUnless(FreeCAD.GuiUp, "Requires FreeCAD GUI")
class ContainmentPanelTests(unittest.TestCase):
    def setUp(self):
        self.document = FreeCAD.newDocument("ContainmentPanelTest")
        self.tool = self.document.addObject("App::FeaturePython", "Tool")
        self.tool.addProperty("App::PropertyString", "ToolPost")
        self.tool.ToolPost = "Front"
        controller = self.document.addObject("App::FeaturePython", "Controller")
        controller.addProperty("App::PropertyLink", "Tool")
        controller.Tool = self.tool
        self.operation = self.document.addObject("App::FeaturePython", "Operation")
        self.operation.addProperty("App::PropertyLink", "ToolController")
        self.operation.ToolController = controller
        for name, value in (("MinDiameter", 4), ("MaxDiameter", 16),
                            ("StartDepth", 10), ("FinalDepth", -20)):
            self.operation.addProperty(
                "App::PropertyDistance" if "Depth" in name else "App::PropertyLength", name)
            setattr(self.operation, name, value)
        self.page = TaskPanelContainment(self.operation, 0)
        self.page.initPage(self.operation)

    def tearDown(self):
        self.page.pageCleanup()
        self.page.form.deleteLater()
        FreeCAD.closeDocument(self.document.Name)

    def test_signed_radius_mapping_and_immediate_changes(self):
        for post, values in (("Front", (8, 2)), ("Rear", (-2, -8))):
            with self.subTest(post=post):
                self.tool.ToolPost = post
                self.page.setFields(self.operation)
                self.assertEqual(self.page.form.plusX.property("rawValue"), values[0])
                self.assertEqual(self.page.form.minusX.property("rawValue"), values[1])
        self.page.form.minusX.setProperty("rawValue", -11)
        self.assertEqual(self.operation.MaxDiameter.Value, 22)
        self.assertEqual(self.operation.MinDiameter.Value, 4)
        self.page.form.plusX.setProperty("rawValue", -1)
        self.assertEqual(self.operation.MinDiameter.Value, 2)
        self.page.form.plusZ.setProperty("rawValue", 12)
        self.page.form.minusZ.setProperty("rawValue", -25)
        self.assertEqual(self.operation.StartDepth.Value, 12)
        self.assertEqual(self.operation.FinalDepth.Value, -25)
        self.assertTrue(self.page.isdirty)

    def test_typing_and_step_arrows_update_without_editing_finished(self):
        from PySide import QtGui
        spin = self.page.form.plusX
        self.assertIn(FreeCAD.Units.Quantity(1, FreeCAD.Units.Length).getUserPreferred()[2],
                      spin.text())
        line = spin.findChild(QtGui.QLineEdit)
        line.setText("9 mm")
        self.assertEqual(self.operation.MaxDiameter.Value, 18)
        spin.stepUp()
        self.assertGreater(self.operation.MaxDiameter.Value, 18)
        line.setText("1 cm")
        self.assertEqual(self.operation.MaxDiameter.Value, 20)

    def test_expressions_are_preserved_on_open_and_apply(self):
        self.operation.setExpression("MaxDiameter", "20 mm")
        self.page.setFields(self.operation)
        self.assertEqual(self.page.form.plusX.property("rawValue"), 10)
        self.assertTrue(self.page.form.plusX.isReadOnly())
        self.page.getFields(self.operation)
        self.assertEqual(dict(self.operation.ExpressionEngine)["MaxDiameter"], "20 mm")

    def test_selection_arrows_map_vertices_and_clear_expressions(self):
        selection = [SimpleNamespace(SubObjects=[Part.Vertex(FreeCAD.Vector(3, 4, -7))])]
        self.page.updateSelection(self.operation, selection)
        self.assertTrue(self.page.form.plusXSet.isEnabled())
        self.assertTrue(self.page.form.minusZSet.isEnabled())
        self.operation.setExpression("MaxDiameter", "20 mm")
        with patch.object(FreeCADGui.Selection, "getSelectionEx", return_value=selection):
            self.page.setFromSelection("plusX")
            self.page.setFromSelection("minusZ")
        self.assertNotIn("MaxDiameter", dict(self.operation.ExpressionEngine))
        self.assertEqual(self.operation.MaxDiameter.Value, 10)
        self.assertEqual(self.operation.FinalDepth.Value, -7)

    def test_coordinate_expressions_convert_radius_and_preserve_units(self):
        self.page.setCoordinateExpression("plusX", "12 mm")
        self.assertEqual(self.operation.MaxDiameter.Value, 24)
        self.page.setFields(self.operation)
        self.assertEqual(self.page.form.plusX.property("rawValue"), 12)
        self.tool.ToolPost = "Rear"
        self.page.setFields(self.operation)
        self.page.setCoordinateExpression("minusX", "-13 mm")
        self.assertEqual(self.operation.MaxDiameter.Value, 26)
        self.page.setCoordinateExpression("minusZ", "-2 cm")
        self.assertEqual(self.operation.FinalDepth.Value, -20)
        with self.assertRaises(ValueError):
            self.page.setCoordinateExpression("minusX", "5 mm")
        with self.assertRaises(ValueError):
            self.page.setCoordinateExpression("plusZ", "5 deg")

    def test_circle_cylinder_and_axial_edge_selection(self):
        circle = Part.makeCircle(6)
        cylinder = next(face for face in Part.makeCylinder(6, 10).Faces
                        if isinstance(face.Surface, Part.Cylinder))
        axial = Part.makeLine(FreeCAD.Vector(3, 4, 0), FreeCAD.Vector(3, 4, 10))
        for sub, expected in ((circle, 6), (cylinder, 6), (axial, 5)):
            with self.subTest(shape=sub.ShapeType):
                selection = [SimpleNamespace(SubObjects=[sub])]
                self.assertEqual(self.page.selectionValue("plusX", selection), expected)
        self.page.updateSelection(self.operation, [])
        self.assertFalse(self.page.form.plusXSet.isEnabled())
        self.assertFalse(self.page.form.plusZSet.isEnabled())
        offset_circle = Part.makeCircle(6, FreeCAD.Vector(2, 0, 0))
        self.assertIsNone(self.page.selectionValue(
            "plusX", [SimpleNamespace(SubObjects=[offset_circle])]))

    def test_external_updates_and_rear_selection(self):
        self.operation.MaxDiameter = 24
        self.page.updateData(self.operation, "MaxDiameter")
        self.assertEqual(self.page.form.plusX.property("rawValue"), 12)
        self.tool.ToolPost = "Rear"
        self.page.setFields(self.operation)
        self.assertEqual(self.page.form.minusX.property("rawValue"), -12)
        selection = [SimpleNamespace(SubObjects=[Part.Vertex(FreeCAD.Vector(6, 8, 4))])]
        with patch.object(FreeCADGui.Selection, "getSelectionEx", return_value=selection):
            self.page.setFromSelection("minusX")
        self.assertEqual(self.operation.MaxDiameter.Value, 20)
        self.assertEqual(self.page.form.minusX.property("rawValue"), -10)

    def test_cancel_restores_original_containment_and_expressions(self):
        self.operation.setExpression("MaxDiameter", "16 mm")
        self.document.recompute()
        self.document.openTransaction("Containment edit")
        self.page.setCoordinateExpression("plusX", "11 mm")
        self.page.form.minusZ.setProperty("rawValue", -25)
        self.document.abortTransaction()
        self.assertEqual(self.operation.MaxDiameter.Value, 16)
        self.assertEqual(self.operation.FinalDepth.Value, -20)
        self.assertEqual(dict(self.operation.ExpressionEngine)["MaxDiameter"], "16 mm")

    def test_existing_properties_and_expressions_survive_save_reopen(self):
        properties = tuple(self.operation.PropertiesList)
        self.page.setCoordinateExpression("plusX", "11 mm")
        self.page.form.minusZ.setProperty("rawValue", -25)
        self.document.recompute()
        with TemporaryDirectory() as directory:
            filename = str(Path(directory) / "containment.FCStd")
            self.document.saveAs(filename)
            self.page.pageCleanup()
            self.page.form.deleteLater()
            FreeCAD.closeDocument(self.document.Name)
            self.document = FreeCAD.openDocument(filename)
            self.operation = self.document.getObject("Operation")
            self.page = TaskPanelContainment(self.operation, 0)
            self.page.initPage(self.operation)
            self.assertEqual(self.page.form.plusX.property("rawValue"), 11)
            self.assertEqual(self.page.form.minusZ.property("rawValue"), -25)
            self.assertEqual(tuple(self.operation.PropertiesList), properties)
            self.assertIn("MaxDiameter", dict(self.operation.ExpressionEngine))
