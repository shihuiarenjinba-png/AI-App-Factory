import importlib.util,sys,tempfile,unittest
from pathlib import Path
P=Path(__file__).resolve().parents[1]/"products"/"jp-bookkeeping-desk"/"core.py";S=importlib.util.spec_from_file_location("jpb_factory",P);m=importlib.util.module_from_spec(S);sys.modules[S.name]=m;S.loader.exec_module(m)
class T(unittest.TestCase):
 def test_jp_chart(self):
  with tempfile.TemporaryDirectory() as d:
   s=m.Store(Path(d)/"x.db");self.assertIn("現金",{x["name"] for x in s.accounts()});s.close()
 def test_journal_suggestion(self):
  x=m.suggest_entry("事務所 家賃の支払い");self.assertEqual(x["debit_code"],"5200");self.assertEqual(x["credit_code"],"1100")
 def test_balance_check(self):
  with tempfile.TemporaryDirectory() as d:
   s=m.Store(Path(d)/"x.db");s.post("2026-10-31","売上",[("1000","10000",""),("4000","","10000")]);self.assertTrue(s.balance_check()["balanced"]);s.close()
if __name__=="__main__":unittest.main()
