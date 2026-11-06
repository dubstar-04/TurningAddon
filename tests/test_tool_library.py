"""Run with: python3 -S -m unittest discover -s tests -v."""

import sys
import unittest

from PathTurnToolLibrary.PathTurnToolTable import ToolEntry, ToolLibrary


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


CORNER_ANGLES = {"C": 80, "D": 55, "S": 90, "T": 60}
# ISO size codes: edge length for C/D/S, inscribed circle for T.
SHAPE_SIZES = {
    "C": {
        "03": 3.97, "04": 4.76, "05": 5.56, "06": 6.35, "08": 7.94,
        "09": 9.525, "12": 12.7, "16": 15.875, "19": 19.05, "22": 22.225,
        "25": 25.4,
    },
    "D": {
        "04": 3.97, "05": 4.76, "06": 5.56, "07": 6.35, "09": 7.94,
        "11": 9.525, "15": 12.7, "19": 15.875, "23": 19.05,
    },
    "S": {
        "03": 3.97, "04": 4.76, "05": 5.56, "06": 6.35, "08": 7.94,
        "09": 9.525, "12": 12.7, "16": 15.875, "19": 19.05, "22": 22.225,
        "25": 25.4,
    },
    "T": {
        "08": 4.76, "09": 5.56, "11": 6.35, "13": 7.94, "16": 9.525,
        "22": 12.7, "27": 15.875, "33": 19.05, "38": 22.225, "44": 25.4,
    },
}
NOSE_RADII = {
    "00": 0, "V3": 0.03, "V5": 0.05, "01": 0.1, "02": 0.2,
    "04": 0.4, "08": 0.8, "12": 1.2, "16": 1.6, "20": 2.0,
    "24": 2.4, "28": 2.8, "32": 3.2,
}


def _insert_area(shape_code, inscribed, radius):
    """Rounded-insert area from the inscribed circle; every corner loses r^2 (cot(a/2) - (pi - a)/2)."""
    import math

    angle = math.radians(CORNER_ANGLES[shape_code])
    if shape_code == "T":
        return 3 * math.sqrt(3) / 4 * inscribed ** 2 - (3 * math.sqrt(3) - math.pi) * radius ** 2
    return inscribed ** 2 / math.sin(angle) - (4 / math.sin(angle) - math.pi) * radius ** 2


def _edge_choice(shape_code, length):
    code = next(code for code, value in SHAPE_SIZES[shape_code].items() if value == length)
    return f"{code} - {length:g} mm"


