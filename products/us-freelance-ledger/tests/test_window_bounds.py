"""Protect the first-run bank-check controls from Windows taskbar clipping."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

PRODUCT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PRODUCT))
import main


class WindowBoundsTests(unittest.TestCase):
    def test_windows_1024_by_720_reserves_decorated_frame(self):
        with patch.object(main.sys, "platform", "win32"):
            geometry, min_width, min_height = main._window_bounds((0, 0, 1024, 720))
        self.assertEqual(geometry, "960x624+32+48")
        self.assertEqual((min_width, min_height), (900, 620))
        # The 16x39 outer-frame overhead observed on Windows hosted at 100%.
        self.assertLessEqual(32 + 960 + 16, 1024)
        self.assertLessEqual(48 + 624 + 39, 720)

    def test_windows_offset_work_area_keeps_margins(self):
        with patch.object(main.sys, "platform", "win32"):
            geometry, minimum_w, minimum_h = main._window_bounds((100, 50, 1024, 720))
        self.assertEqual(geometry, "960x624+132+98")
        self.assertEqual((minimum_w, minimum_h), (900, 620))

    def test_nonwindows_layout_remains_unchanged(self):
        with patch.object(main.sys, "platform", "linux"):
            geometry, _, _ = main._window_bounds((0, 0, 1024, 720))
        self.assertEqual(geometry, "1000x696+12+12")

    def test_invalid_area_rejected(self):
        with self.assertRaises(ValueError):
            main._window_bounds((0, 0, 1024, 0))


if __name__ == "__main__":
    unittest.main()
