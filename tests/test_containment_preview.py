"""Run with FreeCAD's Python environment and the add-in on PYTHONPATH."""

import math
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import FreeCAD
from pivy import coin

from PathTurnScripts.PathTurnContainment import ContainmentPreview


class ContainmentPreviewTests(unittest.TestCase):
    def setUp(self):
        self.document = FreeCAD.newDocument("ContainmentPreviewTest")
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
            kind = "App::PropertyDistance" if "Depth" in name else "App::PropertyLength"
            self.operation.addProperty(kind, name)
            setattr(self.operation, name, value)
        self.root = coin.SoSeparator()
        self.preview = ContainmentPreview(self.root)
        self.sheet = self.document.addObject("App::FeaturePython", "SetupSheet")
        self.sheet.addProperty("App::PropertyDistance", "SafeHeightOffset")
        self.sheet.SafeHeightOffset = 3
        self.job = SimpleNamespace(SetupSheet=self.sheet)
        parent_job = patch("PathTurnScripts.PathTurnContainment.PathUtils.findParentJob",
                           return_value=self.job)
        parent_job.start()
        self.addCleanup(parent_job.stop)

    def tearDown(self):
        self.preview.close()
        FreeCAD.closeDocument(self.document.Name)

    def points(self):
        coordinates = self.preview.graphics.getChild(0).getChild(1)
        return [tuple(coordinates.point[index].getValue()) for index in range(4)]

    def test_rectangle_matches_signed_containment_and_preserves_document(self):
        objects = tuple(self.document.Objects)
        properties = tuple(self.operation.PropertiesList)
        for post, expected in (("Front", (2, 8)), ("Rear", (-8, -2))):
            with self.subTest(post=post):
                self.tool.ToolPost = post
                self.preview.update(self.operation)
                x0, x1 = expected
                self.assertEqual(self.points(),
                                 [(x0, 0, -20), (x1, 0, -20),
                                  (x1, 0, 10), (x0, 0, 10)])
                self.assertEqual(self.preview.graphics.getNumChildren(), 6)
        self.assertEqual(tuple(self.document.Objects), objects)
        self.assertEqual(tuple(self.operation.PropertiesList), properties)
        self.assertEqual(self.root.getNumChildren(), 1)

    def test_boundaries_contain_only_lines_without_labels(self):
        for post, outer in (("Front", 8), ("Rear", -8)):
            with self.subTest(post=post):
                self.tool.ToolPost = post
                self.preview.update(self.operation)
                boundaries = [self.preview.graphics.getChild(i) for i in range(1, 6)]
                for group in boundaries:
                    self.assertEqual(group.getNumChildren(), 4)
                    self.assertTrue(group.getChild(3).isOfType(coin.SoLineSet.getClassTypeId()))
                search = coin.SoSearchAction()
                search.setType(coin.SoText2.getClassTypeId())
                search.apply(self.preview.node)
                self.assertIsNone(search.getPath())
                coordinates = boundaries[0].getChild(2)
                self.assertEqual(tuple(coordinates.point[0].getValue()), (outer, 0, -20))

    def test_updates_replace_geometry_and_allow_zero_minimum(self):
        self.preview.update(self.operation)
        self.operation.MinDiameter = 0
        self.operation.MaxDiameter = 20
        self.operation.StartDepth = 5
        self.operation.FinalDepth = -12
        self.preview.update(self.operation)
        self.assertEqual(self.points(), [(0, 0, -12), (10, 0, -12),
                                        (10, 0, 5), (0, 0, 5)])
        self.assertEqual(self.preview.graphics.getNumChildren(), 6)
        self.assertEqual(self.root.getNumChildren(), 1)

    def test_clearance_outline_uses_radial_offset_and_mirrors_with_tool_post(self):
        for post, sign in (("Front", 1), ("Rear", -1)):
            self.tool.ToolPost = post
            for offset in (0, 0.5, 3):
                with self.subTest(post=post, offset=offset):
                    self.sheet.SafeHeightOffset = offset
                    self.preview.update(self.operation)
                    outline = self.preview.graphics.getChild(5)
                    points = outline.getChild(2).point
                    x = sign * (8 + max(offset, 0.01))
                    self.assertAlmostEqual(points[1].getValue()[0], x, places=5)
                    self.assertAlmostEqual(points[2].getValue()[0], x, places=5)
                    self.assertEqual(points[1].getValue()[2], -20)
                    self.assertEqual(points[2].getValue()[2], 10)
                    self.assertEqual(outline.getChild(1).linePattern.getValue(), 0xF0F0)

    def test_missing_job_and_invalid_clearance_clear_stale_geometry(self):
        self.preview.update(self.operation)
        with patch("PathTurnScripts.PathTurnContainment.PathUtils.findParentJob", return_value=None):
            with self.assertRaisesRegex(ValueError, "parent CAM job"):
                self.preview.update(self.operation)
        self.assertEqual(self.preview.graphics.getNumChildren(), 0)
        for offset in (-1, math.inf, math.nan):
            with self.subTest(offset=offset):
                self.preview.update(self.operation)
                job = SimpleNamespace(SetupSheet=SimpleNamespace(
                    SafeHeightOffset=SimpleNamespace(Value=offset)))
                with patch("PathTurnScripts.PathTurnContainment.PathUtils.findParentJob",
                           return_value=job):
                    with self.assertRaisesRegex(ValueError, "Clearance"):
                        self.preview.update(self.operation)
                self.assertEqual(self.preview.graphics.getNumChildren(), 0)

    def test_invalid_limits_clear_stale_geometry_and_report_error(self):
        for name, value in (("MinDiameter", -1), ("MinDiameter", 16),
                            ("MaxDiameter", 2), ("StartDepth", -21),
                            ("FinalDepth", 10), ("MaxDiameter", math.inf),
                            ("FinalDepth", math.nan)):
            with self.subTest(name=name, value=value):
                self.preview.update(self.operation)
                values = {prop: getattr(self.operation, prop) for prop in
                          ("MinDiameter", "MaxDiameter", "StartDepth", "FinalDepth")}
                values[name] = SimpleNamespace(Value=value)
                with self.assertRaises(ValueError):
                    self.preview.update(SimpleNamespace(**values))
                self.assertEqual(self.preview.graphics.getNumChildren(), 0)

    def test_overlay_is_unpickable_and_cleanup_is_idempotent(self):
        self.preview.update(self.operation)
        self.assertEqual(self.preview.node.getChild(0).style.getValue(),
                         coin.SoPickStyle.UNPICKABLE)
        self.assertFalse(self.preview.node.getChild(1).test.getValue())
        self.assertFalse(self.preview.node.getChild(1).getField("write").getValue())
        action = coin.SoRayPickAction(coin.SbViewportRegion(800, 600))
        action.setRay(coin.SbVec3f(5, -10, 0), coin.SbVec3f(0, 1, 0))
        action.apply(self.root)
        self.assertIsNone(action.getPickedPoint())
        self.preview.clear()
        self.assertEqual(self.preview.graphics.getNumChildren(), 0)
        self.preview.close()
        self.preview.close()
        self.assertEqual(self.root.getNumChildren(), 0)

    @unittest.skipUnless(FreeCAD.GuiUp, "Requires FreeCAD GUI")
    def test_editor_updates_toggle_cleanup_and_invalid_input_warning(self):
        from PySide import QtGui
        from PathTurnScripts import PathTurnBaseGui

        page = PathTurnBaseGui.TaskPanelTurnBase.__new__(PathTurnBaseGui.TaskPanelTurnBase)
        page.obj = self.operation
        page.job = self.job
        page.containment_page = Mock()
        page.form = SimpleNamespace(showContainment=QtGui.QCheckBox())
        page.form.showContainment.setChecked(True)
        page.containment = self.preview
        page.containment_error = None
        page.form.showContainment.toggled.connect(page.updateContainment)
        FreeCAD.addDocumentObserver(page)
        self.addCleanup(FreeCAD.removeDocumentObserver, page)
        page.updateContainment()
        self.operation.MaxDiameter = 24
        page.updateData(self.operation, "MaxDiameter")
        self.assertEqual(self.points()[1][0], 12)
        page.form.showContainment.setChecked(False)
        self.assertEqual(self.preview.graphics.getNumChildren(), 0)
        page.form.showContainment.setChecked(True)
        self.assertEqual(self.preview.graphics.getNumChildren(), 6)
        self.sheet.SafeHeightOffset = 5
        outline = self.preview.graphics.getChild(5)
        self.assertEqual(outline.getChild(2).point[1].getValue()[0], 17)
        self.tool.ToolPost = "Rear"
        outline = self.preview.graphics.getChild(5)
        self.assertEqual(outline.getChild(2).point[1].getValue()[0], -17)
        self.operation.MinDiameter = 30
        with patch.object(PathTurnBaseGui.PathLog, "warning") as warning:
            page.updateData(self.operation, "MinDiameter")
            page.updateData(self.operation, "MinDiameter")
            warning.assert_called_once()
        self.assertEqual(self.preview.graphics.getNumChildren(), 0)
        page.cleanupPage(self.operation)
        page.form.showContainment.setChecked(False)
        page.form.showContainment.setChecked(True)
        self.assertEqual(self.root.getNumChildren(), 0)


if __name__ == "__main__":
    unittest.main()
