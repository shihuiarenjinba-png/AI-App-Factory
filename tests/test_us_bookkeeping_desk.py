import importlib.util,json,sys,tempfile,unittest
from pathlib import Path
P=Path(__file__).resolve().parents[1]/"products"/"us-bookkeeping-desk"/"core.py";S=importlib.util.spec_from_file_location("usb_factory",P);m=importlib.util.module_from_spec(S);sys.modules[S.name]=m;S.loader.exec_module(m)
class T(unittest.TestCase):
 def test_us_chart(self):
  with tempfile.TemporaryDirectory() as d:
   s=m.Store(Path(d)/"x.db");self.assertIn("Cash",{x["name"] for x in s.accounts()});self.assertIn(s.accounting_method,m.METHODS);s.close()
 def test_journal_suggestion(self):
  x=m.suggest_entry("monthly office rent payment");self.assertEqual(x["debit_code"],"5200");self.assertEqual(x["credit_code"],"1100")
 def test_balance_check(self):
  with tempfile.TemporaryDirectory() as d:
   s=m.Store(Path(d)/"x.db");s.post("2026-10-31","sale",[("1000","100.00",""),("4000","","100.00")]);self.assertTrue(s.balance_check()["balanced"]);s.close()
 def test_review_accounts(self):
  self.assertTrue(m.review_requirements_for_codes(["5350"]))
  self.assertTrue(m.review_requirements_for_codes(["5450"]))
  self.assertTrue(m.review_requirements_for_codes(["5600"]))
  x=m.suggest_entry("business vehicle mileage")
  self.assertEqual(x["debit_code"],"5350")
  self.assertTrue(x["review_reasons"])
 def test_us_compliance_evidence_gate(self):
  p=Path(__file__).resolve().parents[1]/"products"/"us-bookkeeping-desk"
  scope=json.loads((p/"market-scope.json").read_text(encoding="utf-8"))
  evidence=(p/"US_COMPLIANCE_SCOPE.md").read_text(encoding="utf-8")
  self.assertEqual(scope["store_markets"],["US"])
  self.assertFalse(scope["cross_market_sale"])
  self.assertFalse(scope["tax_filing"])
  self.assertFalse(scope["compliance_claim"])
  self.assertIn("COMPLIANCE_HOLD",evidence)
  self.assertIn("Form 3115",evidence)
  self.assertIn("Cash versus accrual",evidence)
if __name__=="__main__":unittest.main()
