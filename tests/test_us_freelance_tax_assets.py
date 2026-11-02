import importlib.util,sys,unittest
from pathlib import Path
P=Path(__file__).resolve().parents[1]/"products"/"us-freelance-ledger"/"tax_assets.py"
S=importlib.util.spec_from_file_location("us_tax_assets_fl",P);m=importlib.util.module_from_spec(S);sys.modules[S.name]=m;S.loader.exec_module(m)
class T(unittest.TestCase):
 def test_sales_tax_is_manual(self):
  self.assertEqual(str(m.manual_sales_tax("50","7.5")["gross"]),"53.75")
 def test_tax_profile(self):
  for url in ("https://www.irs.gov/publications/p946","https://irs.gov/forms-pubs/about-form-3115"):
   with self.subTest(url=url):
    x=m.require_tax_profile(url,2026,"MACRS review");self.assertTrue(x["review_required"])
  for url in ("","http://irs.gov/publications/p946","https://example.invalid/irs.gov/2026",
              "https://evil.example/?src=irs.gov","https://irs.gov.evil.example/p946",
              "https://user@irs.gov/publications/p946"):
   with self.subTest(url=url):
    with self.assertRaises(ValueError):m.require_tax_profile(url,2026,"MACRS review")
  with self.assertRaises(ValueError):m.require_tax_profile("https://www.irs.gov/publications/p946",2026,"")
 def test_sales_tax_rejects_invalid_numbers_and_rounding(self):
  self.assertEqual(str(m.manual_sales_tax("50","7.5","nearest")["gross"]),"53.75")
  for amount,rate,rounding in (("NaN","7.5","nearest"),("Infinity","7.5","nearest"),
                               ("50","NaN","nearest"),("50","Infinity","nearest"),
                               ("50","-1","nearest"),("50","101","nearest"),
                               ("-1","7.5","nearest"),("50","7.5","bankers")):
   with self.subTest(amount=amount,rate=rate,rounding=rounding):
    with self.assertRaises(ValueError):m.manual_sales_tax(amount,rate,rounding)
 def test_book_depreciation_rejects_invalid_business_use(self):
  for use in (-1,101,"NaN","Infinity"):
   with self.subTest(use=use):
    with self.assertRaises(ValueError):
     m.straight_line_book_schedule("1000","2026-01-01",5,business_use_percent=use)
  with self.assertRaises(ValueError):
   m.straight_line_book_schedule("1000","2026-01-01",5,through_year=2025)
 def test_manual_depreciation_does_not_exceed_cost(self):
  rows=m.custom_tax_depreciation_schedule("100", {2026:"60",2027:"40"}, business_use_percent=50)
  self.assertEqual(sum(r["tax_depreciation"] for r in rows),100)
  self.assertEqual(sum(r["business_depreciation"] for r in rows),50)
  for rates in ({2026:"70",2027:"40"}, {2026:"NaN"}, {2026:"Infinity"}, {2026:"-1"}, {}):
   with self.subTest(rates=rates):
    self.assertRaises(ValueError,m.custom_tax_depreciation_schedule,"100",rates)
  for use in (-1,101,"NaN","Infinity"):
   with self.subTest(use=use):
    self.assertRaises(ValueError,m.custom_tax_depreciation_schedule,"100",{2026:100},use)
  self.assertRaises(ValueError,m.custom_tax_depreciation_schedule,"100",{2026:50,"2026":50})
 def test_2026_mileage_date_boundaries_are_review_only(self):
  for day,rate in (("2026-01-01","0.725"),("2026-06-30","0.725"),
                   ("2026-07-01","0.76"),("2026-12-31","0.76")):
   with self.subTest(day=day):
    r=m.business_mileage_2026_review(day,"100","business")
    self.assertEqual(str(r["rate_usd_per_mile"]),rate)
    self.assertEqual(str(r["estimate_usd"]),"72.50" if day<"2026-07-01" else "76.00")
    self.assertEqual(r["status"],"REVIEW_REQUIRED")
    self.assertTrue(r["review_required"])
    self.assertFalse(r["auto_post"])
    self.assertFalse(r["deduction_approved"])
    self.assertTrue(r["source_url"].startswith("https://www.irs.gov/"))
 def test_mileage_tax_year_and_purpose_must_not_inherit_business_rate(self):
  for day,purpose in (("2025-12-31","business"),("2027-01-01","business"),
                      ("2026-07-01","medical"),("2026-06-30","commuting"),
                      ("2026-07-01","charity")):
   with self.subTest(day=day,purpose=purpose):
    r=m.business_mileage_2026_review(day,"100",purpose)
    self.assertEqual(r["status"],"REVIEW_REQUIRED")
    self.assertIsNone(r["rate_usd_per_mile"])
    self.assertIsNone(r["estimate_usd"])
    self.assertFalse(r["auto_post"])
    self.assertFalse(r["deduction_approved"])
 def test_mileage_invalid_dates_and_distances_fail_closed(self):
  for day,miles in (("2026-02-30","10"),("20260701","10"),
                    ("2026-07-01","NaN"),("2026-07-01","Infinity"),
                    ("2026-07-01","-1"),("2026-07-01","10000001")):
   with self.subTest(day=day,miles=miles):
    with self.assertRaises(ValueError):
     m.business_mileage_2026_review(day,miles)
  self.assertEqual(str(m.business_mileage_2026_review("2026-07-01","1.5")["estimate_usd"]),"1.14")
 def test_main_syntax(self):
  p=Path(__file__).resolve().parents[1]/"products/us-freelance-ledger/main.py"
  source=p.read_text(encoding="utf-8")
  compile(source,str(p),"exec")
  self.assertIn("does not automatically shift income or expense recognition dates",source)
if __name__=="__main__":unittest.main()
