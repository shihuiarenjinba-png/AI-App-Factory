"""NTA effective-date tax-rate guard: no future/historical rate guessing."""
import importlib.util
import sys
import unittest
from pathlib import Path

P = Path(__file__).resolve().parents[1] / "products" / "jp-bookkeeping-desk" / "tax_assets.py"
spec = importlib.util.spec_from_file_location("jp_tax_date_review", P)
tax = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = tax
spec.loader.exec_module(tax)


class TaxDateReviewTests(unittest.TestCase):
    def test_current_standard_and_reduced_reference_arithmetic(self):
        standard = tax.consumption_tax_review(10000, "2026-11-01", "標準課税")
        food = tax.consumption_tax_review(10000, "2026-11-01", "飲食料品（酒類・外食を除く）")
        paper = tax.consumption_tax_review(10000, "2027-03-31", "定期購読新聞")
        self.assertFalse(standard["review_required"])
        self.assertEqual((standard["tax"], standard["gross"]), (1000, 11000))
        self.assertEqual(food["tax"], 800)
        self.assertEqual(paper["tax"], 800)
        self.assertEqual(standard["source_url"], tax.JP_TAX_RATE_SOURCE)

    def test_future_rate_change_requires_review_without_numeric_guess(self):
        for when in ("2027-04-01", "2028-07-01", "2029-03-31", "2029-04-01"):
            for category in ("標準課税", "飲食料品（酒類・外食を除く）"):
                with self.subTest(when=when, category=category):
                    result = tax.consumption_tax_review(10000, when, category)
                    self.assertTrue(result["review_required"])
                    self.assertIsNone(result["tax"])
                    self.assertIsNone(result["gross"])
                    self.assertIsNone(result["rate"])

    def test_old_date_exempt_uncertain_and_invalid_input(self):
        for when, category in [
            ("2019-09-30", "標準課税"),
            ("2026-11-01", "要確認"),
        ]:
            self.assertTrue(tax.consumption_tax_review(10000, when, category)["review_required"])
        for when, category, amount in [
            ("not-a-date", "標準課税", 100),
            ("2026-11-01", "unknown", 100),
            ("2026-11-01", "標準課税", "NaN"),
            ("2026-11-01", "標準課税", "100.5"),
        ]:
            with self.subTest(when=when, category=category, amount=amount):
                with self.assertRaises(ValueError):
                    tax.consumption_tax_review(amount, when, category)

    def test_ui_syntax(self):
        path = P.with_name("main.py")
        compile(path.read_text(encoding="utf-8"), str(path), "exec")


if __name__ == "__main__":
    unittest.main()
