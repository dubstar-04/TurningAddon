"""Run with FreeCADCmd -P /path/to/TurningAddon -t tests.test_turning_profiles."""

import unittest


class TurningProfileOffsetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import FreeCAD
            import Part
        except ModuleNotFoundError as error:
            if error.name not in ("FreeCAD", "Part"):
                raise
            raise unittest.SkipTest("Run geometry tests in FreeCADCmd.") from error
        from PathTurnScripts import PathTurnAddonHelpers

        cls.app = FreeCAD
        cls.part = Part
        cls.helpers = PathTurnAddonHelpers

    def setUp(self):
        body = self.part.makeCylinder(8, 20, self.app.Vector(0, 0, -20))
        boss = self.part.makeCylinder(2, 8, self.app.Vector(0, 8, -12))
        self.model = body.fuse(boss).removeSplitter()
        self.plane = self.part.makePlane(
            22, 15, self.app.Vector(0, 0, -21), self.app.Vector(0, 1, 0))

    def assert_containing_profile(self, profile):
        self.assertIsNotNone(profile)
        self.assertTrue(profile.isValid())
        self.assertTrue(self.helpers.profileContainsModel(profile, self.model))
        self.assertGreaterEqual(profile.BoundBox.XMax, 10)
        self.assertLessEqual(profile.BoundBox.XMax, 10.01)

    def test_native_offset_contains_an_off_axis_feature(self):
        section = self.model.common(self.plane)
        self.assert_containing_profile(
            self.helpers.getNativeProfile(self.model, section, self.plane, 0.01))

    def test_mesh_offset_contains_an_off_axis_feature(self):
        projected = self.helpers.getRadialMeshProjection(self.model, 0.00125)
        self.assert_containing_profile(
            self.helpers.getPositiveProfile(projected, self.plane))

    def test_operation_outline_includes_an_off_axis_feature(self):
        outline = self.helpers.getPartOutline((self.model,))
        self.assertTrue(outline)
        radius = max(segment.Boundbox().XMax for segment in outline)
        self.assertGreaterEqual(radius, 10)
        self.assertLessEqual(radius, 10.01)
        self.assertGreater(outline[0].start.Z, outline[-1].end.Z)
