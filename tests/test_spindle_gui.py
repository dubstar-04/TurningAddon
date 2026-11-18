import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import Mock, patch


def load_spindle_gui():
    class Page:
        def __init__(self, obj, features):
            self.obj = obj
            self.features = features
            self.form = self.getForm()
            self.parent = None

        def setIcon(self, icon):
            self.icon = icon

        def onDirtyChanged(self, callback):
            self.dirty_callback = callback

    class ToolControllerPage(Page):
        def getForm(self):
            return SimpleNamespace(name="native tool controller")

        def initPage(self, obj):
            self.initialized = True

    path = ModuleType("Path")
    path.__path__ = []
    path.Op = ModuleType("Path.Op")
    path.Op.__path__ = []
    path.Op.Gui = ModuleType("Path.Op.Gui")
    path.Op.Gui.__path__ = []
    path.Op.Gui.Base = ModuleType("Path.Op.Gui.Base")
    path.Op.Gui.Base.TaskPanelPage = Page
    path.Op.Gui.Base.TaskPanelToolControllerPage = ToolControllerPage

    def combo():
        widget = Mock()
        widget.blockSignals.return_value = False
        widget.findData.return_value = 0
        widget.currentData.return_value = "RPM"
        return widget

    qtgui = SimpleNamespace(
        QWidget=Mock(side_effect=lambda: Mock()),
        QGridLayout=Mock(side_effect=lambda parent: Mock()),
        QComboBox=Mock(side_effect=lambda parent: combo()),
        QLabel=Mock(side_effect=lambda *args: Mock()),
        QDoubleSpinBox=Mock(side_effect=lambda parent: Mock()),
        QSpinBox=Mock(side_effect=lambda parent: Mock()),
    )
    freecad = SimpleNamespace(
        Qt=SimpleNamespace(translate=lambda context, text: text),
        addDocumentObserver=Mock(),
        removeDocumentObserver=Mock(),
    )
    spindle_base = ModuleType("PathTurnScripts.PathTurnBase")
    spindle_base.SPINDLE_MODE_RPM = "RPM"
    spindle_base.SPINDLE_MODE_CSS = "CSS"
    spindle_base.SPINDLE_MODE_PROPERTY = "TurnSpindleMode"
    spindle_base.SURFACE_SPEED_PROPERTY = "TurnSurfaceSpeed"
    spindle_base.MAX_SPINDLE_SPEED_PROPERTY = "TurnMaxSpindleSpeed"
    spindle_base.ensure_turning_spindle_properties = Mock()

    modules = {
        "FreeCAD": freecad,
        "Path": path,
        "Path.Op": path.Op,
        "Path.Op.Gui": path.Op.Gui,
        "Path.Op.Gui.Base": path.Op.Gui.Base,
        "PathTurnScripts.PathTurnBase": spindle_base,
        "PySide": SimpleNamespace(QtGui=qtgui),
    }
    source = Path(__file__).resolve().parents[1] / "PathTurnScripts" / "PathTurnSpindleGui.py"
    spec = importlib.util.spec_from_file_location("test_turning_spindle_gui", source)
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, modules):
        spec.loader.exec_module(module)
    return module, freecad, Page


def controller(label, mode="RPM", speed=1200, surface=150, maximum=2500):
    return SimpleNamespace(
        Label=label, SpindleSpeed=speed, TurnSpindleMode=mode,
        TurnSurfaceSpeed=surface, TurnMaxSpindleSpeed=maximum)


