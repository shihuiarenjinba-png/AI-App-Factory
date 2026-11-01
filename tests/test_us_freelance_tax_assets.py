import importlib.util,sys,unittest
from pathlib import Path
P=Path(__file__).resolve().parents[1]/"products"/"us-freelance-ledger"/"tax_assets.py"
S=importlib.util.spec_from_file_location("us_tax_assets_fl",P);m=importlib.util.module_from_spec(S);sys.modules[S.name]=m;S.loader.exec_module(m)
class T(unittest.TestCase):
 def test_sales_tax_is_manual(self):
  self.assertEqual(str(m.manual_sales_tax("50","7.5")["gross"]),"53.75")
 def test_tax_profile(self):
  x=m.require_tax_profile("https://www.irs.gov/publications/p946",2026,"MACRS review");self.assertTrue(x["review_required"])
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
 def test_main_syntax(self):
  p=Path(__file__).resolve().parents[1]/"products/us-freelance-ledger/main.py"
  compile(p.read_text(encoding="utf-8"),str(p),"exec")
if __name__=="__main__":unittest.main()
