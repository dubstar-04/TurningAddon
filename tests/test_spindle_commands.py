import unittest

from PathTurnScripts.PathTurnSpindle import CSS, RPM, spindle_commands


class SpindleCommandTests(unittest.TestCase):
    def test_css_sets_surface_speed_and_restores_fixed_rpm(self):
        self.assertEqual(
            spindle_commands(CSS, True, 1200, 180, 2500, 3000),
            (
                ("G96", {"S": 180, "D": 2500}),
                ("G97", {"S": 1200}),
            ),
        )

    def test_rpm_mode_does_not_add_spindle_commands(self):
        self.assertEqual(spindle_commands(RPM, True, 0, 0, 0), ())

    def test_css_on_fixed_rpm_only_operation_emits_g97(self):
        self.assertEqual(
            spindle_commands(CSS, False, 1200, 0, 0, 3000),
            (("G97", {"S": 1200}),),
        )

    def test_css_requires_valid_speed_and_rpm_limits(self):
        cases = (
            (CSS, True, 1200, 0, 2500, 3000),
            (CSS, True, 1200, float("nan"), 2500, 3000),
            (CSS, True, 1200, 180, 0, 3000),
            (CSS, True, 0, 180, 2500, 3000),
            (CSS, True, float("inf"), 180, 2500, 3000),
            (CSS, True, 1200, 180, 3500, 3000),
            (CSS, True, 3500, 180, 3000, 3000),
        )
        for args in cases:
            with self.subTest(args=args), self.assertRaises(ValueError):
                spindle_commands(*args)

    def test_unknown_mode_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Unknown spindle"):
            spindle_commands("variable", True, 1200, 180, 2500, 3000)


if __name__ == "__main__":
    unittest.main()
