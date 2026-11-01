"""Run JP freelance budget fixtures in Factory CI on Linux and Windows."""
from pathlib import Path
import subprocess
import sys
import unittest


class TestJPFreelanceBudget(unittest.TestCase):
    def test_product_budget_suite(self):
        root = Path(__file__).resolve().parents[1]
        product = root / "products" / "jp-freelance-ledger"
        result = subprocess.run(
            [sys.executable, "-m", "unittest", "discover", "-s", str(product / "tests"),
             "-p", "test_budget.py", "-v"],
            cwd=product, capture_output=True, text=True, timeout=30, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + "\n" + result.stderr)
        self.assertIn("Ran 8 tests", result.stderr)


if __name__ == "__main__":
    unittest.main()
