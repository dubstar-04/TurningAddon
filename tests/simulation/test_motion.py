import unittest

from PathTurnSimulation.dexel.motion import sample_turning, sample_turning_moves, sample_turning_path


class TurningMotionTests(unittest.TestCase):
    def test_coordinate_free_commands_do_not_locate_tool(self):
        for name in ("G0", "G00", "G1", "G01"):
            for params in ({}, {"F": 100}):
                for locating_name, rapid in (("G0", True), ("G1", False)):
                    with self.subTest(name=name, params=params, locating_name=locating_name):
                        commands = [
                            (name, params),
                            (locating_name, {"X": -4, "Z": 2}),
                            ("G1", {"Z": 4}),
                        ]
                        expected = [
                            ((-4, 0, 2), rapid),
                            ((-4, 0, 3), False),
                            ((-4, 0, 4), False),
                        ]
                        initial = (2, 0, -1)
                        self.assertEqual(
                            sample_turning_path(commands, 1, initial), (expected, [1, 3]))
                        self.assertEqual(sample_turning_moves(commands, 1, initial), expected)
                        self.assertEqual(
                            sample_turning(commands, 1, initial),
                            [point for point, _ in expected])

    def test_only_coordinate_free_commands_produce_no_samples_or_boundaries(self):
        commands = [(name, {"F": 100}) for name in ("G0", "G00", "G1", "G01")]
        self.assertEqual(sample_turning_path(commands, 1), ([], []))

    def test_feed_only_commands_between_moves_do_not_add_boundaries(self):
        commands = [
            ("G0", {"X": 4, "Z": 2}),
            ("G1", {"F": 100}),
            ("G1", {"Z": 4}),
        ]
        self.assertEqual(sample_turning_path(commands, 1), ([
            ((4, 0, 2), True),
            ((4, 0, 3), False),
            ((4, 0, 4), False),
        ], [1, 3]))

    def test_first_coordinate_move_preserves_modal_and_initial_coordinates(self):
        for params, expected in (
            ({"X": 8, "Z": 2}, (5, 0, 3)),
            ({"Z": 2}, (1, 0, 3)),
            ({"X": 0}, (1, 0, 1)),
            ({"Y": 0}, (1, 0, 1)),
        ):
            with self.subTest(params=params):
                commands = [
                    ("G1", {"F": 100}),
                    ("G91", {}),
                    ("G7", {}),
                    ("G1", params),
                ]
                self.assertEqual(
                    sample_turning_path(commands, 1, initial=(1, 0, 1)),
                    ([(expected, False)], [1]))


if __name__ == "__main__":
    unittest.main()
