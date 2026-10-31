import importlib.util,sys,tempfile,unittest
from pathlib import Path
P=Path(__file__).resolve().parents[1]/"products"/"jp-freelance-ledger"/"core.py"; S=importlib.util.spec_from_file_location("jpfl_factory",P); m=importlib.util.module_from_spec(S); sys.modules[S.name]=m; S.loader.exec_module(m)
class T(unittest.TestCase):
 def test_japan_only_contract(self):
  self.assertTrue(all(isinstance(x,str) for x in m.CATEGORIES))
  with tempfile.TemporaryDirectory() as d:
   s=m.Store(Path(d)/"x.db"); s.add("2026-10-31","収入","5000","売上高"); self.assertEqual(s.monthly(2026,10)["収入"],5000); s.close()
if __name__=="__main__":unittest.main()
