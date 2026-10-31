import importlib.util,sys,unittest
from pathlib import Path
P=Path(__file__).resolve().parents[1]/"products"/"us-freelance-ledger"/"tax_assets.py"
S=importlib.util.spec_from_file_location("us_tax_assets_fl",P);m=importlib.util.module_from_spec(S);sys.modules[S.name]=m;S.loader.exec_module(m)
class T(unittest.TestCase):
 def test_sales_tax_is_manual(self):
  self.assertEqual(str(m.manual_sales_tax("50","7.5")["gross"]),"53.75")
 def test_tax_profile(self):
  x=m.require_tax_profile("https://www.irs.gov/publications/p946",2026,"MACRS review");self.assertTrue(x["review_required"])
if __name__=="__main__":unittest.main()
