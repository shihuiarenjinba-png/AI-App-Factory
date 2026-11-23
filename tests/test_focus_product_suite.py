"""Run Focus Session Desk's real headless product suite in Factory CI.

A child process isolates the product-local main import from other tests.
No GUI/display, network, API key, or Windows installation is needed.
"""
from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]


class FocusSessionProductTests(unittest.TestCase):
    def test_headless_product_suite(self):
        completed = subprocess.run(
            [sys.executable, "-m", "unittest", "discover",
             "-s", "products/focus-session-desk/tests", "-v"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=90,
            check=False,
        )
        self.assertEqual(completed.returncode, 0,
                         completed.stdout + "\n" + completed.stderr)


if __name__ == "__main__":
    unittest.main()
