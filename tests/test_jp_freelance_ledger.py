import importlib.util,sys,tempfile,unittest
from pathlib import Path
P=Path(__file__).resolve().parents[1]/"products"/"jp-freelance-ledger"/"core.py"; S=importlib.util.spec_from_file_location("jpfl_factory",P); m=importlib.util.module_from_spec(S); sys.modules[S.name]=m; S.loader.exec_module(m)
class T(unittest.TestCase):
 def test_japan_only_contract(self):
  self.assertTrue(all(isinstance(x,str) for x in m.CATEGORIES))
  with tempfile.TemporaryDirectory() as d:
   s=m.Store(Path(d)/"x.db"); s.add("2026-10-31","収入","5000","売上高"); self.assertEqual(s.monthly(2026,10)["収入"],5000); s.close()
 def test_local_account_suggestion(self):
  x=m.suggest_category("NTT 通信回線の月額料金","経費")
  self.assertTrue(x); self.assertEqual(x[0]["category"],"通信費")
 def test_annual_net(self):
  with tempfile.TemporaryDirectory() as d:
   s=m.Store(Path(d)/"x.db");s.add("2026-01-01","収入","10000","売上高");s.add("2026-02-01","経費","2000","通信費");self.assertEqual(s.annual_summary(2026)["差引"],8000);s.close()
if __name__=="__main__":unittest.main()
