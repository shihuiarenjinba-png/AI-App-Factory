"""Issue #64: independent fail-closed regression fixtures for US tax assets."""
import importlib.util
from pathlib import Path
import unittest

MODULE_PATH = Path(__file__).resolve().parents[1] / "products" / "us-freelance-ledger" / "tax_assets.py"
spec = importlib.util.spec_from_file_location("us_freelance_tax_assets_issue64", MODULE_PATH)
tax = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tax)


class Issue64TaxAssetsTests(unittest.TestCase):
    def test_spoofed_and_ambiguous_irs_urls_rejected(self):
        bad = [
            "https://irs.gov.evil.example/p946",
            "http://irs.gov/publications/p946",
            "https://irs.gov@evil.example/publications/p946",
            "https://evil.example/?next=https://irs.gov",
            "https://irs.gov:invalid/publications/p946",
            "https://irs.gov\\@evil.example/publications/p946",
            "https://irs.gov\\@evil.example/publications/p946",
            "https://irs.gov\\evil.example/publications/p946",
            "https://irs.gov/publications/p946\n",
            "https://irs.gov/publications/p946\t",
            "https://irs.gov/publications/p946\r",
            "https://irs.gov/publications/p946 ",
            "https://irs.gov/publications/p946\x00",
            "",
        ]
        for url in bad:
            with self.subTest(url=url), self.assertRaises(ValueError):
                tax.require_tax_profile(url, 2026, "manual-review")

    def test_official_irs_source_is_review_required(self):
        result = tax.require_tax_profile(
            "https://www.irs.gov/publications/p946", "2026", "manual-review"
        )
        self.assertTrue(result["review_required"])
        self.assertEqual(result["tax_year"], 2026)

    def test_invalid_tax_schedule_percentages_rejected(self):
        invalid = [
            {"2026": 101},
            {"2026": -1},
            {"2026": 60, "2027": 41},
            {"2026": "NaN"},
            {"2026": "Infinity"},
            {"2026": 50, 2026: 50},
        ]
        for schedule in invalid:
            with self.subTest(schedule=schedule), self.assertRaises(ValueError):
                tax.custom_tax_depreciation_schedule(1000, schedule)

    def test_invalid_business_use_rejected_for_both_schedules(self):
        for percent in (-1, 101, "NaN", "Infinity"):
            with self.subTest(percent=percent):
                with self.assertRaises(ValueError):
                    tax.custom_tax_depreciation_schedule(1000, {"2026": 50}, percent)
                with self.assertRaises(ValueError):
                    tax.straight_line_book_schedule(
                        1000, "2026-01-01", 5, business_use_percent=percent
                    )

    def test_json_string_year_keys_supported(self):
        rows = tax.custom_tax_depreciation_schedule(
            1000, {"2026": 40, "2027": 60}
        )
        self.assertEqual([row["year"] for row in rows], [2026, 2027])
        self.assertEqual(sum(row["tax_depreciation"] for row in rows), 1000)


if __name__ == "__main__":
    unittest.main()
