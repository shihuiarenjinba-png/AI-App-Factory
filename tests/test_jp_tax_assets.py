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
 def test_main_syntax(self):
  p=Path(__file__).resolve().parents[1]/"products/jp-bookkeeping-desk/main.py"
  compile(p.read_text(encoding="utf-8"),str(p),"exec")
 def test_tax_numeric_safety(self):
  for amount,rate,rounding in [(float("nan"),"0.10","切捨て"),(float("inf"),"0.10","切捨て"),("100.5","0.10","切捨て"),(1000,"NaN","切捨て"),(1000,"1.2","切捨て"),(1000,"0.10","unknown")]:
   with self.subTest(amount=amount,rate=rate,rounding=rounding):
    with self.assertRaises(ValueError):m.consumption_tax_from_net(amount,rate,rounding)
  for amount,rate in [("NaN","0.10"),(1000,"Infinity"),(1000,"-0.1"),("0.5","0.10")]:
   with self.subTest(amount=amount,rate=rate):
    with self.assertRaises(ValueError):m.consumption_tax_from_gross(amount,rate)
 def test_depreciation_numeric_safety(self):
  cases=[
   dict(cost_yen="1000.5",useful_life_years=4,straight_line_rate="0.25"),
   dict(cost_yen=1000,useful_life_years="4.5",straight_line_rate="0.25"),
   dict(cost_yen=1000,useful_life_years=4,straight_line_rate="NaN"),
   dict(cost_yen=1000,useful_life_years=4,straight_line_rate="1.5"),
   dict(cost_yen=1000,useful_life_years=4,straight_line_rate="0"),
   dict(cost_yen=1000,useful_life_years=4,straight_line_rate="0.25",business_use_percent="NaN"),
   dict(cost_yen=1000,useful_life_years=4,straight_line_rate="0.25",through_year=2025),
  ]
  for params in cases:
   with self.subTest(params=params):
    with self.assertRaises(ValueError):m.jp_depreciation_schedule(first_use_date="2026-01-01",**params)
  with self.assertRaises(ValueError):
   m.jp_depreciation_schedule(1000,"2026-01-01",4,method="定率法",declining_rate="0.2",revised_rate="Infinity",guarantee_rate="0.05")
  good=m.jp_depreciation_schedule(1000,"2026-01-01",4,straight_line_rate="0.25",through_year=2026)
  self.assertEqual(good[0]["business_depreciation"],250)
if __name__=="__main__":unittest.main()
