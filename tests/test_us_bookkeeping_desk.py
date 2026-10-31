import importlib.util,sys,tempfile,unittest
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
if __name__=="__main__":unittest.main()
