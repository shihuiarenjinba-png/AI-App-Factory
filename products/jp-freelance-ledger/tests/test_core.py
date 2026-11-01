import importlib.util,sys,tempfile,unittest
from pathlib import Path
P=Path(__file__).resolve().parents[1]/"core.py"; S=importlib.util.spec_from_file_location("jpfl",P); m=importlib.util.module_from_spec(S); sys.modules[S.name]=m; S.loader.exec_module(m)
class T(unittest.TestCase):
 def test_jpy_and_summary(self):
  with tempfile.TemporaryDirectory() as d:
   s=m.Store(Path(d)/"x.db"); s.add("2026-10-01","収入","10000","売上高"); s.add("2026-10-02","経費","1200","通信費")
   self.assertEqual(s.monthly(2026,10)["差引"],8800); s.close()
 def test_date(self): self.assertRaises(m.LedgerError,m.validate_date,"10/31/2026")
if __name__=="__main__":unittest.main()
