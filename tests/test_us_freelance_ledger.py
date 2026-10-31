import importlib.util,sys,tempfile,unittest
from pathlib import Path
P=Path(__file__).resolve().parents[1]/"products"/"us-freelance-ledger"/"core.py";S=importlib.util.spec_from_file_location("usfl_factory",P);m=importlib.util.module_from_spec(S);sys.modules[S.name]=m;S.loader.exec_module(m)
class T(unittest.TestCase):
 def test_us_only_contract(self):
  self.assertIn("cash",m.METHODS);self.assertIn("accrual",m.METHODS)
  with tempfile.TemporaryDirectory() as d:
   s=m.Store(Path(d)/"x.db");s.add("2026-10-31","expense","12.50","Supplies");self.assertEqual(s.monthly(2026,10)["expense"],1250);s.close()
 def test_us_category_suggestion(self):
  x=m.suggest_category("Verizon business phone and internet","expense")
  self.assertTrue(x);self.assertEqual(x[0]["category"],"Utilities")
 def test_annual_net(self):
  with tempfile.TemporaryDirectory() as d:
   s=m.Store(Path(d)/"x.db");s.add("2026-01-01","income","100.00","Business income");s.add("2026-02-01","expense","25.00","Supplies");self.assertEqual(s.annual_summary(2026)["net"],7500);s.close()
 def test_review_rules(self):
  self.assertTrue(m.review_requirements("Meals - review"))
  self.assertTrue(m.review_requirements("Car and truck expenses - review"))
  self.assertTrue(m.review_requirements("Business use of home - review"))
  x=m.suggest_category("business vehicle mileage log","expense")
  self.assertTrue(x);self.assertTrue(x[0]["requires_review"])
 def test_ambiguous_or_substring_suggestions_fail_closed(self):
  self.assertEqual(m.suggest_category("carpet repair", "expense")[0]["category"], "Repairs and maintenance")
  self.assertEqual(m.suggest_category("gas bill", "expense"), [])
  self.assertEqual(m.suggest_category("car mileage", "expense")[0]["category"], "Car and truck expenses - review")
  self.assertEqual(m.suggest_category("hotel meal", "expense"), [])
  self.assertEqual(m.suggest_category("unknown memo", "expense"), [])
 def test_inventory_review_and_amount_boundaries(self):
  x=m.suggest_category("inventory goods for resale", "expense")
  self.assertEqual(x[0]["category"], "Inventory / COGS - review")
  self.assertTrue(x[0]["requires_review"])
  for amount in ["0.001", "0.004", "999999999999999999999.00", "NaN", "Infinity"]:
   with self.subTest(amount=amount),self.assertRaises(m.LedgerError):m.usd_to_cents(amount)
  self.assertEqual(m.usd_to_cents("0.005"), 1)
if __name__=="__main__":unittest.main()
