"""Run with: python3 -S -m unittest discover -s tests -v."""

import sys
import unittest

from ToolLibrary.library import ToolEntry, ToolLibrary


class ToolLibraryTests(unittest.TestCase):
    def test_import_needs_no_external_packages(self):
        dependencies = {"FreeCAD", "FreeCADGui", "Part", "Path", "PySide", "liblathe"}
        self.assertFalse(dependencies.intersection(sys.modules))

    def test_table_operations_and_numeric_sorting(self):
        library = ToolLibrary()
        self.assertEqual(library.next_number, 1)
        library.add(ToolEntry(10, "first", "D insert", "IsoShape"))
        library.add(ToolEntry(2, "second"))
        self.assertEqual([entry.number for entry in library.entries], [2, 10])
        self.assertEqual(library.next_number, 11)
        library.edit(10, name="Edited")
        library.renumber(10, 1)
        self.assertEqual(
            library.get(1), ToolEntry(1, "first", "Edited", "IsoShape")
        )
        self.assertEqual([entry.number for entry in library.entries], [1, 2])
        library.remove(2)
        self.assertEqual(library.entries, (library.get(1),))

    def test_invalid_changes_leave_library_unchanged(self):
        entries = (ToolEntry(1, "first"), ToolEntry(2, "second"))
        library = ToolLibrary(entries)
        for operation in (
            lambda: library.add(ToolEntry(1, "different")),
            lambda: library.add(ToolEntry(3, "first")),
            lambda: library.renumber(1, 2),
            lambda: library.renumber(1, 0),
        ):
            with self.assertRaises(ValueError):
                operation()
            self.assertEqual(library.entries, entries)

    def test_startup_requires_tool_side_api(self):
        from types import ModuleType, SimpleNamespace
        from unittest.mock import Mock, patch
        from PathTurnScripts import initialize

        library = ModuleType("liblathe")
        library.__version__ = "0.0.8"
        library.__file__ = "/test/liblathe/__init__.py"
        tools = ModuleType("liblathe.tool.tool")
        message = Mock()
        modules = {
            "FreeCAD": SimpleNamespace(Console=SimpleNamespace(PrintMessage=message)),
            "liblathe": library,
            "liblathe.tool": ModuleType("liblathe.tool"),
            "liblathe.tool.tool": tools,
        }
        with patch.dict(sys.modules, modules):
            with self.assertRaisesRegex(ImportError, "requires a LibLathe build with the ToolSide enum") as error:
                initialize()
            self.assertIn(library.__file__, str(error.exception))
            tools.ToolSide = SimpleNamespace(NEAR=object())
            with self.assertRaisesRegex(ImportError, "ToolSide.NEAR and ToolSide.FAR"):
                initialize()
            tools.ToolSide.FAR = object()
            initialize()
        self.assertIn(library.__file__, message.call_args.args[0])



