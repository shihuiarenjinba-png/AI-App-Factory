import importlib.util,sys,unittest
from pathlib import Path
P=Path(__file__).resolve().parents[1]/"products"/"jp-bookkeeping-desk"/"tax_assets.py"
S=importlib.util.spec_from_file_location("jp_tax_assets_book",P);m=importlib.util.module_from_spec(S);sys.modules[S.name]=m;S.loader.exec_module(m)
class T(unittest.TestCase):
 def test_consumption_tax(self):
  x=m.consumption_tax_from_net(10000,"0.10");self.assertEqual(x["tax"],1000);self.assertEqual(x["gross"],11000)
 def test_straight_line_and_retro(self):
  rows=m.jp_depreciation_schedule(120000,"2026-01-01",4,method="定額法",straight_line_rate="0.250",through_year=2027)
  self.assertEqual(rows[0]["business_depreciation"],30000)
  adj=m.retrospective_adjustment(rows,{2026:20000});self.assertEqual(adj["rows"][0]["difference"],10000);self.assertTrue(adj["review_required"])
 def test_declining_requires_official_rates(self):
  with self.assertRaises(ValueError):m.jp_depreciation_schedule(100000,"2026-01-01",4,method="定率法")
if __name__=="__main__":unittest.main()
