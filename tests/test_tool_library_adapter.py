import importlib
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import Mock, patch


class ToolLibraryJobChoicesTests(unittest.TestCase):
    def setUp(self):
        self.freecad = SimpleNamespace(ActiveDocument=None, GuiUp=False)
        self.utils = SimpleNamespace(GetJobs=Mock(return_value=[]), findParentJob=Mock())
        modules = {"FreeCAD": self.freecad, "PathScripts.PathUtils": self.utils}
        for name in ("Path", "Path.Preferences", "Path.Tool", "Path.Tool.assets",
                     "Path.Tool.camassets", "Path.Main", "Path.Main.Job", "PathScripts"):
            modules[name] = ModuleType(name)
            modules[name].__path__ = []
        modules["Path.Tool.assets"].AssetUri = Mock()
        modules["Path.Tool.camassets"].cam_assets = Mock()
        modules["FreeCADGui"] = SimpleNamespace(
            Selection=SimpleNamespace(getSelection=Mock(return_value=[])))
        self.selection = modules["FreeCADGui"].Selection.getSelection
        module_patch = patch.dict(sys.modules, modules)
        module_patch.start()
        self.addCleanup(module_patch.stop)
        self.adapter = importlib.import_module("PathTurnToolLibrary.PathTurnAdapter")

    def test_no_document_does_not_require_a_job(self):
        self.assertEqual(self.adapter.job_choices(), (None, (), ""))

    def test_active_document_defaults_to_its_only_job(self):
        document = SimpleNamespace(Name="Part")
        self.freecad.ActiveDocument = document
        self.assertEqual(self.adapter.job_choices(), ("Part", (), ""))
        job = SimpleNamespace(Name="Job", Label="Turning", Document=document)
        self.utils.GetJobs.return_value = [job]
        self.assertEqual(self.adapter.job_choices(), ("Part", (("Job", "Turning"),), "Job"))

    def test_selection_prefers_a_job_in_the_active_document(self):
        document = SimpleNamespace(Name="Part")
        other_document = SimpleNamespace(Name="OtherPart")
        self.freecad.ActiveDocument = document
        self.freecad.GuiUp = True
        first = SimpleNamespace(Name="Job", Label="First", Document=document)
        second = SimpleNamespace(Name="Job002", Label="Second", Document=document)
        self.utils.GetJobs.return_value = [first, second]
        self.assertEqual(
            self.adapter.job_choices(),
            ("Part", (("Job", "First"), ("Job002", "Second")), ""),
        )
        operation = SimpleNamespace(Document=document)
        self.selection.return_value = [operation, SimpleNamespace(Document=other_document)]
        self.utils.findParentJob.return_value = second
        self.assertEqual(
            self.adapter.job_choices(),
            ("Part", (("Job", "First"), ("Job002", "Second")), "Job002"),
        )
        self.utils.findParentJob.assert_called_once_with(operation)
