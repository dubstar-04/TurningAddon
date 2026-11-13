import unittest
from unittest.mock import patch

from PathTurnSimulation.dexel import DexelGrid, RevolvedTool, TurningTool


class MillingSegmentTests(unittest.TestCase):
    def test_centreline_drill_removes_only_its_revolved_profile(self):
        grid = DexelGrid.cylinder(6, 10, 0.5)
        tool = TurningTool([(-4, 2), (0, 0), (4, 2), (4, 40), (-4, 40)])
        self.assertEqual(grid.cut_turning(tool, 1, (0, 13), (0, 13)), 0)
        self.assertGreater(grid.cut_turning(tool, 1, (0, 13), (0, 3)), 0)
        for j in range(grid.ny):
            for i in range(grid.nx):
                radius = ((grid.xmin + (i + 0.5) * grid.dx) ** 2
                          + (grid.ymin + (j + 0.5) * grid.dy) ** 2) ** 0.5
                c = j * grid.nx + i
                if radius < 4:
                    self.assertAlmostEqual(grid.hi[c], 3 + radius / 2)
                    self.assertEqual(grid.hi_id[c], 1)
                elif radius < 6:
                    self.assertEqual(grid.hi[c], 10)
                    self.assertEqual(grid.hi_id[c], 0)

    def test_turning_axis_crossing_preserves_separate_axial_intervals(self):
        grid = DexelGrid.cylinder(4, 10, 0.5)
        tool = TurningTool([(-3, 1), (-3, 2), (3, 8), (3, 7)])
        self.assertGreater(grid.cut_turning(tool, 1, (0, 0), (0, 0)), 0)
        for j in range(grid.ny):
            for i in range(grid.nx):
                radius = ((grid.xmin + (i + 0.5) * grid.dx) ** 2
                          + (grid.ymin + (j + 0.5) * grid.dy) ** 2) ** 0.5
                c = j * grid.nx + i
                if 1 < radius < 3:
                    intervals = grid.multi[c]
                    self.assertEqual(len(intervals), 3)
                    self.assertAlmostEqual(intervals[0][1], 4 - radius)
                    self.assertAlmostEqual(intervals[1][0], 5 - radius)
                    self.assertAlmostEqual(intervals[1][1], 4 + radius)
                    self.assertAlmostEqual(intervals[2][0], 5 + radius)
                elif 3 < radius < 4:
                    self.assertEqual(grid.lo[c], 0)
                    self.assertEqual(grid.hi[c], 10)
        self.assertTrue(grid.multi)

    def test_vertical_move_reaches_exact_lowest_endpoint(self):
        for tool in (RevolvedTool.flat(1), RevolvedTool.ball(1)):
            for start_z, end_z in ((4, 2), (2, 4)):
                with self.subTest(flat=tool.is_flat, start_z=start_z):
                    grid = DexelGrid((0, 0, 0, 3, 3, 6), resolution=1)
                    grid.extract()
                    changed = grid.cut_segment(
                        tool, 7, (1.5, 1.5, start_z), (1.5, 1.5, end_z))
                    self.assertGreater(changed, 0)
                    for j in range(grid.ny):
                        for i in range(grid.nx):
                            radius = ((i - 1) ** 2 + (j - 1) ** 2) ** 0.5
                            c = j * grid.nx + i
                            if radius <= tool.radius:
                                self.assertEqual(grid.hi[c], 2 + tool.bottom(radius))
                                self.assertEqual(grid.hi_id[c], 7)
                                self.assertEqual(grid.touch[c], 7)
                            else:
                                self.assertEqual(grid.hi[c], 6)
                    self.assertTrue(grid._dirty)
                    triangles, ids = grid.extract()
                    self.assertIn(7, ids)
                    self.assertIn(
                        2, [z for triangle in triangles for z in triangle[2::3]])

    def test_finite_tool_reaches_exact_upper_endpoint(self):
        for start_z, end_z in ((4, 2), (2, 4)):
            with self.subTest(start_z=start_z):
                grid = DexelGrid((0, 0, 0, 1, 1, 6), resolution=1)
                tool = RevolvedTool.flat(1, length=1)
                grid.cut_segment(tool, 7, (0.5, 0.5, start_z), (0.5, 0.5, end_z))
                self.assertEqual(grid.multi[0], [[0, 2, 0, 7], [5, 6, 7, 0]])
                self.assertEqual(grid.volume(), 3)

    def test_sloped_move_cuts_endpoints_only_at_their_xy_positions(self):
        for reverse in (False, True):
            with self.subTest(reverse=reverse):
                grid = DexelGrid((0, 0, 0, 5, 1, 6), resolution=1)
                tool = RevolvedTool.flat(0.5, length=0.5)
                start, end = (0.5, 0.5, 2), (4.5, 0.5, 4)
                if reverse:
                    start, end = end, start
                grid.cut_segment(tool, 7, start, end)
                self.assertEqual(grid.multi[0][0], [0, 2, 0, 7])
                self.assertEqual(grid.multi[4][-1], [4.5, 6, 7, 0])
                self.assertGreater(grid.multi[2][0][1], 2)
                self.assertLess(grid.multi[2][-1][0], 4.5)

    def test_z_changing_move_keeps_midpoint_pieces(self):
        grid = DexelGrid((0, 0, 0, 1, 1, 6), resolution=1)
        tool = RevolvedTool.flat(1)
        with patch.object(grid, "_cut_piece", wraps=grid._cut_piece) as cut:
            changed = grid.cut_segment(tool, 7, (0.5, 0.5, 4), (0.5, 0.5, 2))
        self.assertEqual(cut.call_count, 10)
        heights = [call.args[-1] for call in cut.call_args_list]
        self.assertEqual(sorted(heights), [2] + [2.125 + i * 0.25 for i in range(8)] + [4])
        self.assertGreater(changed, 0)

    def test_constant_z_moves_do_not_add_endpoint_cuts(self):
        for end in ((0.5, 0.5, 2), (1.5, 0.5, 2)):
            with self.subTest(end=end):
                grid = DexelGrid((0, 0, 0, 2, 1, 6), resolution=1)
                tool = RevolvedTool.flat(1)
                with patch.object(grid, "_cut_piece", wraps=grid._cut_piece) as cut:
                    grid.cut_segment(tool, 7, (0.5, 0.5, 2), end)
                cut.assert_called_once_with(tool, 7, 0.5, 0.5, end[0], end[1], 2)