class SpindlePageTests(unittest.TestCase):
    def setUp(self):
        self.module, self.freecad, self.page_base = load_spindle_gui()
        self.obj = SimpleNamespace(
            Proxy=SimpleNamespace(supports_css=True),
            ToolController=controller("First"),
        )

    def make_page(self):
        page = self.module.TaskPanelTurningSpindlePage(self.obj, 1)
        page.initPage(self.obj)
        self.addCleanup(page.cleanupPage, self.obj)
        return page

    def test_spindle_page_is_registered_separately_before_operation(self):
        class OtherPage(self.page_base):
            def getForm(self):
                return object()

            def initPage(self, obj):
                self.initialized = True

        containment = OtherPage(self.obj, 1)
        tool_page = self.module.TaskPanelToolControllerWithSpindlePage(self.obj, 1)
        operation = OtherPage(self.obj, 1)
        panel = SimpleNamespace(featurePages=[containment, tool_page, operation])
        callback = Mock()
        for page in panel.featurePages:
            page.parent = panel
            page.initPage(self.obj)
            page.onDirtyChanged(callback)

        spindle = panel.featurePages[2]
        self.addCleanup(spindle.cleanupPage, self.obj)
        self.assertEqual(panel.featurePages, [containment, tool_page, spindle, operation])
        self.assertIsInstance(spindle, self.module.TaskPanelTurningSpindlePage)
        self.assertIsNot(spindle.form, tool_page.form)
        self.assertEqual(tool_page.form.name, "native tool controller")
        self.assertEqual(spindle.getTitle(self.obj), "Turning Spindle")
        self.assertIs(spindle.parent, panel)
        self.assertIs(spindle.dirty_callback, callback)
        self.assertTrue(operation.initialized)

    def test_controller_switch_and_edits_use_selected_controller(self):
        page = self.make_page()
        first = self.obj.ToolController
        page.setFields(self.obj)

        second = controller("Second", mode="CSS", speed=900, surface=200, maximum=1800)
        self.obj.ToolController = second
        page.updateData(self.obj, "ToolController")
        page.controllerName.setText.assert_called_with("Tool Controller: Second")
        page.surfaceSpeed.setValue.assert_called_with(200)
        page.maxSpindleSpeed.setValue.assert_called_with(1800)

        page.spindleMode.currentData.return_value = "CSS"
        page.surfaceSpeed.value.return_value = 175
        page.maxSpindleSpeed.value.return_value = 1600
        page.getFields(self.obj)
        self.assertEqual((second.TurnSpindleMode, second.TurnSurfaceSpeed,
                          second.TurnMaxSpindleSpeed), ("CSS", 175, 1600))
        self.assertEqual((first.TurnSpindleMode, first.TurnSurfaceSpeed,
                          first.TurnMaxSpindleSpeed), ("RPM", 150, 2500))
        self.assertEqual(second.SpindleSpeed, 900)

    def test_external_controller_changes_refresh_and_observer_is_removed(self):
        page = self.make_page()
        current = self.obj.ToolController
        page.setFields(self.obj)
        current.TurnSurfaceSpeed = 180
        page.slotChangedObject(current, "TurnSurfaceSpeed")
        page.surfaceSpeed.setValue.assert_called_with(180)

        page.cleanupPage(self.obj)
        page.stopObserving()
        self.freecad.addDocumentObserver.assert_called_once_with(page)
        self.freecad.removeDocumentObserver.assert_called_once_with(page)

    def test_initializing_controller_properties_does_not_reenter_refresh(self):
        page = self.make_page()
        ensure = self.module.ensure_turning_spindle_properties
        ensure.side_effect = lambda tc, obj: page.slotChangedObject(tc, "TurnSpindleMode")
        page.setFields(self.obj)
        ensure.assert_called_once_with(self.obj.ToolController, self.obj)
        self.assertFalse(page.updating)

    def test_fixed_rpm_only_operations_do_not_edit_css_settings(self):
        self.obj.Proxy.supports_css = False
        self.obj.ToolController.TurnSpindleMode = "CSS"
        page = self.make_page()
        page.setFields(self.obj)
        page.surfaceSpeedLabel.setVisible.assert_called_with(False)
        page.maxSpindleSpeedLabel.setVisible.assert_called_with(False)
        page.spindleMode.addItem.assert_called_with("Fixed RPM (required)", "RPM")
        self.assertEqual(page.getSignalsForUpdate(self.obj), [])
        page.getFields(self.obj)
        self.assertEqual(self.obj.ToolController.TurnSpindleMode, "CSS")


if __name__ == "__main__":
    unittest.main()
