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


if __name__ == "__main__":
    unittest.main()