@unittest.skipUnless("FreeCAD" in sys.modules, "Requires the FreeCAD native runtime")
class NativeToolBitTests(unittest.TestCase):
    def test_shape_picker_previews_selection_import_and_cancel_without_asset_writes(self):
        from unittest.mock import patch

        import FreeCAD
        from PySide import QtCore, QtGui
        from PathTurnToolLibrary import PathTurnAdapter as assets
        from PathTurnToolLibrary.PathTurnToolGui import ToolShapeDialog

        application = QtGui.QApplication.instance() or QtGui.QApplication([])
        documents = set(FreeCAD.listDocuments())
        active = FreeCAD.ActiveDocument
        with patch.object(assets.cam_assets, "add_raw") as publish:
            dialog = ToolShapeDialog()
            try:
                self.assertEqual(dialog.shapes.count(), 5)
                self.assertFalse(dialog.choose_button.isEnabled())
                self.assertIsNone(dialog.selected_preset())
                for row, snapshot in enumerate(dialog.presets):
                    item = dialog.shapes.item(row)
                    self.assertTrue(item.flags() & QtCore.Qt.ItemIsEnabled, item.toolTip())
                    self.assertFalse(item.icon().isNull())
                    image = item.icon().pixmap(120, 96).toImage()
                    self.assertTrue(any(image.pixelColor(x, y).alpha()
                                        for x in range(image.width()) for y in range(image.height())))
                    dialog.shapes.setCurrentRow(row)
                    self.assertIs(dialog.selected_preset(), snapshot)
                    self.assertTrue(dialog.choose_button.isEnabled())
                self.assertEqual([snapshot.values["name"] for snapshot in dialog.presets],
                                 ["Custom profile", "ISO C rhombic 80°", "ISO D rhombic 55°", "ISO S square",
                                  "ISO T triangle"])
                dialog.accept()
                self.assertEqual(dialog.result(), QtGui.QDialog.Accepted)
                dialog.reject()
                self.assertEqual(dialog.result(), QtGui.QDialog.Rejected)
                dialog.shapes.clearSelection()
                dialog.accept()
                self.assertEqual(dialog.result(), QtGui.QDialog.Rejected)
                dialog.import_button.click()
                self.assertTrue(dialog.import_requested)
                self.assertEqual(dialog.result(), QtGui.QDialog.Accepted)
                application.processEvents()
                publish.assert_not_called()
                self.assertEqual(set(FreeCAD.listDocuments()), documents)
                self.assertEqual(FreeCAD.ActiveDocument, active)
            finally:
                dialog.reject()

    def test_shape_picker_reports_invalid_preview_and_disables_shape(self):
        from unittest.mock import patch

        from PySide import QtCore, QtGui
        from PathTurnToolLibrary import PathTurnAdapter as assets
        from PathTurnToolLibrary.PathTurnToolGui import ToolShapeDialog

        application = QtGui.QApplication.instance() or QtGui.QApplication([])
        with patch.object(assets, "custom_tool_preview", side_effect=ValueError("Invalid cutting body")):
            dialog = ToolShapeDialog()
            try:
                self.assertIn("Invalid cutting body", dialog.problem.text())
                for row in range(len(dialog.presets)):
                    self.assertFalse(dialog.shapes.item(row).flags() & QtCore.Qt.ItemIsEnabled)
            finally:
                dialog.reject()
        application.processEvents()

    def test_new_tool_grid_routes_presets_and_import_and_preserves_cancel(self):
        from types import SimpleNamespace
        from unittest.mock import patch

        from PySide import QtGui
        from PathTurnToolLibrary import PathTurnAdapter as assets
        from PathTurnToolLibrary import PathTurnToolGui as gui

        application = QtGui.QApplication.instance() or QtGui.QApplication([])
        stored = {}
        fake = SimpleNamespace(
            exists=lambda uri, **kwargs: str(uri) in stored,
            get_raw=lambda uri, **kwargs: stored[str(uri)],
            add_raw=lambda kind, identity, data, **kwargs: stored.__setitem__(
                str(assets.AssetUri.build(asset_type=kind, asset_id=identity)), data),
        )
        presets = assets.tool_shape_presets()

        def choose_c(dialog):
            dialog.shapes.setCurrentRow(next(
                row for row, snapshot in enumerate(dialog.presets)
                if snapshot.values["name"] == "ISO C rhombic 80°"))
            dialog.accept()
            return dialog.result()

        with (
            patch.object(assets, "cam_assets", fake),
            patch.object(assets, "library_location", return_value={"writable": True, "path": "test"}),
            patch.object(assets, "tool_shape_presets", return_value=presets),
            patch.object(gui.LibraryDialog, "refresh_jobs"),
            patch.object(gui.LibraryDialog, "reload_libraries"),
            patch.object(gui.LibraryDialog, "_report_error") as report_error,
        ):
            dialog = gui.LibraryDialog()
            dialog.libraries.blockSignals(True)
            dialog._set_snapshot(assets.LibrarySnapshot("test", "Test", ToolLibrary(), {}, {}, ()))
            dialog.libraries.blockSignals(False)
            try:
                with patch.object(gui.ToolShapeDialog, "exec_", return_value=QtGui.QDialog.Rejected):
                    dialog.create_tool()
                self.assertEqual(dialog.table.entries, ())
                self.assertEqual(stored, {})
                with (
                    patch.object(gui.ToolShapeDialog, "exec_", choose_c),
                    patch.object(gui.CustomToolDialog, "exec_", return_value=QtGui.QDialog.Rejected),
                ):
                    dialog.create_tool()
                self.assertEqual(dialog.table.entries, ())
                self.assertEqual(stored, {})
                with (
                    patch.object(gui.ToolShapeDialog, "exec_", choose_c),
                    patch.object(gui.CustomToolDialog, "exec_", return_value=QtGui.QDialog.Accepted),
                ):
                    dialog.create_tool()
                entry, = dialog.table.entries
                self.assertEqual(entry.name, "ISO C rhombic 80°")
                loaded = assets.load_tool_definition(entry.tool_id)
                self.assertIsNotNone(loaded.fields)
                self.assertEqual(loaded.values["EdgeLength"], "12 - 12.7 mm")
                before = dict(stored)
                with (
                    patch.object(gui.ToolShapeDialog, "exec_", lambda picker: (
                        picker._import_shape(), QtGui.QDialog.Accepted)[1]),
                    patch.object(dialog, "create_custom_tool") as import_shape,
                ):
                    dialog.create_tool()
                    import_shape.assert_called_once_with()
                self.assertEqual(stored, before)
                report_error.assert_not_called()
            finally:
                dialog.table = ToolLibrary()
                dialog.reject()
        application.processEvents()

    def test_custom_unitless_numbers_use_the_native_property_unit(self):
        from tempfile import TemporaryDirectory

        import FreeCAD
        from PathTurnScripts.PathTurnToolBit import custom_shape_from_bytes

        with TemporaryDirectory() as directory:
            path = self._custom_shape_file(directory)
            shape = custom_shape_from_bytes(path.read_bytes(), "unitless-parameters")
            for name, value, expected in (
                ("Bend", "90", "90 deg"), ("Bend", -35, "-35 deg"),
                ("Bend", "45 deg", "45 deg"), ("Reach", "12.7", "12.7 mm"),
                ("Reach", "0.5 in", "12.7 mm"),
            ):
                shape.set_parameter(name, value)
                actual = shape.get_parameter(name)
                quantity = FreeCAD.Units.Quantity(expected)
                self.assertEqual(actual.Unit, quantity.Unit)
                self.assertAlmostEqual(actual.Value, quantity.Value)
            for name, value in (("Bend", "5 mm"), ("Reach", "20 deg")):
                with self.assertRaisesRegex(ValueError, "Unexpected units"):
                    shape.set_parameter(name, value)

    def test_iso_s_uses_file_defined_iso_data_and_generic_editor(self):
        self._check_file_defined_iso_editor("S")

    def test_iso_c_uses_file_defined_iso_data_and_generic_editor(self):
        self._check_file_defined_iso_editor("C")

    def test_iso_d_uses_file_defined_iso_data_and_generic_editor(self):
        self._check_file_defined_iso_editor("D")

    def test_iso_t_uses_file_defined_iso_data_and_generic_editor(self):
        self._check_file_defined_iso_editor("T")

    def _check_file_defined_iso_editor(self, shape_code):
        import math
        from pathlib import Path

        import FreeCAD
        from PySide import QtGui
        from PathTurnToolLibrary import PathTurnAdapter as assets
        from PathTurnToolLibrary.PathTurnToolGui import CustomToolDialog

        application = QtGui.QApplication.instance() or QtGui.QApplication([])
        path = Path(__file__).resolve().parents[1] / f"Tools/Shape/Iso_{shape_code}.fcstd"
        active = FreeCAD.ActiveDocument
        document = FreeCAD.openDocument(str(path), hidden=True)
        try:
            self.assertIn(document.getObjectsByLabel("Attributes")[0], document.Body.Group)
            self.assertEqual(document.Sketch.TypeId, "Sketcher::SketchObject")
            self.assertEqual(document.Pad.Profile[0], document.Sketch)
        finally:
            FreeCAD.closeDocument(document.Name)
            FreeCAD.setActiveDocument(active.Name if active else "")
        snapshot = assets.custom_tool_preset(path)
        self.assertEqual(
            snapshot.fields["EdgeLength"]["choices"],
            tuple(f"{code} - {length:g} mm" for code, length in SHAPE_SIZES[shape_code].items()),
        )
        self.assertNotIn("InsertShape", snapshot.fields)
        self.assertNotIn("TipAngle", snapshot.fields)
        self.assertNotIn("SizeCode", snapshot.fields)
        self.assertEqual(snapshot.fields["Thickness"]["type"], "App::PropertyEnumeration")
        self.assertEqual(
            snapshot.fields["TipRadius"]["choices"],
            tuple(f"{code} - {radius:g} mm" for code, radius in NOSE_RADII.items()),
        )
        dialog = CustomToolDialog(snapshot)
        try:
            self.assertTrue(dialog.save_button.isEnabled(), dialog.problem.text())
            for code, edge_length in SHAPE_SIZES[shape_code].items():
                dialog.controls["EdgeLength"].setCurrentText(f"{code} - {edge_length:g} mm")
                dialog._refresh_preview()
                self.assertTrue(dialog.save_button.isEnabled(), (code, dialog.problem.text()))
                geometry = assets.custom_tool_preview(snapshot, dialog.values())
                self.assertTrue(geometry["outlines"])
                if shape_code == "S":
                    radial = [point[0] for edge in geometry["outlines"] for point in edge]
                    self.assertAlmostEqual(max(radial) - min(radial), edge_length)
                diameter = FreeCAD.Units.Quantity(geometry["calculated"]["Diameter"]).Value
                angle = math.radians(CORNER_ANGLES[shape_code])
                self.assertAlmostEqual(diameter, edge_length / math.sin(angle / 2))
            dialog.controls["EdgeLength"].setCurrentText(_edge_choice(shape_code, 12.7))
            for code, radius in NOSE_RADII.items():
                dialog.controls["TipRadius"].setCurrentText(f"{code} - {radius:g} mm")
                dialog._refresh_preview()
                self.assertTrue(dialog.save_button.isEnabled(), (code, dialog.problem.text()))
                geometry = assets.custom_tool_preview(snapshot, dialog.values())
                self.assertTrue(geometry["outlines"])
            for thickness in snapshot.fields["Thickness"]["choices"]:
                dialog.controls["Thickness"].setCurrentText(thickness)
                dialog._refresh_preview()
                self.assertTrue(dialog.save_button.isEnabled(), (thickness, dialog.problem.text()))
            self.assertNotIn("TipAngle", dialog.controls)
            self.assertIsInstance(dialog.controls["EdgeLength"], QtGui.QComboBox)
            self.assertIsInstance(dialog.controls["TipRadius"], QtGui.QComboBox)
            self.assertTrue(dialog.controls["Diameter"].isReadOnly())
            dialog.controls["TipRadius"].setCurrentText("04 - 0.4 mm")
            dialog.controls["ToolPost"].setCurrentText("Rear")
            dialog.controls["Compensation"].setCurrentText("Tip centre")
            for rotation in ("90", "-35", "135 deg"):
                dialog.controls["Rotation"].setText(rotation)
                dialog._refresh_preview()
                self.assertTrue(dialog.save_button.isEnabled(), (rotation, dialog.problem.text()))
            application.processEvents()
        finally:
            dialog.reject()

    def test_iso_s_preserves_body_attributes_in_native_toolbits(self):
        self._check_file_defined_iso_restore("S")

    def test_iso_c_preserves_body_attributes_in_native_toolbits(self):
        self._check_file_defined_iso_restore("C")

    def test_iso_d_preserves_body_attributes_in_native_toolbits(self):
        self._check_file_defined_iso_restore("D")

    def test_iso_t_preserves_body_attributes_in_native_toolbits(self):
        self._check_file_defined_iso_restore("T")

    def _check_file_defined_iso_restore(self, shape_code):
        import json
        from pathlib import Path
        from tempfile import TemporaryDirectory

        import FreeCAD
        import Part
        from PathTurnScripts.PathTurnToolBit import create_tool

        root = Path(__file__).resolve().parents[1]
        path = root / f"Tools/Shape/Iso_{shape_code}.fcstd"
        attributes = json.loads((root / f"Tools/Bit/iso_{shape_code.lower()}.fctb").read_text())
        active = FreeCAD.ActiveDocument
        documents = []

        def check_body(tool):
            bags = [child for child in tool.BitBody.Group if child.Label == "Attributes"]
            self.assertEqual(len(bags), 1)
            self.assertEqual(bags[0].EdgeLength, tool.EdgeLength)
            self.assertEqual(bags[0].TipRadius, tool.TipRadius)
            self.assertEqual(bags[0].Thickness, tool.Thickness)
            self.assertTrue(tool.Shape.isValid())
            self.assertEqual(len(tool.Shape.Solids), 1)
            self.assertFalse(any("Invalid" in obj.State for obj in tool.Document.Objects))
            return bags[0]

        try:
            with TemporaryDirectory() as directory:
                document = FreeCAD.newDocument("IsoInstance")
                documents.append(document.Name)
                tool = create_tool(path, attributes, document)
                check_body(tool)
                tool.EdgeLength = _edge_choice(shape_code, 4.76)
                tool.TipRadius = "00 - 0 mm"
                tool.Rotation = "90 deg"
                tool.Compensation = "Tip"
                document.recompute()
                bag = check_body(tool)
                self.assertAlmostEqual(bag.CuttingEdgeLength.Value, 4.76)
                self.assertAlmostEqual(bag.NoseRadius.Value, 0)
                copied_document = FreeCAD.newDocument("IsoCopy")
                documents.append(copied_document.Name)
                copied = copied_document.copyObject(tool, True)
                copied_document.recompute()
                check_body(copied)
                name = copied.Name
                saved = str(Path(directory) / "s-instance.fcstd")
                copied_document.saveAs(saved)
                for document_name in reversed(documents):
                    FreeCAD.closeDocument(document_name)
                documents.clear()
                document = FreeCAD.openDocument(saved, hidden=True)
                documents.append(document.Name)
                tool = document.getObject(name)
                check_body(tool)
                tool.EdgeLength = _edge_choice(shape_code, 6.35)
                tool.TipRadius = "08 - 0.8 mm"
                tool.Thickness = "06 - 6.35 mm"
                tool.ToolPost = "Rear"
                tool.Rotation = "-35 deg"
                tool.Compensation = "Tip centre"
                document.recompute()
                bag = check_body(tool)
                self.assertAlmostEqual(bag.CuttingEdgeLength.Value, 6.35)
                self.assertAlmostEqual(bag.NoseRadius.Value, 0.8)
                self.assertGreater(tool.Diameter.Value, 0)
                centres = [edge.Curve.Center for edge in tool.Shape.Edges if isinstance(edge.Curve, Part.Circle)]
                self.assertLess(min((centre.x ** 2 + centre.z ** 2) ** 0.5 for centre in centres), 1e-6)
        finally:
            for name in reversed(documents):
                FreeCAD.closeDocument(name)
            FreeCAD.setActiveDocument(active.Name if active else "")

    def test_iso_s_native_compensation_matches_actual_nose(self):
        self._check_file_defined_iso_compensation("S")

    def test_iso_c_native_compensation_matches_actual_nose(self):
        self._check_file_defined_iso_compensation("C")

    def test_iso_d_native_compensation_matches_actual_nose(self):
        self._check_file_defined_iso_compensation("D")

    def test_iso_t_native_compensation_matches_actual_nose(self):
        self._check_file_defined_iso_compensation("T")

    def test_iso_c_dimensions_match_rhombus(self):
        self._check_insert_dimensions("C")

    def test_iso_d_dimensions_match_rhombus(self):
        self._check_insert_dimensions("D")

    def test_iso_t_dimensions_match_triangle(self):
        self._check_insert_dimensions("T")

    def _check_insert_dimensions(self, shape_code):
        import math
        from pathlib import Path

        import FreeCAD
        import Part
        from PathTurnScripts import PathTurnAddonHelpers as helpers

        active = FreeCAD.ActiveDocument
        path = Path(__file__).resolve().parents[1] / f"Tools/Shape/Iso_{shape_code}.fcstd"
        document = FreeCAD.openDocument(str(path), hidden=True)
        try:
            bag = document.getObjectsByLabel("Attributes")[0]
            angle = math.radians(CORNER_ANGLES[shape_code])
            bag.Compensation = "Insert centre"
            bag.Rotation = 90
            cases = [(_edge_choice(shape_code, length), length, "04", 0.4)
                     for length in SHAPE_SIZES[shape_code].values()]
            cases += [(_edge_choice(shape_code, 12.7), 12.7, code, radius) for code, radius in NOSE_RADII.items()]
            for size, length, nose, nominal in cases:
                bag.EdgeLength = size
                bag.TipRadius = f"{nose} - {nominal:g} mm"
                document.recompute()
                # Sharp (00) noses are drawn with the template's 0.01 mm minimum radius.
                radius = max(nominal, 0.01)
                solid = document.Body.Shape
                self.assertTrue(solid.isValid(), (size, nose))
                self.assertEqual(len(solid.Solids), 1)
                self.assertAlmostEqual(solid.Volume, _insert_area(shape_code, length, radius) * bag.InsertThickness.Value,
                                       delta=1e-5)
                self.assertAlmostEqual(solid.BoundBox.YLength, bag.InsertThickness.Value)
                if shape_code == "T":
                    expected_length = 1.5 * length - radius
                else:
                    expected_length = length / math.sin(angle / 2) - 2 * radius * (1 / math.sin(angle / 2) - 1)
                self.assertAlmostEqual(solid.BoundBox.XLength, expected_length, delta=1e-6)
                self.assertTrue(helpers.getToolSegments(solid))
                self.assertAlmostEqual(bag.NoseRadius.Value, nominal)
                arcs = [edge for edge in solid.Edges if isinstance(edge.Curve, Part.Circle)]
                self.assertTrue(arcs)
                self.assertTrue(all(abs(edge.Curve.Radius - radius) < 1e-9 for edge in arcs))
        finally:
            FreeCAD.closeDocument(document.Name)
            FreeCAD.setActiveDocument(active.Name if active else "")

    def _check_file_defined_iso_compensation(self, shape_code):
        import math
        from pathlib import Path

        import FreeCAD
        import Part

        active = FreeCAD.ActiveDocument
        path = Path(__file__).resolve().parents[1] / f"Tools/Shape/Iso_{shape_code}.fcstd"
        document = FreeCAD.openDocument(str(path), hidden=True)
        try:
            bag = document.getObjectsByLabel("Attributes")[0]
            bag.EdgeLength = _edge_choice(shape_code, 12.7)
            bag.TipRadius = "16 - 1.6 mm"
            for post in ("Front", "Rear"):
                bag.ToolPost = post
                for angle in (0, 35, 45, 90, 135, 180, 225, 270, -35):
                    bag.Rotation = angle
                    effective = math.radians(angle - 90)
                    radial = math.cos(effective)
                    axial = math.sin(effective)
                    sign_x = 1 if radial > 1e-12 else -1 if radial < -1e-12 else (-1 if post == "Rear" else 1)
                    sign_z = -1 if axial > 1e-12 else 1
                    for compensation in ("Tip Tangent", "Tip centre", "Tip", "Insert centre"):
                        bag.Compensation = compensation
                        document.recompute()
                        radius = 1.6
                        corner = math.radians(CORNER_ANGLES[shape_code])
                        distance = radius / math.sin(corner / 2)
                        if compensation == "Tip Tangent":
                            expected = (sign_x * radius, sign_z * radius)
                        elif compensation == "Tip centre":
                            expected = (0, 0)
                        elif compensation == "Tip":
                            expected = (distance * radial, -distance * axial)
                        else:
                            distance -= bag.CuttingEdgeLength.Value / (2 * math.sin(corner / 2))
                            expected = (distance * radial, -distance * axial)
                        centres = [(edge.Curve.Center.x, edge.Curve.Center.z)
                                   for edge in document.Body.Shape.Edges if isinstance(edge.Curve, Part.Circle)]
                        self.assertTrue(centres, (post, angle, compensation))
                        error = min(math.hypot(centre[0] - expected[0], centre[1] - expected[1]) for centre in centres)
                        self.assertLess(error, 1e-6, (post, angle, compensation, expected, centres))
                        self.assertTrue(document.Body.Shape.isValid())
                        volume = (_insert_area(shape_code, bag.CuttingEdgeLength.Value, radius)
                                  * bag.InsertThickness.Value)
                        self.assertAlmostEqual(document.Body.Shape.Volume, volume, delta=1e-5)
        finally:
            FreeCAD.closeDocument(document.Name)
            FreeCAD.setActiveDocument(active.Name if active else "")

    def _custom_shape_file(self, directory):
        from pathlib import Path

        import FreeCAD
        from Path.Base import PropertyBag

        active = FreeCAD.ActiveDocument
        document = FreeCAD.newDocument("UserAuthoredShape")
        try:
            bag = PropertyBag.Create()
            bag.Label = "Attributes"
            definitions = {
                "CuttingSpan": ("Length", 5), "Reach": ("Length", 9),
                "Diameter": ("Length", 5),
                "Thickness": ("Length", 2), "Bend": ("Angle", 0),
                "Relieved": ("Bool", True), "Steps": ("Integer", 2),
                "Grade": ("String", "User grade"), "Allowance": ("Float", 0.125),
                "Finish": ("Enumeration", ["Rough", "Fine"]),
                "ToolPost": ("Enumeration", ["Front", "Rear"]),
                "Compensation": ("Enumeration", ["Profile datum", "Back datum"]),
                "ComputedReach": ("Length", 18),
            }
            for name, (kind, value) in definitions.items():
                bag.addProperty("App::Property" + kind, name, "Shape", "Native " + name)
                setattr(bag, name, value)
            bag.setExpression("ComputedReach", "Reach * 2")
            bag.setEditorMode("ComputedReach", 1)
            bag.setExpression("Diameter", "CuttingSpan")
            bag.setEditorMode("Diameter", 1)
            body = document.addObject("PartDesign::Body", "Body")
            body.Label = "UnregisteredUserAuthoredTool"
            body.Group = list(body.Group) + [bag]
            body.setExpression("Placement.Base.x", "PropertyBag.Compensation == 1 ? -PropertyBag.CuttingSpan : 0 mm")
            block = body.newObject("PartDesign::AdditiveBox", "CuttingBody")
            for name, expression in (("Length", "CuttingSpan"), ("Width", "Thickness"), ("Height", "Reach")):
                block.setExpression(name, "PropertyBag." + expression)
            document.recompute()
            path = Path(directory) / "user_authored.fcstd"
            document.saveAs(str(path))
            return path
        finally:
            FreeCAD.closeDocument(document.Name)
            FreeCAD.setActiveDocument(active.Name if active else "")

    def test_custom_editor_discovers_native_properties_without_registration(self):
        from tempfile import TemporaryDirectory

        from PySide import QtGui
        from PathTurnToolLibrary import PathTurnAdapter as assets
        from PathTurnToolLibrary.PathTurnToolGui import CustomToolDialog

        application = QtGui.QApplication.instance() or QtGui.QApplication([])
        with TemporaryDirectory() as directory:
            snapshot = assets.custom_tool_preset(self._custom_shape_file(directory))
            self.assertNotIn("EdgeLength", snapshot.fields)
            self.assertNotIn("Rotation", snapshot.fields)
            self.assertEqual(snapshot.fields["Finish"]["choices"], ("Rough", "Fine"))
            self.assertTrue(snapshot.fields["ComputedReach"]["readonly"])
            dialog = CustomToolDialog(snapshot)
            try:
                self.assertTrue(dialog.save_button.isEnabled(), dialog.problem.text())
                self.assertIsInstance(dialog.controls["Relieved"], QtGui.QCheckBox)
                self.assertIsInstance(dialog.controls["Steps"], QtGui.QSpinBox)
                self.assertIsInstance(dialog.controls["Finish"], QtGui.QComboBox)
                self.assertTrue(dialog.controls["ComputedReach"].isReadOnly())
                dialog.controls["Reach"].setText("11 mm")
                dialog.controls["Compensation"].setCurrentText("Back datum")
                dialog.controls["Finish"].setCurrentText("Fine")
                dialog.controls["Relieved"].setChecked(False)
                dialog._refresh_preview()
                self.assertTrue(dialog.save_button.isEnabled(), dialog.problem.text())
                self.assertIn("22", dialog.controls["ComputedReach"].text())
                self.assertEqual(dialog.values()["Finish"], "Fine")
                self.assertFalse(dialog.values()["Relieved"])
                self.assertLess(min(point[0] for edge in dialog.preview.outlines for point in edge), -4.99)
                original = dialog.values()
                dialog.flip_x_view.setChecked(True)
                self.assertEqual(dialog.values(), original)
                dialog.controls["Reach"].setText("invalid")
                dialog._refresh_preview()
                self.assertFalse(dialog.save_button.isEnabled())
                application.processEvents()
            finally:
                dialog.reject()

    def test_custom_native_parameters_survive_copy_and_reopen(self):
        from tempfile import TemporaryDirectory

        import FreeCAD
        from PathTurnScripts.PathTurnToolBit import create_tool
        from PathTurnToolLibrary import PathTurnAdapter as assets

        active = FreeCAD.ActiveDocument
        documents = []
        try:
            with TemporaryDirectory() as directory:
                path = self._custom_shape_file(directory)
                snapshot = assets.custom_tool_preset(path)
                document = FreeCAD.newDocument("UserCustomInstance")
                documents.append(document.Name)
                tool = create_tool(path, snapshot.attributes, document)
                tool.Reach = "11 mm"
                tool.Finish = "Fine"
                tool.ToolPost = "Rear"
                document.recompute()
                self.assertAlmostEqual(tool.Shape.BoundBox.ZMax, 11)
                self.assertAlmostEqual(tool.ComputedReach.Value, 22)
                copied_document = FreeCAD.newDocument("UserCustomCopy")
                documents.append(copied_document.Name)
                copied = copied_document.copyObject(tool, True)
                copied_document.recompute()
                self.assertAlmostEqual(copied.Shape.BoundBox.ZMax, 11)
                FreeCAD.closeDocument(documents.pop())
                FreeCAD.setActiveDocument(document.Name)
                name = tool.Name
                for _attempt in range(2):
                    document.saveAs(directory + "/instance.fcstd")
                    FreeCAD.closeDocument(documents.pop())
                    document = FreeCAD.openDocument(directory + "/instance.fcstd", hidden=True)
                    documents.append(document.Name)
                    tool = document.getObject(name)
                    self.assertEqual(tool.Finish, "Fine")
                    self.assertEqual(tool.ToolPost, "Rear")
                    self.assertEqual(tool.getEnumerationsOfProperty("Compensation"), ["Profile datum", "Back datum"])
                    self.assertEqual(tool.getEnumerationsOfProperty("Finish"), ["Rough", "Fine"])
                    self.assertIn("ReadOnly", tool.getEditorMode("ComputedReach"))
                    self.assertAlmostEqual(tool.ComputedReach.Value, tool.Reach.Value * 2)
                    tool.Reach = "12 mm"
                    document.recompute()
                    self.assertAlmostEqual(tool.Shape.BoundBox.ZMax, 12)
                    self.assertAlmostEqual(tool.ComputedReach.Value, 24)
        finally:
            for name in reversed(documents):
                FreeCAD.closeDocument(name)
            FreeCAD.setActiveDocument(active.Name if active else "")

    def test_custom_assets_preserve_metadata_units_and_stale_checks(self):
        import json
        from tempfile import TemporaryDirectory
        from types import SimpleNamespace
        from unittest.mock import patch

        from PathTurnToolLibrary import PathTurnAdapter as assets

        stored = {}
        fake = SimpleNamespace(
            exists=lambda uri, **kwargs: str(uri) in stored,
            get_raw=lambda uri, **kwargs: stored[str(uri)],
            add_raw=lambda kind, identity, data, **kwargs: stored.__setitem__(
                str(assets.AssetUri.build(asset_type=kind, asset_id=identity)), data),
        )
        with TemporaryDirectory() as directory, patch.object(assets, "cam_assets", fake):
            snapshot = assets.custom_tool_preset(self._custom_shape_file(directory))
            snapshot.attributes["parameter"]["CuttingSpan"] = "0.5 in"
            snapshot.attributes["attribute"]["supplier"] = {"keep": [1, 2]}
            snapshot = assets._custom_snapshot("", snapshot.attributes, snapshot.shape_data)
            entry = assets.create_custom_tool(snapshot, 17)
            table = ToolLibrary()
            table.add(entry)
            self.assertEqual(table.get(17).tool_id, entry.tool_id)
            library_uri = assets.AssetUri.build(asset_type="toolbitlibrary", asset_id="custom-membership")
            stored[str(library_uri)] = json.dumps({"version": 1, "tools": []}).encode()
            library = assets.load_library(library_uri)
            saved_library = assets.save_library(library, table)
            self.assertEqual(saved_library.table.get(17), entry)
            self.assertEqual(assets.load_library(library_uri).table.get(17), entry)
            loaded = assets.load_tool_definition(entry.tool_id)
            before_noop = dict(stored)
            self.assertIs(assets.save_custom_tool(loaded, loaded.values), loaded)
            self.assertEqual(stored, before_noop)
            updated = assets.save_custom_tool(loaded, dict(loaded.values, name="Edited custom tool", Reach="11 mm"))
            self.assertEqual(updated.attributes["parameter"]["CuttingSpan"], "0.5 in")
            self.assertEqual(updated.attributes["attribute"], snapshot.attributes["attribute"])
            self.assertEqual(updated.attributes["shape"], snapshot.attributes["shape"])
            self.assertEqual(stored[str(assets._reference("toolbitshape", updated.attributes["shape"]))], snapshot.shape_data)
            with self.assertRaisesRegex(ValueError, "changed since loading"):
                assets.save_custom_tool(loaded, loaded.values)
            before_invalid = dict(stored)
            for values in (dict(updated.values, Finish="Not a file choice"),
                           dict(updated.values, Reach="-1 mm"),
                           dict(updated.values, ComputedReach="100 mm")):
                with self.subTest(values=values):
                    with self.assertRaises((ValueError, RuntimeError)):
                        assets.save_custom_tool(updated, values)
                    self.assertEqual(stored, before_invalid)

    def test_custom_tool_job_assignment_supports_undo_redo(self):
        self._check_custom_tool_job_assignment()

    def test_iso_c_job_assignment_supports_undo_redo(self):
        self._check_custom_tool_job_assignment("C")

    def test_iso_d_job_assignment_supports_undo_redo(self):
        self._check_custom_tool_job_assignment("D")

    def test_iso_t_job_assignment_supports_undo_redo(self):
        self._check_custom_tool_job_assignment("T")

    def _check_custom_tool_job_assignment(self, shape_code=None):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from types import SimpleNamespace
        from unittest.mock import patch

        import FreeCAD
        import Part
        import Path.Main.Job as jobs
        from PathTurnToolLibrary import PathTurnAdapter as assets

        stored = {}
        fake = SimpleNamespace(
            exists=lambda uri, **kwargs: str(uri) in stored,
            get_raw=lambda uri, **kwargs: stored[str(uri)],
            add_raw=lambda kind, identity, data, **kwargs: stored.__setitem__(
                str(assets.AssetUri.build(asset_type=kind, asset_id=identity)), data),
        )
        active = FreeCAD.ActiveDocument
        document = FreeCAD.newDocument("CustomToolJob")
        document.UndoMode = 1
        try:
            with TemporaryDirectory() as directory, patch.object(assets, "cam_assets", fake):
                shape_path = (Path(__file__).resolve().parents[1] / f"Tools/Shape/Iso_{shape_code}.fcstd"
                              if shape_code else self._custom_shape_file(directory))
                snapshot = assets.custom_tool_preset(shape_path)
                entry = assets.create_custom_tool(snapshot, 17)
                model = document.addObject("Part::Feature", "Model")
                model.Shape = Part.makeBox(20, 20, 20)
                job = jobs.Create("Job", [model], None)
                document.recompute()
                if document.HasPendingTransaction:
                    document.commitTransaction()
                before = dict(stored)
                controller = assets.add_to_job(entry, document.Name, job.Name)
                name = controller.Name
                self.assertEqual(controller.ToolNumber, 17)
                self.assertIn(controller, job.Tools.Group)
                self.assertGreater(float(controller.Tool.Diameter), 0)
                self.assertEqual(controller.Tool.Compensation, snapshot.values["Compensation"])
                self.assertEqual(controller.Tool.ToolPost, "Front")
                self.assertTrue(controller.Tool.Shape.isValid())
                self.assertEqual(stored, before)
                document.undo()
                self.assertIsNone(document.getObject(name))
                document.redo()
                document.recompute()
                restored = document.getObject(name)
                self.assertEqual(restored.ToolNumber, 17)
                enum_name = "EdgeLength" if shape_code else "Finish"
                self.assertEqual(restored.Tool.getEnumerationsOfProperty(enum_name),
                                 list(snapshot.fields[enum_name]["choices"]))
                self.assertTrue(restored.Tool.Shape.isValid())
                self.assertEqual(stored, before)
                from PathTurnScripts import PathTurnFace

                with (
                    patch.object(PathTurnFace.ObjectTurnFace, "opExecute", return_value=None) as execute,
                    patch.object(PathTurnFace.PathTurnBase.PathUtils, "findToolController", return_value=restored),
                ):
                    operation = PathTurnFace.Create("CustomToolExecution", parentJob=job)
                    operation.ToolController = restored
                    execute.reset_mock()
                    operation.Proxy.execute(operation)
                    execute.assert_called_with(operation)
                    self.assertAlmostEqual(operation.OpToolDiameter.Value, restored.Tool.Diameter.Value)
        finally:
            FreeCAD.closeDocument(document.Name)
            FreeCAD.setActiveDocument(active.Name if active else "")

    def test_custom_templates_require_native_cam_diameter(self):
        from tempfile import TemporaryDirectory

        import FreeCAD
        from PathTurnToolLibrary import PathTurnAdapter as assets

        active = FreeCAD.ActiveDocument
        try:
            with TemporaryDirectory() as directory:
                path = self._custom_shape_file(directory)
                for kind, value in ((None, None), ("App::PropertyLength", 0),
                                    ("App::PropertyFloat", 2)):
                    with self.subTest(kind=kind, value=value):
                        document = FreeCAD.openDocument(str(path), hidden=True)
                        try:
                            bag = document.getObjectsByLabel("Attributes")[0]
                            bag.setExpression("Diameter", None)
                            bag.removeProperty("Diameter")
                            if kind:
                                bag.addProperty(kind, "Diameter", "Shape")
                                bag.Diameter = value
                            document.recompute()
                            invalid = directory + "/invalid.fcstd"
                            document.saveAs(invalid)
                        finally:
                            FreeCAD.closeDocument(document.Name)
                        with self.assertRaisesRegex(ValueError, "Diameter"):
                            assets.custom_tool_preset(invalid)
                snapshot = assets.custom_tool_preset(path)
                self.assertTrue(snapshot.fields["Diameter"]["readonly"])
                geometry = assets.custom_tool_preview(snapshot, dict(snapshot.values, CuttingSpan="6 mm"))
                self.assertIn("6", geometry["calculated"]["Diameter"])
        finally:
            FreeCAD.setActiveDocument(active.Name if active else "")

    def test_active_gui_edit_still_blocks_job_addition(self):
        from types import SimpleNamespace
        from unittest.mock import patch

        import FreeCAD
        from PathTurnToolLibrary import PathTurnAdapter as assets

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
        from PathTurnToolLibrary import PathTurnAdapter as assets

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
                self.assertIsNone(assets.job_add_problem(document.Name, "Job", 12))
            self.assertTrue(document.HasPendingTransaction)
        finally:
            document.abortTransaction()
            FreeCAD.closeDocument(document.Name)
            FreeCAD.setActiveDocument(active.Name if active else "")

    def test_add_to_job_revalidates_when_current_tool_changes(self):
        from types import SimpleNamespace
        from unittest.mock import patch

        from PySide import QtGui
        from PathTurnToolLibrary import PathTurnAdapter as assets
        from PathTurnToolLibrary.PathTurnToolGui import LibraryDialog

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

    def test_operation_maps_post_to_enum_and_restores_outline(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        from liblathe.base.point import Point
        from liblathe.base.segment import Segment
        from liblathe.tool.tool import ToolSide
        from PathTurnScripts import PathTurnBase

        outline = [Segment(Point(12, 0), Point(10, -5), 0.2)]
        insert = [Segment(Point(0, 0), Point(1, 1))]
        proxy = SimpleNamespace(part_outline=outline)
        for post, side, radial in (("Front", ToolSide.NEAR, 12), ("Rear", ToolSide.FAR, -12)):
            obj = SimpleNamespace(ToolController=SimpleNamespace(Tool=SimpleNamespace(
                Compensation="Tip Tangent", ToolPost=post, Shape=object())))

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



if __name__ == "__main__":
    unittest.main()