class SurfaceOwnershipTests(unittest.TestCase):
    def wall_faces(self, grid, axis, coordinate):
        triangles, owners = grid.extract()
        return [(min(triangle[2::3]), max(triangle[2::3]), owner)
                for triangle, owner in zip(triangles, owners)
                if all(abs(value - coordinate) < 1e-9 for value in triangle[axis::3])]

    def test_separate_cuts_keep_their_wall_colours(self):
        for axis in (0, 1):
            with self.subTest(axis=axis):
                bounds = (0, 0, 0, 2, 1, 10) if axis == 0 else (0, 0, 0, 1, 2, 10)
                grid = DexelGrid(bounds, 1)
                tool = RevolvedTool.flat(0.49, length=1)
                position = (1.5, 0.5) if axis == 0 else (0.5, 1.5)
                for owner, z in ((1, 2), (2, 6)):
                    point = (*position, z)
                    grid.cut_segment(tool, owner, point, point)
                    walls = self.wall_faces(grid, axis, 1)
                    self.assertIn((2, 3, 1), walls)
                self.assertIn((6, 7, 2), walls)
                self.assertEqual(self.wall_faces(grid, axis, 1), walls)

    def test_adjacent_removed_ranges_split_wall_by_operation(self):
        for axis in (0, 1):
            for reverse in (False, True):
                with self.subTest(axis=axis, reverse=reverse):
                    bounds = (0, 0, 0, 2, 1, 10) if axis == 0 else (0, 0, 0, 1, 2, 10)
                    grid = DexelGrid(bounds, 1)
                    coordinate = 0.5 if reverse else 1.5
                    position = (coordinate, 0.5) if axis == 0 else (0.5, coordinate)
                    tool = RevolvedTool.flat(0.49, length=2)
                    for owner, z in ((1, 2), (2, 4), (3, 0), (4, 6), (5, 8)):
                        point = (*position, z)
                        grid.cut_segment(tool, owner, point, point)
                        grid.extract()
                    walls = self.wall_faces(grid, axis, 1)
                    for expected in ((0, 2, 3), (2, 4, 1), (4, 6, 2), (6, 8, 4), (8, 10, 5)):
                        self.assertEqual(walls.count(expected), 2)
                    self.assertEqual(len(walls), 10)

    def test_air_cuts_do_not_recolour_and_same_owner_ranges_merge(self):
        grid = DexelGrid((0, 0, 0, 2, 1, 10), 1)
        tool = RevolvedTool.flat(0.49, length=1)
        for owner, z in ((1, 2), (1, 3), (2, 2)):
            point = (1.5, 0.5, z)
            grid.cut_segment(tool, owner, point, point)
        self.assertEqual(grid.removed[1], [(2, 4, 1)])
        self.assertEqual(self.wall_faces(grid, 0, 1), [(2, 4, 1)] * 2)
        for coordinate in (0, 2):
            self.assertTrue(all(owner == 0 for _, _, owner in self.wall_faces(grid, 0, coordinate)))

    def test_tolerance_snapped_removals_keep_complete_wall_ownership(self):
        grid = DexelGrid((0, 0, 0, 2, 1, 10), 1)
        tool = RevolvedTool.flat(0.49, length=10 - grid.tolerance)
        point = (1.5, 0.5, grid.tolerance / 2)
        grid.cut_segment(tool, 3, point, point)
        self.assertEqual(grid.removed[1], [(0, 10, 3)])
        self.assertEqual(self.wall_faces(grid, 0, 1), [(0, 10, 3)] * 2)

    def test_tiny_ownership_boundary_does_not_leave_a_mesh_gap(self):
        grid = DexelGrid((0, 0, 0, 2, 1, 10), 1)
        tool = RevolvedTool.flat(0.49, length=2)
        for owner, z in ((1, 2), (2, 4)):
            point = (1.5, 0.5, z)
            grid.cut_segment(tool, owner, point, point)
        height = 4 - grid.tolerance / 2
        tool = RevolvedTool.flat(0.49, length=height)
        point = (0.5, 0.5, 0)
        grid.cut_segment(tool, 3, point, point)
        walls = self.wall_faces(grid, 0, 1)
        self.assertIn((height, 6, 2), walls)
        self.assertTrue(all(high - low > grid.tolerance for low, high, _ in walls))

    def test_turning_grooves_keep_separate_surface_owners(self):
        grid = DexelGrid.cylinder(3, 10, 0.5)
        tool = TurningTool([(0, 0), (2, 0), (2, 1), (0, 1)])
        first = (2, 2)
        grid.cut_turning(tool, 1, first, first)
        triangles, owners = grid.extract()
        original = {triangle: owner for triangle, owner in zip(triangles, owners)
                    if owner == 1}
        self.assertTrue(original)
        second = (2, 6)
        grid.cut_turning(tool, 2, second, second)
        triangles, owners = grid.extract()
        current = dict(zip(triangles, owners))
        for triangle, owner in original.items():
            self.assertEqual(current[triangle], owner)
        walls = [(min(t[2::3]), max(t[2::3]), owner)
                 for t, owner in zip(triangles, owners)
                 if max(t[2::3]) > min(t[2::3])]
        self.assertTrue(any(low == 2 and high == 3 and owner == 1 for low, high, owner in walls))
        self.assertTrue(any(low == 6 and high == 7 and owner == 2 for low, high, owner in walls))
        self.assertTrue(all(owner == 0 for low, high, owner in walls if low == 0 and high == 10))


if __name__ == "__main__":
    unittest.main()
