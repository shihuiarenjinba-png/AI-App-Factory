"""Run JP freelance balance-check fixtures in Factory core CI on both OSes."""
from pathlib import Path
import subprocess
import sys
import unittest


class TestJPFreelanceMonthlyBalance(unittest.TestCase):
    def test_product_balance_suite(self):
        root = Path(__file__).resolve().parents[1]
        product = root / "products" / "jp-freelance-ledger"
        result = subprocess.run(
            [sys.executable, "-m", "unittest", "discover", "-s", str(product / "tests"),
             "-p", "test_reconciliation.py", "-v"],
            cwd=product, capture_output=True, text=True, timeout=30, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + "\n" + result.stderr)
        self.assertIn("Ran 6 tests", result.stderr)


if __name__ == "__main__": unittest.main()
