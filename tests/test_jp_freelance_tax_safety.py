"""Run JP freelance tax and retroactive fixtures in Factory CI."""
from pathlib import Path
import subprocess
import sys
import unittest


class TestJPFreelanceTaxSafety(unittest.TestCase):
    def test_product_tax_safety_suite(self):
        root = Path(__file__).resolve().parents[1]
        product = root / "products" / "jp-freelance-ledger"
        result = subprocess.run(
            [sys.executable, "-m", "unittest", "discover", "-s", str(product / "tests"),
             "-p", "test_tax_safety.py", "-v"],
            cwd=product, capture_output=True, text=True, timeout=30, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + "\n" + result.stderr)
        self.assertIn("Ran 7 tests", result.stderr)


if __name__ == "__main__":
    unittest.main()
