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


@unittest.skipUnless("FreeCAD" in sys.modules, "Requires the FreeCAD native runtime")
class NativeToolBitTests(unittest.TestCase):
    def test_reference_labels_preserve_existing_selections(self):
        from PySide import QtGui
        from ToolLibrary import freecad as assets
        from ToolLibrary.iso_gui import IsoToolDialog

        application = QtGui.QApplication.instance() or QtGui.QApplication([])
        snapshot = assets.iso_tool_preset("C", "09", "04", "R")
        for reference, label in (("TipTangent", "Tip tangent"), ("StoredOrigin", "Tip"), ("NoseCentre", "Tip centre"),
                                 ("InsertCentre", "Insert centre")):
            with self.subTest(reference=reference):
                dialog = IsoToolDialog(dict(snapshot.values, ToolReference=reference))
                try:
                    self.assertEqual(dialog.reference.currentText(), label)
                    self.assertEqual(dialog.values()["ToolReference"], reference)
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

    def test_conflicting_or_invalid_reference_parameters_are_rejected(self):
        from ToolLibrary import freecad as assets

        attributes, _ = assets.iso_tool_definition("C", "09", "04", "R")
        for nose, insert in ((True, True), (False, "true"), (False, 1)):
            with self.subTest(nose=nose, insert=insert):
                attributes["parameter"].update(NoseCentre=nose, InsertCentre=insert)
                with self.assertRaises(ValueError):
                    assets._iso_values(attributes)
        for nose, insert, tangent in ((True, False, True), (False, True, True), (False, False, "true")):
            with self.subTest(nose=nose, insert=insert, tangent=tangent):
                attributes["parameter"].update(NoseCentre=nose, InsertCentre=insert, TipTangent=tangent)
                with self.assertRaises(ValueError):
                    assets._iso_values(attributes)

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
                    bag.TipTangent = True
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
        from PathTurnScripts.PathTurnToolBit import create_tool
        from ToolLibrary import freecad as assets

        active = FreeCAD.ActiveDocument
        documents = []
        try:
            with TemporaryDirectory() as directory:
                for family, size in (("C", "09"), ("D", "07"), ("S", "09"), ("T", "11")):
                    for reference in ("StoredOrigin", "NoseCentre", "InsertCentre", "TipTangent"):
                        for side in ("Near", "Far"):
                            with self.subTest(family=family, reference=reference, side=side):
                                attributes, path = assets.iso_tool_definition(family, size, "04", "R")
                                original = assets._iso_values(attributes)
                                values = dict(original, ToolReference=reference, ToolSide=side)
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
                                self.assertEqual(copied.InsertCentre, reference == "InsertCentre")
                                self.assertEqual(copied.NoseCentre, reference == "NoseCentre")
                                self.assertEqual(copied.TipTangent, reference == "TipTangent")
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
                                    self.assertEqual(tool.InsertCentre, reference == "InsertCentre")
                                    self.assertEqual(tool.NoseCentre, reference == "NoseCentre")
                                    self.assertEqual(tool.TipTangent, reference == "TipTangent")
                                self.assertLess(before.cut(tool.Shape).Volume + tool.Shape.cut(before).Volume, 1e-7)
                                tool.EdgeLength = tool.EdgeLength.Value * 1.1
                                document.recompute()
                                self.assertTrue(tool.Shape.isValid())
                                self.assertAlmostEqual(tool.Diameter.Value, 17.25)
                                if reference == "InsertCentre":
                                    centre = tool.Shape.CenterOfMass
                                    self.assertLess(math.hypot(centre.x, centre.z), 1e-4)
                                FreeCAD.closeDocument(documents.pop())
        finally:
            for name in reversed(documents):
                FreeCAD.closeDocument(name)
            FreeCAD.setActiveDocument(active.Name if active else "")

    def test_legacy_upgrade_preserves_shared_template_and_metadata(self):
        import json
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from types import SimpleNamespace
        from unittest.mock import patch

        import FreeCAD
        from ToolLibrary import freecad as assets

        attributes, path = assets.iso_tool_definition("C", "09", "04", "R")
        attributes["parameter"].pop("InsertCentre")
        attributes["parameter"].pop("TipTangent")
        attributes["parameter"]["Diameter"] = "0.5 in"
        attributes["attribute"]["custom"] = {"keep": [1, 2]}
        active = FreeCAD.ActiveDocument
        document = FreeCAD.openDocument(str(path), hidden=True)
        try:
            for axis, sign, trig in (("x", "-", "cos"), ("y", "", "sin")):
                document.Sketch.setExpression(
                    ".AttachmentOffset.Base." + axis,
                    "<<Attributes>>.NoseCentre ? " + sign
                    + "<<Attributes>>.TipRadius / sin(<<Attributes>>.TipAngle / 2) * "
                    + trig + "(<<Attributes>>.Rotation) : 0 mm")
            document.getObjectsByLabel("Attributes")[0].removeProperty("InsertCentre")
            document.getObjectsByLabel("Attributes")[0].removeProperty("TipTangent")
            document.recompute()
            with TemporaryDirectory() as directory:
                filename = Path(directory) / "legacy.fcstd"
                document.saveAs(str(filename))
                shape_data = filename.read_bytes()
        finally:
            FreeCAD.closeDocument(document.Name)
            FreeCAD.setActiveDocument(active.Name if active else "")
        uri = assets.AssetUri.build(asset_type="toolbit", asset_id="legacy-reference-test")
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
            values = dict(snapshot.values, ToolReference="TipTangent")
            self.assertTrue(assets.iso_tool_preview(snapshot, values))
            self.assertEqual(stored, original)
            updated = assets.save_iso_tool(snapshot, values)
            self.assertNotEqual(updated.attributes["shape"], attributes["shape"])
            self.assertEqual(stored[str(shape_uri)], shape_data)
            self.assertEqual(updated.attributes["attribute"], attributes["attribute"])
            self.assertEqual(updated.attributes["parameter"]["Diameter"], "0.5 in")
            reloaded = assets.load_iso_tool(uri)
            self.assertFalse(reloaded.needs_reference_update)
            self.assertEqual(reloaded.values["ToolReference"], "TipTangent")


if __name__ == "__main__":
    unittest.main()
