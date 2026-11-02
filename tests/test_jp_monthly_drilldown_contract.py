"""Run the JP monthly source-journal fixture on BOTH Factory Linux and Windows CI."""
from pathlib import Path
import subprocess
import sys
import unittest


class JPMonthEndWindowsContract(unittest.TestCase):
    def test_monthly_drilldown_product_fixture(self):
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            [sys.executable, "-m", "unittest", "discover",
             "-s", "products/jp-bookkeeping-desk/tests",
             "-p", "test_monthly_drilldown.py", "-v"],
            cwd=root, capture_output=True, text=True, timeout=90, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + "\n" + result.stderr)
        self.assertIn("Ran 1 test", result.stderr)


if __name__ == "__main__":
    unittest.main()
