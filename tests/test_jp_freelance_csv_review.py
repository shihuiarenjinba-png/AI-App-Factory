"""Run JP freelance CSV import fixtures in Factory core CI on both OSes."""
from pathlib import Path
import subprocess
import sys
import unittest


class TestJPFreelanceCSVReview(unittest.TestCase):
    def test_product_csv_review_suite(self):
        root = Path(__file__).resolve().parents[1]
        tests = root / "products" / "jp-freelance-ledger" / "tests"
        result = subprocess.run(
            [sys.executable, "-m", "unittest", "discover", "-s", str(tests),
             "-p", "test_csv_review.py", "-v"],
            cwd=root / "products" / "jp-freelance-ledger",
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + "\n" + result.stderr)
        self.assertIn("Ran 6 tests", result.stderr)


if __name__ == "__main__":
    unittest.main()
