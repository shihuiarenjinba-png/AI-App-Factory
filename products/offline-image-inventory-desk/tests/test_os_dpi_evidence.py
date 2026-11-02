"""OS DPI evidence must never treat 100% or Tk text scaling as OS 125/150."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from os_dpi_evidence_windows import dpi_gate


class RealOsDpiGateTests(unittest.TestCase):
    def test_actual_target_125_and_150(self):
        self.assertTrue(dpi_gate(125, 120, 120, True))
        self.assertTrue(dpi_gate(150, 144, 144, True))

    def test_100_percent_is_not_scaled_os(self):
        self.assertFalse(dpi_gate(125, 96, 96, True))
        self.assertFalse(dpi_gate(150, 96, 96, True))

    def test_mismatch_and_virtualization_fail_closed(self):
        for system, monitor, aware in ((120, 96, True), (96, 120, True),
                                       (144, 120, True), (120, 120, False),
                                       (120, 120, None), (True, 120, True)):
            with self.subTest(system=system, monitor=monitor, aware=aware):
                self.assertFalse(dpi_gate(125, system, monitor, aware))

    def test_unsupported_target_rejected(self):
        with self.assertRaises(ValueError):
            dpi_gate(175, 168, 168, True)


if __name__ == "__main__":
    unittest.main()
