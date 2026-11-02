"""Committed source smoke contract for the US-only pre-Identity Windows EXE builder.

This is not a Store approval, signed package or human acceptance test.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bank_csv_preview import BankCSVError, REQUIRED
from core import Store


class USLedgerSmokeTests(unittest.TestCase):
    def test_csv_review_is_explicit_and_usd_only(self):
        self.assertEqual(REQUIRED, ("date", "amount", "direction", "currency"))
        self.assertTrue(issubclass(BankCSVError, ValueError))

    def test_local_store_contract(self):
        self.assertTrue(callable(Store))


if __name__ == "__main__":
    unittest.main()
