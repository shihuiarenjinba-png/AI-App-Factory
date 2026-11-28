import importlib.util
import os
import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
P = ROOT / "products" / "us-freelance-ledger" / "tax_assets.py"
S = importlib.util.spec_from_file_location("us_tax_assets_fl", P)
m = importlib.util.module_from_spec(S)
sys.modules[S.name] = m
S.loader.exec_module(m)


def load_us_core():
    path = ROOT / "products" / "us-freelance-ledger" / "core.py"
    spec = importlib.util.spec_from_file_location("us_depreciation_review_core", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def complete_review(**overrides):
    values = {
        "tax_year": 2026,
        "source_url": m.IRS_PUB_946_2025_PDF_URL,
        "source_version": m.IRS_PUB_946_2025_VERSION,
        "acquisition_date": "2026-02-01",
        "placed_in_service_date": "2026-02-15",
        "asset_class": "Computer equipment",
        "recovery_period_years": 5,
        "depreciable_basis_usd": "10000.00",
        "business_use_percent": "80",
        "macrs_method": "GDS 200% declining balance",
        "convention": "half_year",
        "section_179_election": "not_applicable",
        "special_depreciation_election": "elect_out",
        "eligibility_confirmed": True,
        "prior_depreciation_applicable": False,
        "prior_depreciation_usd": None,
    }
    values.update(overrides)
    return m.build_tax_depreciation_review(**values)


class T(unittest.TestCase):
    def test_sales_tax_is_manual(self):
        self.assertEqual(str(m.manual_sales_tax("50", "7.5")["gross"]), "53.75")

    def test_tax_profile(self):
        for url in ("https://www.irs.gov/publications/p946", "https://irs.gov/forms-pubs/about-form-3115"):
            with self.subTest(url=url):
                x = m.require_tax_profile(url, 2026, "MACRS review")
                self.assertTrue(x["review_required"])
        for url in ("", "http://irs.gov/publications/p946", "https://example.invalid/irs.gov/2026",
                    "https://evil.example/?src=irs.gov", "https://irs.gov.evil.example/p946",
                    "https://user@irs.gov/publications/p946"):
            with self.subTest(url=url):
                with self.assertRaises(ValueError):
                    m.require_tax_profile(url, 2026, "MACRS review")
        with self.assertRaises(ValueError):
            m.require_tax_profile("https://www.irs.gov/publications/p946", 2026, "")

    def test_sales_tax_rejects_invalid_numbers_and_rounding(self):
        self.assertEqual(str(m.manual_sales_tax("50", "7.5", "nearest")["gross"]), "53.75")
        for amount, rate, rounding in (("NaN", "7.5", "nearest"), ("Infinity", "7.5", "nearest"),
                                       ("50", "NaN", "nearest"), ("50", "Infinity", "nearest"),
                                       ("50", "-1", "nearest"), ("50", "101", "nearest"),
                                       ("-1", "7.5", "nearest"), ("50", "7.5", "bankers")):
            with self.subTest(amount=amount, rate=rate, rounding=rounding):
                with self.assertRaises(ValueError):
                    m.manual_sales_tax(amount, rate, rounding)

    def test_book_depreciation_rejects_invalid_business_use(self):
        for use in (-1, 101, "NaN", "Infinity"):
            with self.subTest(use=use):
                with self.assertRaises(ValueError):
                    m.straight_line_book_schedule("1000", "2026-01-01", 5, business_use_percent=use)
        with self.assertRaises(ValueError):
            m.straight_line_book_schedule("1000", "2026-01-01", 5, through_year=2025)

    def test_manual_depreciation_does_not_exceed_cost(self):
        rows = m.custom_tax_depreciation_schedule("100", {2026: "60", 2027: "40"}, business_use_percent=50)
        self.assertEqual(sum(r["tax_depreciation"] for r in rows), 100)
        self.assertEqual(sum(r["business_depreciation"] for r in rows), 50)
        for rates in ({2026: "70", 2027: "40"}, {2026: "NaN"}, {2026: "Infinity"}, {2026: "-1"}, {}):
            with self.subTest(rates=rates):
                self.assertRaises(ValueError, m.custom_tax_depreciation_schedule, "100", rates)
        for use in (-1, 101, "NaN", "Infinity"):
            with self.subTest(use=use):
                self.assertRaises(ValueError, m.custom_tax_depreciation_schedule, "100", {2026: 100}, use)
        self.assertRaises(ValueError, m.custom_tax_depreciation_schedule, "100", {2026: 50, "2026": 50})

    def test_2026_mileage_date_boundaries_are_review_only(self):
        for day, rate in (("2026-01-01", "0.725"), ("2026-06-30", "0.725"),
                          ("2026-07-01", "0.76"), ("2026-12-31", "0.76")):
            with self.subTest(day=day):
                r = m.business_mileage_2026_review(day, "100", "business")
                self.assertEqual(str(r["rate_usd_per_mile"]), rate)
                self.assertEqual(str(r["estimate_usd"]), "72.50" if day < "2026-07-01" else "76.00")
                self.assertEqual(r["status"], "REVIEW_REQUIRED")
                self.assertTrue(r["review_required"])
                self.assertFalse(r["auto_post"])
                self.assertFalse(r["deduction_approved"])
                self.assertTrue(r["source_url"].startswith("https://www.irs.gov/"))

    def test_mileage_tax_year_and_purpose_must_not_inherit_business_rate(self):
        for day, purpose in (("2025-12-31", "business"), ("2027-01-01", "business"),
                             ("2026-07-01", "medical"), ("2026-06-30", "commuting"),
                             ("2026-07-01", "charity")):
            with self.subTest(day=day, purpose=purpose):
                r = m.business_mileage_2026_review(day, "100", purpose)
                self.assertEqual(r["status"], "REVIEW_REQUIRED")
                self.assertIsNone(r["rate_usd_per_mile"])
                self.assertIsNone(r["estimate_usd"])
                self.assertFalse(r["auto_post"])
                self.assertFalse(r["deduction_approved"])

    def test_mileage_invalid_dates_and_distances_fail_closed(self):
        for day, miles in (("2026-02-30", "10"), ("20260701", "10"),
                           ("2026-07-01", "NaN"), ("2026-07-01", "Infinity"),
                           ("2026-07-01", "-1"), ("2026-07-01", "10000001")):
            with self.subTest(day=day, miles=miles):
                with self.assertRaises(ValueError):
                    m.business_mileage_2026_review(day, miles)
        self.assertEqual(str(m.business_mileage_2026_review("2026-07-01", "1.5")["estimate_usd"]), "1.14")

    def test_section_179_source_fixtures_are_tax_year_specific(self):
        y2025 = m.section_179_source_reference(2025)
        self.assertEqual(y2025["source_version"], "IRS Publication 946 (2025)")
        self.assertEqual(y2025["section_179_max_usd"], "2500000")
        self.assertEqual(y2025["section_179_phaseout_threshold_usd"], "4000000")
        self.assertEqual(y2025["suv_limit_usd"], "31300")
        self.assertTrue(y2025["reference_only"])
        self.assertTrue(y2025["review_required"])
        self.assertFalse(y2025["auto_post"])

        y2026 = m.section_179_source_reference(2026)
        self.assertEqual(y2026["section_179_max_usd"], "2560000")
        self.assertEqual(y2026["section_179_phaseout_threshold_usd"], "4090000")
        self.assertEqual(y2026["suv_limit_usd"], "32000")
        self.assertEqual(y2026["corroborating_source_version"], "IRS IR-2026-133 (2026-11-05)")
        self.assertEqual(y2026["source_effective_period"], "Tax years beginning in 2026")
        self.assertFalse(y2026["deduction_approved"])

        unsupported = m.section_179_source_reference(2027)
        self.assertEqual(unsupported["status"], "REVIEW_REQUIRED")
        self.assertEqual(unsupported["reason"], "TAX_YEAR_SOURCE_NOT_VERIFIED")
        self.assertIsNone(unsupported["section_179_max_usd"])
        self.assertFalse(unsupported["auto_post"])

    def test_depreciation_review_requires_explicit_provenance_and_rejects_nta_source(self):
        missing = m.build_tax_depreciation_review()
        self.assertEqual(missing["status"], "REVIEW_REQUIRED")
        for field in ("tax_year", "source_url", "source_version", "acquisition_date",
                      "placed_in_service_date", "asset_class", "recovery_period_years",
                      "depreciable_basis_usd", "business_use_percent", "macrs_method",
                      "convention", "section_179_election", "special_depreciation_election",
                      "eligibility_confirmed", "prior_depreciation_applicable"):
            self.assertIn(field, missing["missing_fields"])
        self.assertFalse(missing["calculation_performed"])
        self.assertIsNone(missing["calculation_preview"])
        self.assertFalse(missing["ledger_write"])

        nta_source = complete_review(
            source_url="https://www.nta.go.jp/taxes/shiraberu/taxanswer/shotoku/2100.htm",
            source_version="NTA Tax Answer No.2100",
        )
        self.assertIn("OFFICIAL_IRS_SOURCE_REQUIRED", nta_source["blocking_reasons"])
        self.assertIn("UNSUPPORTED_IRS_PUBLICATION_SOURCE", nta_source["blocking_reasons"])
        self.assertFalse(nta_source["provenance_complete"])
        self.assertFalse(nta_source["auto_post"])

    def test_special_depreciation_date_boundary_is_candidate_not_eligibility(self):
        after_boundary = complete_review(
            acquisition_date="2025-01-20",
            placed_in_service_date="2025-01-20",
        )
        self.assertEqual(after_boundary["special_depreciation_window"],
                         "POST_2025_01_19_CANDIDATE_REVIEW_REQUIRED")
        self.assertTrue(after_boundary["provenance_complete"])
        self.assertTrue(after_boundary["review_required"])
        self.assertFalse(after_boundary["eligibility_determined"])
        self.assertFalse(after_boundary["deduction_approved"])
        self.assertFalse(after_boundary["calculation_performed"])

        acquisition_on_boundary = complete_review(
            acquisition_date="2025-01-19",
            placed_in_service_date="2025-01-20",
        )
        self.assertEqual(acquisition_on_boundary["special_depreciation_window"],
                         "PRE_2025_01_20_ACQUISITION_2025_SERVICE_REVIEW_REQUIRED")
        self.assertFalse(acquisition_on_boundary["eligibility_determined"])

    def test_complete_depreciation_review_preserves_source_and_prior_depreciation(self):
        result = complete_review(
            prior_depreciation_applicable=True,
            prior_depreciation_usd="500.00",
        )
        self.assertTrue(result["provenance_complete"])
        self.assertTrue(result["ready_for_manual_review"])
        self.assertEqual(result["status"], "REVIEW_REQUIRED")
        self.assertEqual(result["provenance"]["tax_year"], 2026)
        self.assertEqual(result["provenance"]["source_version"], "IRS Publication 946 (2025)")
        self.assertEqual(result["provenance"]["source_effective_period"], "Tax years beginning in 2026")
        self.assertEqual(result["provenance"]["prior_depreciation_usd"], "500.00")
        self.assertEqual(result["source_reference"]["section_179_max_usd"], "2560000")
        self.assertFalse(result["eligibility_determined"])
        self.assertFalse(result["deduction_approved"])
        self.assertFalse(result["calculation_performed"])
        self.assertIsNone(result["calculation_preview"])
        self.assertFalse(result["auto_post"])
        self.assertFalse(result["ledger_write"])
        self.assertFalse(result["tax_advice"])

    def test_depreciation_review_is_read_only_and_preserves_jp_sentinel(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            jp_dir = base / "JPFreelanceLedger"
            jp_dir.mkdir()
            jp_db = jp_dir / "books.sqlite3"
            with closing(sqlite3.connect(jp_db)) as connection:
                with connection:
                    connection.execute("CREATE TABLE sentinel (value TEXT NOT NULL)")
                    connection.execute("INSERT INTO sentinel VALUES ('JP-KEEP')")
            jp_before = jp_db.read_bytes()

            with patch.dict(os.environ, {"APPDATA": str(base)}):
                core = load_us_core()
                store = core.Store()
                try:
                    us_before = store.path.read_bytes()
                    result = complete_review()
                    transaction_count = store.conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
                    audit_count = store.conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
                    self.assertEqual(transaction_count, 0)
                    self.assertEqual(audit_count, 0)
                    self.assertEqual(store.path.read_bytes(), us_before)
                    self.assertEqual(jp_db.read_bytes(), jp_before)
                    self.assertEqual(result["status"], "REVIEW_REQUIRED")
                    self.assertFalse(result["ledger_write"])
                    self.assertFalse(result["auto_post"])
                finally:
                    store.close()

    def test_main_syntax(self):
        p = ROOT / "products/us-freelance-ledger/main.py"
        source = p.read_text(encoding="utf-8")
        compile(source, str(p), "exec")
        self.assertIn("does not automatically shift income or expense recognition dates", source)


if __name__ == "__main__":
    unittest.main()
