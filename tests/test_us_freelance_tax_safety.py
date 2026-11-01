"""Boundary tests for US-only manual tax arithmetic; not a tax certification."""
import importlib.util
import sys
import unittest
from pathlib import Path

PATH = Path(__file__).resolve().parents[1] / "products/us-freelance-ledger/tax_assets.py"
spec = importlib.util.spec_from_file_location("us_fl_tax_validation", PATH)
tax = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = tax
spec.loader.exec_module(tax)


class TaxSafetyTests(unittest.TestCase):
    def test_valid_manual_sales_tax(self):
        result = tax.manual_sales_tax("100.00", "7.25")
        self.assertEqual(str(result["gross"]), "107.25")

    def test_nonfinite_and_invalid_rates_rejected(self):
        for amount, rate in [("NaN", "5"), ("Infinity", "5"), ("10", "NaN"),
                             ("10", "-1"), ("10", "101")]:
            with self.subTest(amount=amount, rate=rate):
                with self.assertRaises(ValueError):
                    tax.manual_sales_tax(amount, rate)
        with self.assertRaises(ValueError):
            tax.manual_sales_tax("10", "5", rounding="not-a-mode")

    def test_manual_tax_schedule_bounds(self):
        valid = tax.custom_tax_depreciation_schedule(
            "1000", {2026: "40", 2027: "60"}, business_use_percent=75
        )
        self.assertEqual(sum(r["tax_depreciation"] for r in valid), 1000)
        self.assertEqual(sum(r["business_depreciation"] for r in valid), 750)
        for schedule in ({2026: "70", 2027: "50"}, {2026: "NaN"},
                         {2026: "-1"}, {2026: "101"}, {"not-year": "10"}):
            with self.subTest(schedule=schedule):
                with self.assertRaises(ValueError):
                    tax.custom_tax_depreciation_schedule("1000", schedule)
        with self.assertRaises(ValueError):
            tax.custom_tax_depreciation_schedule("1000", {2026: "10"}, 101)

    def test_book_depreciation_validation(self):
        rows = tax.straight_line_book_schedule("1200", "2026-01-01", 2)
        self.assertEqual(sum(r["book_depreciation"] for r in rows), 1200)
        for kwargs in ({"cost": "NaN"}, {"salvage_value": "Infinity"},
                       {"business_use_percent": 101}, {"useful_life_years": "2.5"}):
            with self.subTest(kwargs=kwargs):
                args = dict(cost="1200", first_use_date="2026-01-01", useful_life_years=2)
                args.update(kwargs)
                with self.assertRaises(ValueError):
                    tax.straight_line_book_schedule(**args)

    def test_official_url_must_have_irs_hostname(self):
        accepted = tax.require_tax_profile(
            "https://www.irs.gov/publications/p946", 2026, "Manual review"
        )
        self.assertTrue(accepted["review_required"])
        for url in ("https://fake.example/?source=irs.gov",
                    "https://irs.gov.evil.example/p946",
                    "http://irs.gov/publications/p946",
                    "https://irs.gov@evil.example/publications/p946"):
            with self.subTest(url=url):
                with self.assertRaises(ValueError):
                    tax.require_tax_profile(url, 2026, "Manual review")


if __name__ == "__main__":
    unittest.main()
