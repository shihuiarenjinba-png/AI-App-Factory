"""Source-versioned 2026 tax-year reference fixture checks; no tax calculation."""
import json
import unittest
from pathlib import Path
from urllib.parse import urlsplit

FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "tax_year_rules_2026.json"
FIXTURE = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


class TaxYearReferenceFixture2026Tests(unittest.TestCase):
    def test_fixture_is_reference_only_and_review_required(self):
        self.assertEqual(FIXTURE["fixture_id"], "jp-us-asset-tax-year-2026")
        self.assertEqual(FIXTURE["retrieved_on"], "2026-11-26")
        self.assertEqual(FIXTURE["status"], "REFERENCE_ONLY_REVIEW_REQUIRED")
        self.assertIs(FIXTURE["auto_apply"], False)
        self.assertIs(FIXTURE["product_code_consumption"], False)
        self.assertIs(FIXTURE["cross_jurisdiction_guard"]["no_currency_conversion"], True)
        self.assertIs(FIXTURE["cross_jurisdiction_guard"]["no_rule_inheritance_between_jurisdictions"], True)

    def test_all_sources_are_official_https_and_each_rule_requires_review(self):
        for jurisdiction, section in FIXTURE["jurisdictions"].items():
            for rule in section["rules"]:
                source = rule["source"]
                parsed = urlsplit(source["url"])
                with self.subTest(jurisdiction=jurisdiction, rule=rule["rule_id"]):
                    self.assertEqual(parsed.scheme, "https")
                    host = (parsed.hostname or "").lower()
                    if jurisdiction.startswith("US-"):
                        self.assertIn(host, {"irs.gov", "www.irs.gov"})
                    else:
                        self.assertEqual(host, "www.nta.go.jp")
                    self.assertTrue(rule["review_required"])
                    self.assertFalse(rule["auto_apply"])

    def test_us_2026_section179_values_and_tax_year_basis(self):
        section = FIXTURE["jurisdictions"]["US-FEDERAL"]
        rule = next(x for x in section["rules"] if x["rule_id"] == "us.section179.2026")
        self.assertEqual(section["tax_year"], 2026)
        self.assertEqual(rule["tax_year_basis"], "taxable years beginning in 2026")
        self.assertEqual(rule["maximum_expense_usd"], 2_560_000)
        self.assertEqual(rule["phaseout_threshold_usd"], 4_090_000)
        self.assertEqual(rule["sport_utility_vehicle_cost_cap_usd"], 32_000)
        self.assertEqual(rule["source"]["published_on"], "2025-11-03")
        self.assertEqual(rule["source"]["source_section"], "Rev. Proc. 2025-32, §4.24 (2026 adjusted items)")

    def test_us_bonus_depreciation_is_qualified_property_not_universal(self):
        rule = next(
            x for x in FIXTURE["jurisdictions"]["US-FEDERAL"]["rules"]
            if x["rule_id"] == "us.special_depreciation.qualified_property.after_2025-01-19"
        )
        self.assertEqual(rule["acquired_after"], "2025-01-19")
        self.assertEqual(rule["placed_in_service_after"], "2025-01-19")
        self.assertEqual(rule["allowance_percent"], 100)
        self.assertTrue(rule["election_out_allowed"])
        self.assertEqual(rule["first_tax_year_ending_after_2025_01_19_election_percent"], 40)
        self.assertEqual(rule["long_production_period_or_certain_aircraft_election_percent"], 60)
        self.assertIn("not a general 2026 default rate", rule["note"])
        self.assertEqual(rule["source"]["edition"], "2025")
        self.assertNotIn("published_on", rule["source"])
        self.assertEqual(rule["source"]["irs_download_directory_date"], "2026-03-13")
        self.assertEqual(rule["source"]["irs_download_directory_filename"], "p946--2025.pdf")
        self.assertEqual(rule["source"]["irs_download_directory_url"], "https://www.irs.gov/downloads/irs-prior")

    def test_japan_2026_acquisition_date_cutover_is_strict_and_non_overlapping(self):
        rules = FIXTURE["jurisdictions"]["JP-INDIVIDUAL-INCOME-TAX"]["rules"]
        before = next(x for x in rules if x["rule_id"].endswith("pre_cutover"))
        after = next(x for x in rules if x["rule_id"].endswith("post_cutover"))
        self.assertEqual(before["acquisition_date_through"], "2026-03-31")
        self.assertEqual(after["acquisition_date_from"], "2026-04-01")
        self.assertEqual(before["eligible_cost_max_exclusive_jpy"], 300_000)
        self.assertEqual(after["eligible_cost_max_exclusive_jpy"], 400_000)
        self.assertEqual(before["annual_aggregate_cap_jpy"], 3_000_000)
        self.assertEqual(after["annual_aggregate_cap_jpy"], 3_000_000)
        self.assertTrue(before["blue_return_required"])
        self.assertTrue(after["blue_return_required"])
        self.assertTrue(before["exclude_if_three_year_pooled_asset_rule_applied"])
        self.assertTrue(after["exclude_if_three_year_pooled_asset_rule_applied"])

    def test_japan_common_conditions_apply_to_both_cutover_windows(self):
        rules = FIXTURE["jurisdictions"]["JP-INDIVIDUAL-INCOME-TAX"]["rules"]
        for rule in rules:
            with self.subTest(rule=rule["rule_id"]):
                self.assertIn("tax-inclusive cost", rule["cost_tax_inclusion_rule"])
                self.assertIn("on or after 2022-04-01", rule["lending_asset_exclusion"])
                self.assertIn("principal business", rule["lending_asset_exclusion"])
                self.assertIn("注3・注4・注5", rule["source"]["source_note"])

    def test_jurisdiction_currency_and_tax_scope_are_not_mixed(self):
        guard = FIXTURE["cross_jurisdiction_guard"]
        self.assertEqual(guard["currency_by_jurisdiction"]["US-FEDERAL"], "USD")
        self.assertEqual(guard["currency_by_jurisdiction"]["JP-INDIVIDUAL-INCOME-TAX"], "JPY")
        self.assertIn("not state sales tax", FIXTURE["jurisdictions"]["US-FEDERAL"]["tax_scope"])
        self.assertIn("individual income tax", FIXTURE["jurisdictions"]["JP-INDIVIDUAL-INCOME-TAX"]["tax_scope"])


if __name__ == "__main__":
    unittest.main()
