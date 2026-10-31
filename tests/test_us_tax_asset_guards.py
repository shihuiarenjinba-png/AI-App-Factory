"""Fail-closed US tax input guards; no tax deductibility is inferred."""
import importlib.util
import sys
import unittest
from decimal import Decimal
from pathlib import Path

PATH = Path(__file__).resolve().parents[1] / "products" / "us-bookkeeping-desk" / "tax_assets.py"
SPEC = importlib.util.spec_from_file_location("us_tax_asset_guards", PATH)
mod = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = mod
SPEC.loader.exec_module(mod)


class TaxAssetGuardTests(unittest.TestCase):
    def test_manual_jurisdiction_rate_is_finite_and_explicit(self):
        self.assertEqual(mod.manual_sales_tax("100", "8.25")["tax"], Decimal("8.25"))
        for amount, rate in (("NaN", "8"), ("Infinity", "8"), ("100", "NaN"),
                             ("100", "-1"), ("-1", "5")):
            with self.subTest(amount=amount, rate=rate), self.assertRaises(ValueError):
                mod.manual_sales_tax(amount, rate)
        with self.assertRaises(ValueError):
            mod.manual_sales_tax("100", "8", rounding="surprise")

    def test_book_depreciation_rejects_nonfinite_or_impossible_use(self):
        self.assertEqual(mod.straight_line_book_schedule("1200", "2026-01-01", 4, through_year=2026)[0]["business_depreciation"], Decimal("300.00"))
        for cost, salvage, use in (("NaN", 0, 100), ("1200", "Infinity", 100),
                                   ("1200", 0, -1), ("1200", 0, 101)):
            with self.subTest(cost=cost, salvage=salvage, use=use), self.assertRaises(ValueError):
                mod.straight_line_book_schedule(cost, "2026-01-01", 4, salvage, use)
        with self.assertRaises(ValueError):
            mod.straight_line_book_schedule("1200", "2026-01-01", 4, through_year=2025)

    def test_tax_schedule_requires_reviewable_bounded_manual_rates(self):
        rows = mod.custom_tax_depreciation_schedule("1000", {2026: "20", 2027: "32"}, 75)
        self.assertEqual(rows[0]["business_depreciation"], Decimal("150.00"))
        for rates in ({2026: "101"}, {2026: "-1"}, {2026: "NaN"},
                      {2026: "70", 2027: "40"}, {"2026": "20", 2026: "20"}):
            with self.subTest(rates=rates), self.assertRaises(ValueError):
                mod.custom_tax_depreciation_schedule("1000", rates)
        for use in (-1, 101, "Infinity"):
            with self.subTest(use=use), self.assertRaises(ValueError):
                mod.custom_tax_depreciation_schedule("1000", {2026: "20"}, use)
        self.assertEqual(mod.custom_tax_depreciation_schedule("1000", {"2026": "20"})[0]["year"], 2026)

    def test_retroactive_difference_never_posts_and_requires_review(self):
        schedule = mod.custom_tax_depreciation_schedule("1000", {2026: "20"})
        result = mod.retrospective_adjustment(schedule, {2026: "100"}, tax_mode=True)
        self.assertEqual(result["total_difference"], Decimal("100.00"))
        self.assertTrue(result["review_required"])
        self.assertFalse(result["auto_post"])
        self.assertIn("Form 3115", result["message"])
        with self.assertRaises(ValueError):
            mod.retrospective_adjustment(schedule, {2026: "NaN"}, tax_mode=True)

    def test_irs_source_must_have_real_https_irs_hostname(self):
        valid = mod.require_tax_profile("https://www.irs.gov/publications/p946", 2025, "manual review")
        self.assertTrue(valid["review_required"])
        for url in ("https://notirs.gov/p946", "https://irs.gov.evil.example/p946",
                    "http://www.irs.gov/p946", "https://example.com/irs.gov/p946"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                mod.require_tax_profile(url, 2025, "manual review")


if __name__ == "__main__":
    unittest.main()