@unittest.skipUnless("FreeCAD" in sys.modules, "Requires the FreeCAD native runtime")
class NativeToolBitTests(unittest.TestCase):
    def test_reference_labels_preserve_existing_selections(self):
        from PySide import QtGui
        from ToolLibrary import freecad as assets
        from ToolLibrary.iso_gui import IsoToolDialog

        application = QtGui.QApplication.instance() or QtGui.QApplication([])
        snapshot = assets.iso_tool_preset("C", "09", "04", "R")
        self.assertEqual(snapshot.values["Compensation"], "Tip Tangent")
        for reference in ("Tip Tangent", "Tip", "Tip centre", "Insert centre"):
            with self.subTest(reference=reference):
                dialog = IsoToolDialog(dict(snapshot.values, Compensation=reference))
                try:
                    self.assertEqual(dialog.reference.currentText(), reference)
                    self.assertEqual(dialog.values()["Compensation"], reference)
                    self.assertEqual(dialog.reference.count(), 4)
                    self.assertEqual(dialog.reference.findText("Stored origin"), -1)
                    self.assertTrue(dialog.save_button.isEnabled())
                    application.processEvents()
                finally:
                    dialog.reject()

    def test_active_gui_edit_still_blocks_job_addition(self):
        from types import SimpleNamespace
        from unittest.mock import patch

        import FreeCAD
        from ToolLibrary import freecad as assets

        if not FreeCAD.GuiUp:
            self.skipTest("Requires the FreeCAD GUI")
        import FreeCADGui

        job = SimpleNamespace(Document=SimpleNamespace(Name="EditTest"), Tools=SimpleNamespace(Group=[]))
        for editing, task_dialog in ((object(), False), (None, True), (None, False)):
            with self.subTest(editing=editing is not None, task_dialog=task_dialog):
                gui_document = SimpleNamespace(getInEdit=lambda editing=editing: editing)
                control = SimpleNamespace(activeDialog=lambda task_dialog=task_dialog: task_dialog)
                with (
                    patch.object(assets, "_job", return_value=job),
                    patch.object(FreeCADGui, "getDocument", return_value=gui_document),
                    patch.object(FreeCADGui, "Control", control),
                ):
                    problem = assets.job_add_problem("EditTest", "Job", 12)
                    if editing is not None or task_dialog:
                        self.assertIn("Finish the current document edit", problem)
                    else:
                        self.assertIsNone(problem)

    def test_pending_undo_transaction_does_not_block_job_addition(self):
        from types import SimpleNamespace
        from unittest.mock import patch

        import FreeCAD
        from ToolLibrary import freecad as assets

        active = FreeCAD.ActiveDocument
        document = FreeCAD.newDocument("PendingToolAdditionTest")
        try:
            document.UndoMode = 1
            document.openTransaction("Previous document change")
            document.addObject("App::FeaturePython", "PreviousChange")
            self.assertTrue(document.HasPendingTransaction)
            job = SimpleNamespace(Document=document, Tools=SimpleNamespace(Group=[]))
            with patch.object(assets, "_job", return_value=job):
                self.assertIsNone(assets.job_add_problem(document.Name, "Job", 12))
                job.Tools.Group.append(SimpleNamespace(ToolNumber=12))
                self.assertIn("already in use", assets.job_add_problem(document.Name, "Job", 12))
            self.assertTrue(document.HasPendingTransaction)
        finally:
            document.abortTransaction()
            FreeCAD.closeDocument(document.Name)
            FreeCAD.setActiveDocument(active.Name if active else "")

    def test_add_to_job_revalidates_when_current_tool_changes(self):
        from types import SimpleNamespace
        from unittest.mock import patch

        from PySide import QtGui
        from ToolLibrary import freecad as assets
        from ToolLibrary.gui import LibraryDialog

        application = QtGui.QApplication.instance() or QtGui.QApplication([])
        used = set()

        def problem(document, job, number):
            return "Tool number already in use" if number in used else None

        def add(entry, document, job):
            used.add(entry.number)
            return SimpleNamespace(ToolNumber=entry.number)

        table = ToolLibrary((ToolEntry(11, "first"), ToolEntry(12, "second")))
        snapshot = assets.LibrarySnapshot("library://test", "Test", table, {}, {}, ())
        with patch.object(assets, "library_location", return_value={"writable": True, "path": "test"}), \
                patch.object(assets, "job_choices", return_value=("document", (("Job", "Job"),), "Job")), \
                patch.object(assets, "job_add_problem", side_effect=problem), \
                patch.object(assets, "add_to_job", side_effect=add), \
                patch.object(LibraryDialog, "open_library"), \
                patch.object(LibraryDialog, "reload_libraries"):
            dialog = LibraryDialog()
            try:
                dialog._set_snapshot(snapshot)
                dialog.rows.setCurrentCell(0, 0)
                self.assertTrue(dialog.job_button.isEnabled())
                dialog.add_to_job()
                self.assertFalse(dialog.job_button.isEnabled())
                dialog.rows.setCurrentCell(1, 0)
                self.assertTrue(dialog.job_button.isEnabled())
                dialog.add_to_job()
                self.assertEqual(used, {11, 12})
                self.assertFalse(dialog.job_button.isEnabled())
                dialog.rows.setCurrentCell(0, 0)
                self.assertFalse(dialog.job_button.isEnabled())
                application.processEvents()
            finally:
                dialog.reject()

    def test_compensation_is_required_and_validated(self):
        from ToolLibrary import freecad as assets

        attributes, _ = assets.iso_tool_definition("C", "09", "04", "R")
        attributes["parameter"].pop("Compensation")
        with self.assertRaises(ValueError):
            assets._iso_values(attributes)

        for reference in ("Tip Tangent", "Tip", "Tip centre", "Insert centre"):
            attributes, _ = assets.iso_tool_definition("C", "09", "04", "R")
            attributes["parameter"]["Compensation"] = reference
            self.assertEqual(assets._iso_values(attributes)["Compensation"], reference)
        for reference in (None, "unknown", True, 0):
            attributes["parameter"]["Compensation"] = reference
            with self.assertRaises(ValueError):
                assets._iso_values(attributes)

    def test_operation_maps_side_to_enum_and_restores_outline(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        from liblathe.base.point import Point
        from liblathe.base.segment import Segment
        from liblathe.tool.tool import ToolSide
        from PathTurnScripts import PathTurnBase

        outline = [Segment(Point(12, 0), Point(10, -5), 0.2)]
        insert = [Segment(Point(0, 0), Point(1, 1))]
        proxy = SimpleNamespace(part_outline=outline)
        for name, side, radial in (("Near", ToolSide.NEAR, 12), ("Far", ToolSide.FAR, -12)):
            obj = SimpleNamespace(ToolController=SimpleNamespace(Tool=SimpleNamespace(
                Compensation="Tip Tangent", ToolSide=name, Shape=object())))

            def generate(operation, tool):
                self.assertIs(tool.side, side)
                self.assertEqual(proxy.part_outline[0].start.X, radial)
                self.assertEqual(tool.get_segmentgroup().getSegments()[0].end.X, 1)
                self.assertIs(operation, obj)

            proxy.op_generate_gcode = generate
            with patch.object(PathTurnBase.PathTurnHelpers, "getToolSegments", return_value=insert):
                PathTurnBase.ObjectOp.generate_gcode(proxy, obj)
                self.assertIs(proxy.part_outline, outline)

                def fail_planning(*_arguments):
                    raise RuntimeError("planning failed")

                proxy.op_generate_gcode = fail_planning
                with self.assertRaisesRegex(RuntimeError, "planning failed"):
                    PathTurnBase.ObjectOp.generate_gcode(proxy, obj)
                self.assertIs(proxy.part_outline, outline)

    def test_tip_tangent_native_datum_follows_mounting_and_side(self):
        import math

        import FreeCAD
        import Part
        from ToolLibrary import freecad as assets

        active = FreeCAD.ActiveDocument
        try:
            for family, size in (("C", "09"), ("D", "07"), ("S", "09"), ("T", "11")):
                _, path = assets.iso_tool_definition(family, size, "04", "R")
                document = FreeCAD.openDocument(str(path), hidden=True)
                try:
                    bag = document.getObjectsByLabel("Attributes")[0]
                    self.assertEqual(bag.Compensation, "Tip Tangent")
                    bag.Compensation = "Tip Tangent"
                    for angle in (-360, -180, -135, -90, -45, 0, 45, 90, 135, 180, 270, 360):
                        for side in ("Near", "Far"):
                            with self.subTest(family=family, angle=angle, side=side):
                                bag.Rotation = angle
                                bag.ToolSide = side
                                document.recompute()
                                self.assertTrue(document.Body.Shape.isValid())
                                radius = bag.TipRadius.Value
                                cosine, sine = math.cos(math.radians(angle)), math.sin(math.radians(angle))
                                radial_sign = (1 if cosine > 1e-12 else -1 if cosine < -1e-12 else
                                               -1 if side == "Far" else 1)
                                expected = (radius * radial_sign, radius * (-1 if sine > 1e-12 else 1))
                                distance = radius / math.sin(math.radians(bag.TipAngle.Value) / 2)
                                offset = document.Sketch.AttachmentOffset.Base
                                self.assertAlmostEqual(offset.x, -distance * cosine + expected[0], places=9)
                                self.assertAlmostEqual(offset.y, distance * sine + expected[1], places=9)
                                centres = [edge.Curve.Center for edge in document.Body.Shape.Edges
                                           if isinstance(edge.Curve, Part.Circle)
                                           and abs(edge.Curve.Radius - radius) < 1e-4]
                                self.assertLess(min(math.hypot(point.x - expected[0], point.z - expected[1])
                                                    for point in centres), 1e-4)
                finally:
                    FreeCAD.closeDocument(document.Name)
        finally:
            FreeCAD.setActiveDocument(active.Name if active else "")

    def test_reference_and_diameter_survive_copy_and_reopen(self):
        import math
        from tempfile import TemporaryDirectory

        import FreeCAD
        import Part
        from PathTurnScripts.PathTurnToolBit import create_tool
        from ToolLibrary import freecad as assets

        active = FreeCAD.ActiveDocument
        documents = []
        try:
            with TemporaryDirectory() as directory:
                for family, size in (("C", "09"), ("D", "07"), ("S", "09"), ("T", "11")):
                    for reference in ("Tip", "Tip centre", "Insert centre", "Tip Tangent"):
                        for side in ("Near", "Far"):
                            with self.subTest(family=family, reference=reference, side=side):
                                attributes, path = assets.iso_tool_definition(family, size, "04", "R")
                                self.assertEqual(attributes["parameter"]["Compensation"], "Tip Tangent")
                                original = assets._iso_values(attributes)
                                values = dict(original, Compensation=reference, ToolSide=side)
                                if side == "Far":
                                    angle = 180 - values["Rotation"]
                                    values["Rotation"] = angle - 360 if angle > 180 else angle
                                attributes, _ = assets._updated_iso_definition(attributes, original, values)
                                document = FreeCAD.newDocument("NativeReferenceTest")
                                documents.append(document.Name)
                                tool = create_tool(path, attributes, document)
                                tool.Diameter = "17.25 mm"
                                document.recompute()
                                before = tool.Shape.copy()
                                copied_document = FreeCAD.newDocument("NativeReferenceCopy")
                                documents.append(copied_document.Name)
                                copied = copied_document.copyObject(tool, True)
                                copied_document.recompute()
                                self.assertAlmostEqual(copied.Diameter.Value, 17.25)
                                self.assertEqual(copied.Compensation, reference)
                                self.assertEqual(copied.getTypeIdOfProperty("Compensation"), "App::PropertyEnumeration")
                                FreeCAD.closeDocument(documents.pop())
                                FreeCAD.setActiveDocument(document.Name)
                                filename = directory + "/tool.fcstd"
                                name = tool.Name
                                for _ in range(2):
                                    document.saveAs(filename)
                                    FreeCAD.closeDocument(documents.pop())
                                    document = FreeCAD.openDocument(filename, hidden=True)
                                    documents.append(document.Name)
                                    tool = document.getObject(name)
                                    self.assertAlmostEqual(tool.Diameter.Value, 17.25)
                                    self.assertEqual(tool.Compensation, reference)
                                    self.assertEqual(tool.getEnumerationsOfProperty("Compensation"),
                                                     ["Tip Tangent", "Tip", "Tip centre", "Insert centre"])
                                self.assertLess(before.cut(tool.Shape).Volume + tool.Shape.cut(before).Volume, 1e-7)
                                tool.EdgeLength = tool.EdgeLength.Value * 1.1
                                document.recompute()
                                self.assertTrue(tool.Shape.isValid())
                                self.assertAlmostEqual(tool.Diameter.Value, 17.25)
                                if reference == "Insert centre":
                                    centre = tool.Shape.CenterOfMass
                                    self.assertLess(math.hypot(centre.x, centre.z), 1e-4)
                                tool.Compensation = "Tip centre"
                                document.recompute()
                                centres = [edge.Curve.Center for edge in tool.Shape.Edges
                                           if isinstance(edge.Curve, Part.Circle)
                                           and abs(edge.Curve.Radius - tool.TipRadius.Value) < 1e-4]
                                self.assertLess(min(math.hypot(point.x, point.z) for point in centres), 1e-4)
                                self.assertEqual(tool.Proxy._tool_bit_shape.get_parameter("Compensation"),
                                                 "Tip centre")
                                self.assertAlmostEqual(tool.Diameter.Value, 17.25)
                                FreeCAD.closeDocument(documents.pop())
        finally:
            for name in reversed(documents):
                FreeCAD.closeDocument(name)
            FreeCAD.setActiveDocument(active.Name if active else "")

    def test_compensation_edit_preserves_shared_template_and_metadata(self):
        import json
        from types import SimpleNamespace
        from unittest.mock import patch

        from ToolLibrary import freecad as assets

        attributes, path = assets.iso_tool_definition("C", "09", "04", "R")
        attributes["parameter"]["Diameter"] = "0.5 in"
        attributes["attribute"]["custom"] = {"keep": [1, 2]}
        shape_data = path.read_bytes()
        uri = assets.AssetUri.build(asset_type="toolbit", asset_id="compensation-test")
        shape_uri = assets._reference("toolbitshape", attributes["shape"])
        stored = {str(uri): json.dumps(attributes).encode(), str(shape_uri): shape_data}
        original = dict(stored)
        fake = SimpleNamespace(
            exists=lambda uri, **kwargs: str(uri) in stored,
            get_raw=lambda uri, **kwargs: stored[str(uri)],
            add_raw=lambda kind, identity, data, **kwargs: stored.__setitem__(
                str(assets.AssetUri.build(asset_type=kind, asset_id=identity)), data),
        )
        with patch.object(assets, "cam_assets", fake):
            snapshot = assets.load_iso_tool(uri)
            self.assertEqual(snapshot.values["Compensation"], "Tip Tangent")
            values = dict(snapshot.values, Compensation="Tip centre")
            self.assertTrue(assets.iso_tool_preview(snapshot, values))
            self.assertEqual(stored, original)
            updated = assets.save_iso_tool(snapshot, values)
            self.assertEqual(updated.attributes["shape"], attributes["shape"])
            self.assertEqual(stored[str(shape_uri)], shape_data)
            self.assertEqual(updated.attributes["attribute"], attributes["attribute"])
            self.assertEqual(updated.attributes["parameter"]["Diameter"], "0.5 in")
            reloaded = assets.load_iso_tool(uri)
            self.assertEqual(reloaded.values["Compensation"], "Tip centre")
            before_noop = dict(stored)
            self.assertIs(assets.save_iso_tool(reloaded, reloaded.values), reloaded)
            self.assertEqual(stored, before_noop)


if __name__ == "__main__":
    unittest.main()
