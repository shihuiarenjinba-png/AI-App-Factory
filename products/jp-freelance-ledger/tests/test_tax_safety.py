"""NTA-aligned calculation input guards and retrospective review fixtures."""
import unittest

from tax_assets import (consumption_tax_from_gross, consumption_tax_from_net,
                        jp_depreciation_schedule, retrospective_adjustment)


class JPTaxSafetyTests(unittest.TestCase):
    def test_net_and_gross_integer_yen(self):
        self.assertEqual(consumption_tax_from_net(1000, "0.10")["gross"], 1100)
        self.assertEqual(consumption_tax_from_gross(1100, "0.10")["net"], 1000)
        self.assertEqual(consumption_tax_from_net(1000, "0.08")["tax"], 80)

    def test_nonfinite_and_fractional_yen_rejected(self):
        for value in ("nan", "Infinity", "-Infinity", "-1", "1.5"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    consumption_tax_from_net(value, "0.10")
                with self.assertRaises(ValueError):
                    consumption_tax_from_gross(value, "0.10")

    def test_nonfinite_negative_or_oversized_rate_rejected(self):
        for rate in ("NaN", "Infinity", "-0.01", "1.01"):
            with self.subTest(rate=rate):
                with self.assertRaises(ValueError):
                    consumption_tax_from_net(1000, rate)
                with self.assertRaises(ValueError):
                    consumption_tax_from_gross(1000, rate)

    def test_unknown_rounding_rejected(self):
        with self.assertRaises(ValueError):
            consumption_tax_from_net(1000, "0.10", "unknown")

    def test_depreciation_requires_verified_rates_and_month_proration(self):
        with self.assertRaises(ValueError):
            jp_depreciation_schedule(120000, "2026-07-01", 4, method="定率法")
        rows = jp_depreciation_schedule(
            120000, "2026-07-01", 4, method="定額法",
            straight_line_rate="0.25", business_use_percent=50, through_year=2026)
        self.assertEqual((rows[0]["months"], rows[0]["tax_depreciation_before_business_use"],
                          rows[0]["business_depreciation"]), (6, 15000, 7500))

    def test_retrospective_includes_posted_only_years(self):
        schedule = [{"year": 2025, "business_depreciation": 100},
                    {"year": 2026, "business_depreciation": 200}]
        r = retrospective_adjustment(schedule, {2024: 50, 2025: 120})
        self.assertEqual([x["year"] for x in r["rows"]], [2024, 2025, 2026])
        self.assertEqual([x["difference"] for x in r["rows"]], [-50, -20, 200])
        self.assertEqual(r["total_difference"], 130)
        self.assertTrue(r["rows"][0]["posted_only"])
        self.assertTrue(r["review_required"])
        self.assertFalse(r["auto_post"])

    def test_retrospective_rejects_unsafe_values(self):
        for value in (True, "nan", "1.2", "9999999999999999999"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                retrospective_adjustment([], {2026: value})
        with self.assertRaises(ValueError):
            retrospective_adjustment([], {"2026": 5})


if __name__ == "__main__":
    unittest.main()
