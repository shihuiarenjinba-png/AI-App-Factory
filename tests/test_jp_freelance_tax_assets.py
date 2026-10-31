import importlib.util,sys,unittest
from pathlib import Path
P=Path(__file__).resolve().parents[1]/"products"/"jp-freelance-ledger"/"tax_assets.py"
S=importlib.util.spec_from_file_location("jp_tax_assets_fl",P);m=importlib.util.module_from_spec(S);sys.modules[S.name]=m;S.loader.exec_module(m)
class T(unittest.TestCase):
 def test_reduced_tax(self):
  x=m.consumption_tax_from_net(1000,"0.08");self.assertEqual(x["tax"],80)
 def test_midyear_proration(self):
  rows=m.jp_depreciation_schedule(120000,"2026-07-01",4,method="定額法",straight_line_rate="0.250",through_year=2026)
  self.assertEqual(rows[0]["months"],6);self.assertEqual(rows[0]["business_depreciation"],15000)
if __name__=="__main__":unittest.main()
