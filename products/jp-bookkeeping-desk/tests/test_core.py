import importlib.util,sys,tempfile,unittest
from pathlib import Path
P=Path(__file__).resolve().parents[1]/"core.py";S=importlib.util.spec_from_file_location("jpb",P);m=importlib.util.module_from_spec(S);sys.modules[S.name]=m;S.loader.exec_module(m)
class T(unittest.TestCase):
 def test_double_entry(self):
  with tempfile.TemporaryDirectory() as d:
   s=m.Store(Path(d)/"x.db");s.post("2026-10-31","売上",[("1000","10000",""),("4000","","10000")]);self.assertEqual(s.pnl()["利益"],10000);self.assertEqual(s.bs()["資産"],10000);s.close()
if __name__=="__main__":unittest.main()
