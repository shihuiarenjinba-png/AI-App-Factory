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
if __name__=="__main__":unittest.main()
