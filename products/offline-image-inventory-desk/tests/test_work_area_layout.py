"""Cross-platform contract: 1024x768 desktop with a 48px taskbar."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from main import window_geometry_for_work_area


class WorkAreaLayoutTests(unittest.TestCase):
    def test_1024x768_screen_with_taskbar(self):
        self.assertEqual(
            window_geometry_for_work_area(0, 0, 1024, 720),
            "1008x664+0+0",
        )

    def test_nonzero_monitor_origin(self):
        self.assertEqual(
            window_geometry_for_work_area(1920, 0, 2944, 720),
            "1008x664+1920+0",
        )

    def test_larger_work_area_is_bounded(self):
        self.assertEqual(
            window_geometry_for_work_area(0, 0, 1920, 1040),
            "1024x768+0+0",
        )

    def test_small_work_area_rejected_not_silently_clipped(self):
        for bounds in ((0, 0, 850, 720), (0, 0, 1024, 640)):
            with self.subTest(bounds=bounds), self.assertRaises(ValueError):
                window_geometry_for_work_area(*bounds)


if __name__ == "__main__":
    unittest.main()
