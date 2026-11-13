import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import MagicMock, Mock, patch
from xml.etree import ElementTree


class TurningTaskPageTests(unittest.TestCase):
    def setUp(self):
        scripts = Path(__file__).resolve().parents[1] / "PathTurnScripts"
        modules = {}
        for name in (
                "Path", "Path.Log", "Path.Op", "Path.Op.Gui", "Path.Op.Gui.Base",
                "Path.Op.Gui.Selection", "Path.Base", "Path.Base.Gui", "Path.Base.Gui.Util",
                "PathScripts", "PathScripts.PathUtils", "PathTurnScripts",
                "PathTurnScripts.PathTurnAddonHelpers", "PathTurnScripts.PathTurnContainment",
                "PathTurnScripts.PathTurnToolBit", "PathTurnScripts.PathTurnDrill",
                "PathTurnScripts.PathTurnStockPreview", "Part", "PySide"):
            modules[name] = ModuleType(name)
            modules[name].__path__ = []

        modules["FreeCAD"] = SimpleNamespace(
            Qt=SimpleNamespace(translate=lambda context, text: text),
            addDocumentObserver=Mock(), removeDocumentObserver=Mock())
        modules["FreeCADGui"] = SimpleNamespace(addIcon=Mock())
        modules["PySide"].QtCore = SimpleNamespace(
            QTimer=MagicMock(), QT_TRANSLATE_NOOP=lambda context, text: text)
        modules["PySide"].QtGui = MagicMock()
        log = modules["Path.Log"]
        log.Level = SimpleNamespace(NOTICE=1, DEBUG=2)
        log.thisModule = Mock()
        log.setLevel = Mock()
        selection = modules["Path.Op.Gui.Selection"]
        selection.select = Mock()
        gui = modules["Path.Op.Gui.Base"]
        gui.TaskPanelPage = type("TaskPanelPage", (), {})
        self.z_selection = Mock(return_value=12.5)
        gui.TaskPanelHeightsPage = type(
            "TaskPanelHeightsPage", (), {"selectionZLevel": self.z_selection})
        gui.ViewProvider = type("ViewProvider", (), {"setEdit": lambda *args: None})
        gui.SetupOperation = Mock()
        modules["PathTurnScripts.PathTurnContainment"].ContainmentPreview = MagicMock()
        modules["PathTurnScripts.PathTurnToolBit"].post_from_parameters = Mock()
        modules["PathTurnScripts.PathTurnDrill"].Create = Mock()
        modules["PathTurnScripts.PathTurnDrill"].SetupProperties = Mock()
        modules["PathTurnScripts.PathTurnStockPreview"].StockGuide = MagicMock()

        module_patch = patch.dict(sys.modules, modules)
        module_patch.start()
        self.addCleanup(module_patch.stop)

        def load(name):
            qualified = "PathTurnScripts." + name
            spec = importlib.util.spec_from_file_location(qualified, scripts / (name + ".py"))
            module = importlib.util.module_from_spec(spec)
            sys.modules[qualified] = module
            spec.loader.exec_module(module)
            return module

        self.containment = load("PathTurnContainmentGui")
        self.base = load("PathTurnBaseGui")
        self.drill = load("PathTurnDrillGui")

    def test_cam_diameter_hook_creates_containment_for_turning_and_drill(self):
        for op_class, containment_class in (
                (self.base.TaskPanelTurnBase, self.containment.TaskPanelContainment),
                (self.drill.TaskPanelOpPage, self.drill.TaskPanelDrillContainment)):
            with self.subTest(operation=op_class.__name__):
                self.assertIs(op_class.taskPanelDiametersPage, containment_class)
                page = containment_class.__new__(containment_class)
                page.form = MagicMock()
                operation = op_class.__new__(op_class)
                operation.form = MagicMock()
                operation.parent = SimpleNamespace(featurePages=[page, operation])
                operation.updateContainment = Mock()
                obj = SimpleNamespace(
                    Proxy=SimpleNamespace(), ViewObject=SimpleNamespace(RootNode=object()))

                operation.initPage(obj)

                self.assertIs(operation.containment_page, page)
                self.assertEqual(operation.parent.featurePages, [page, operation])
                self.assertIs(operation.form.showContainment, page.form.showContainment)

    def test_z_selection_uses_current_cam_heights_api(self):
        page = self.containment.TaskPanelContainment.__new__(
            self.containment.TaskPanelContainment)
        page.obj = object()
        selection = [object()]

        self.assertEqual(page.selectionValue("plusZ", selection), 12.5)
        self.z_selection.assert_called_once_with(page, page.obj, selection)

    def test_drill_containment_only_maps_axial_limits(self):
        page = self.drill.TaskPanelDrillContainment.__new__(self.drill.TaskPanelDrillContainment)
        self.assertEqual(
            page.mapping(object()),
            {"plusZ": ("StartDepth", 1), "minusZ": ("FinalDepth", 1)},
        )

    def test_operation_form_does_not_duplicate_controller_controls(self):
        path = (Path(__file__).resolve().parents[1] / "Gui" / "Resources" /
                "panels" / "PageOpTurnBaseEdit.ui")
        form = ElementTree.parse(path)
        for name in ("toolController", "coolantController"):
            with self.subTest(widget=name):
                self.assertIsNone(form.find(f".//widget[@name='{name}']"))
        for name in ("mode", "direction"):
            with self.subTest(widget=name):
                self.assertIsNotNone(form.find(f".//widget[@name='{name}']"))


class FreeCADControllerPageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import FreeCAD
        except ModuleNotFoundError as error:
            if error.name != "FreeCAD":
                raise
            raise unittest.SkipTest("Requires FreeCAD GUI.") from error
        if not FreeCAD.GuiUp:
            raise unittest.SkipTest("Requires FreeCAD GUI.")

        import Path.Op.Base as PathOp
        import Path.Op.Gui.Base as PathOpGui
        import Path.Tool.Controller as PathToolController
        from PathTurnScripts import PathTurnBaseGui

        cls.app = FreeCAD
        cls.cam = PathOp
        cls.cam_gui = PathOpGui
        cls.controllers = PathToolController
        cls.turn_gui = PathTurnBaseGui

    def setUp(self):
        document = self.app.newDocument("TurningControllerPageTest")
        self.addCleanup(self.app.closeDocument, document.Name)
        first_tool = document.addObject("Part::Feature", "FirstTool")
        second_tool = document.addObject("Part::Feature", "SecondTool")
        self.first = self.controllers.Create(
            "TC First", first_tool, 1, assignViewProvider=False)
        self.second = self.controllers.Create(
            "TC Second", second_tool, 2, assignViewProvider=False)
        proxy = SimpleNamespace(
            __module__=__name__,
            optional_parameters=lambda: (
                ("PassOffset", False), ("FinishPasses", False),
                ("StockToLeave", False), ("AllowGrooving", False)),
            pass_offset_label="Pass Offset",
            isToolSupported=lambda obj, tool: True)
        self.obj = SimpleNamespace(
            Label="Turning", Proxy=proxy, ToolController=self.first,
            CoolantMode="None", Mode="External", Direction="-Z",
            getEnumerationsOfProperty=lambda name: (
                ["External", "Internal"] if name == "Mode" else ["-Z", "+Z"]))
        job = SimpleNamespace(SetupSheet=SimpleNamespace(CoolantModes=["None", "Flood"]))
        utils = self.cam_gui.PathUtils
        for name, value in (
                ("findParentJob", lambda obj: job),
                ("getToolControllers", lambda obj, proxy=None: [
                    tc for tc in (self.first, self.second)
                    if (proxy or obj.Proxy).isToolSupported(obj, tc.Tool)]),
                ("findToolController", lambda obj, proxy, name=None: next(
                    tc for tc in (self.first, self.second) if name is None or tc.Label == name)),
                ("GetJobs", lambda: [])):
            patcher = patch.object(utils, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

        self.operation = self.turn_gui.TaskPanelTurnBase(
            self.obj, self.cam.FeatureTool | self.cam.FeatureCoolant)
        self.operation.updateContainment = Mock()
        self.addCleanup(self.operation.form.deleteLater)
        if self.operation._installTCUpdate():
            self.addCleanup(
                self.cam_gui.PathJob.Notification.updateTC.disconnect,
                self.operation.resetToolController)

        self.tool_page = self.cam_gui.TaskPanelToolControllerPage(
            self.obj, self.cam.FeatureTool | self.cam.FeatureCoolant)
        self.addCleanup(self.tool_page.form.deleteLater)
        self.addCleanup(self.tool_page.pageCleanup)
        self.tool_page.initPage(self.obj)
        self.tool_page.setFields(self.obj)
        self.operation.parent = SimpleNamespace(featurePages=[self.tool_page, self.operation])
        self.operation.setFields(self.obj)

    def test_controller_editor_is_only_on_controller_page(self):
        self.assertIsNotNone(self.tool_page.tcEditor)
        self.assertIsNone(self.operation.tcEditor)
        self.assertFalse(hasattr(self.operation.form, "toolController"))
        self.assertFalse(hasattr(self.operation.form, "coolantController"))
        self.assertTrue(hasattr(self.tool_page.form, "toolController"))
        self.assertTrue(hasattr(self.tool_page.form, "coolantController"))
        self.assertFalse(self.operation._installTCUpdate())
        self.assertTrue(self.tool_page._installTCUpdate())

    def test_controller_and_coolant_changes_survive_operation_apply(self):
        combo = self.tool_page.form.toolController
        index = combo.findText(self.second.Label)
        self.assertGreaterEqual(index, 0)
        combo.setCurrentIndex(index)
        self.tool_page.form.coolantController.setCurrentText("Flood")
        self.operation.form.direction.setCurrentText("+Z")
        self.tool_page.getFields(self.obj)
        self.operation.getFields(self.obj)

        self.assertEqual(self.obj.ToolController, self.second)
        self.assertEqual(self.obj.CoolantMode, "Flood")
        self.assertEqual(self.obj.Direction, "+Z")

    def test_operation_hides_empty_mode_frame(self):
        del self.obj.Mode
        del self.obj.Direction
        self.operation.setFields(self.obj)

        self.assertTrue(self.operation.form.frame.isHidden())

    def test_changing_mode_refreshes_compatible_tool_controllers(self):
        for controller, mode in ((self.first, "External"), (self.second, "Internal")):
            controller.Tool.addProperty("App::PropertyString", "Mode")
            controller.Tool.Mode = mode
        self.obj.Proxy.isToolSupported = lambda obj, tool: tool.Mode == obj.Mode

        self.operation.form.mode.setCurrentText("Internal")
        with patch.object(self.turn_gui.PathLog, "warning") as warning:
            self.operation.getFields(self.obj)

        self.assertEqual(self.obj.ToolController, self.second)
        self.assertEqual(self.tool_page.form.toolController.currentText(), self.second.Label)
        self.assertEqual(self.tool_page.tcEditor.obj, self.second)
        warning.assert_called_once()

    def test_changing_mode_warns_when_no_compatible_controller_exists(self):
        for controller in (self.first, self.second):
            controller.Tool.addProperty("App::PropertyString", "Mode")
            controller.Tool.Mode = "External"
        self.obj.Proxy.isToolSupported = lambda obj, tool: tool.Mode == obj.Mode

        self.operation.form.mode.setCurrentText("Internal")
        with patch.object(self.turn_gui.PathLog, "warning") as warning:
            self.operation.getFields(self.obj)

        self.assertEqual(self.obj.ToolController, self.first)
        self.assertEqual(self.tool_page.form.toolController.findText(self.first.Label), -1)
        warning.assert_called_once()

    def test_changing_mode_keeps_a_compatible_controller(self):
        self.operation.form.mode.setCurrentText("Internal")
        with patch.object(self.turn_gui.PathLog, "warning") as warning:
            self.operation.getFields(self.obj)

        self.assertEqual(self.obj.ToolController, self.first)
        self.assertEqual(self.tool_page.form.toolController.currentText(), self.first.Label)
        warning.assert_not_called()
