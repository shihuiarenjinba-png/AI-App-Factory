import importlib.util,sys,unittest
from decimal import Decimal
from pathlib import Path
P=Path(__file__).resolve().parents[1]/"products"/"us-bookkeeping-desk"/"tax_assets.py"
S=importlib.util.spec_from_file_location("us_tax_assets_book",P);m=importlib.util.module_from_spec(S);sys.modules[S.name]=m;S.loader.exec_module(m)
class T(unittest.TestCase):
 def test_manual_sales_tax(self):
  x=m.manual_sales_tax("100.00","8.25");self.assertEqual(x["tax"],Decimal("8.25"))
 def test_book_depreciation(self):
  rows=m.straight_line_book_schedule("1200","2026-01-01",4,through_year=2026);self.assertEqual(rows[0]["business_depreciation"],Decimal("300.00"))
 def test_tax_retro_requires_review(self):
  rows=m.custom_tax_depreciation_schedule("1000",{2026:"20",2027:"32"})
  x=m.retrospective_adjustment(rows,{2026:"0"},tax_mode=True);self.assertTrue(x["review_required"]);self.assertIn("Form 3115",x["message"])
 def test_tax_profile_requires_irs(self):
  with self.assertRaises(ValueError):m.require_tax_profile("https://example.com",2026,"MACRS")
if __name__=="__main__":unittest.main()
