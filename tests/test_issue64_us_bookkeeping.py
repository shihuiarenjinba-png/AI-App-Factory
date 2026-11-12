"""Issue #64: US Bookkeeping Desk IRS source fail-closed fixtures."""
import importlib.util
from pathlib import Path
import unittest

path = Path(__file__).resolve().parents[1] / "products/us-bookkeeping-desk/tax_assets.py"
spec = importlib.util.spec_from_file_location("bookkeeping_tax_assets", path)
tax = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tax)


class Issue64BookkeepingTests(unittest.TestCase):
    def test_reject_irs_spoofing_and_ambiguous_urls(self):
        invalid = [
            "https://irs.gov.evil.example/p946",
            "http://irs.gov/publications/p946",
            "https://irs.gov@evil.example/publications/p946",
            "https://irs.gov:invalid/publications/p946",
            "https://irs.gov:444/publications/p946",
            "https://irs.gov\\\\@evil.example/publications/p946",
            "https://irs.gov/publications/p946\\n",
            "https://irs.gov/publications/p946\\t",
            "https://irs.gov/publications/p946 ",
            "https://irs.gov/publications/p946\\x00",
        ]
        for url in invalid:
            with self.subTest(url=url), self.assertRaises(ValueError):
                tax.require_tax_profile(url, 2026, "manual-review")

    def test_official_source_still_requires_review(self):
        profile = tax.require_tax_profile(
            "https://www.irs.gov/publications/p946", "2026", "manual-review"
        )
        self.assertTrue(profile["review_required"])
        self.assertEqual(profile["tax_year"], 2026)

    def test_reject_invalid_percentages(self):
        for schedule in ({"2026": 101}, {"2026": -1}, {"2026": 60, "2027": 41},
                         {"2026": "NaN"}, {"2026": "Infinity"}):
            with self.subTest(schedule=schedule), self.assertRaises(ValueError):
                tax.custom_tax_depreciation_schedule(1000, schedule)

    def test_reject_invalid_business_use(self):
        for use in (-1, 101, "NaN", "Infinity"):
            with self.subTest(use=use), self.assertRaises(ValueError):
                tax.custom_tax_depreciation_schedule(1000, {"2026": 50}, use)
            with self.subTest(use=use), self.assertRaises(ValueError):
                tax.straight_line_book_schedule(1000, "2026-01-01", 5,
                                                business_use_percent=use)

    def test_manual_sales_tax_rate_bounds(self):
        for rate in (-1, 100.01, 101, "NaN", "Infinity", "-Infinity", "invalid"):
            with self.subTest(rate=rate), self.assertRaises(ValueError):
                tax.manual_sales_tax(100, rate)
        for rate in (0, 100):
            with self.subTest(valid_rate=rate):
                result = tax.manual_sales_tax(100, rate)
                self.assertEqual(result["rate_percent"], tax._percent(rate, "Sales tax rate"))

    def test_json_year_keys(self):
        rows = tax.custom_tax_depreciation_schedule(1000, {"2026": 40, "2027": 60})
        self.assertEqual([row["year"] for row in rows], [2026, 2027])


if __name__ == "__main__":
    unittest.main()
