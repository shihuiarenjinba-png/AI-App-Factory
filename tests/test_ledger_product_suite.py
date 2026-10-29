"""Exercise the real File Integrity Ledger product suite in Factory CI.

Runs in a child process to keep product-local 'main' imports isolated from
other Factory and cohort tests. No GUI/display, network or external API needed.
"""
from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]


class FileIntegrityLedgerProductTests(unittest.TestCase):
    def test_headless_product_suite(self):
        completed = subprocess.run(
            [
                sys.executable, "-m", "unittest", "discover",
                "-s", "products/file-integrity-ledger/tests", "-v",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=90,
            check=False,
        )
        self.assertEqual(
            completed.returncode, 0,
            completed.stdout + "\n" + completed.stderr,
        )


if __name__ == "__main__":
    unittest.main()
