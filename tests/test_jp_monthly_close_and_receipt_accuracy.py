import importlib.util,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def load(name,path):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);sys.modules[s.name]=m;s.loader.exec_module(m);return m
core=load("jp_fl_core_close",ROOT/"products"/"jp-freelance-ledger"/"core.py")
close=load("jp_fl_monthly_close",ROOT/"products"/"jp-freelance-ledger"/"monthly_close.py")
acc=load("jp_fl_receipt_accuracy",ROOT/"products"/"jp-freelance-ledger"/"receipt_accuracy.py")
class T(unittest.TestCase):
 def test_monthly_package(self):
  with tempfile.TemporaryDirectory() as td:
   s=core.Store(Path(td)/"x.db")
   s.add("2026-11-01","収入","10000","売上高","A社","請求書","","制作料")
   s.add("2026-11-02","経費","1200","通信費","通信会社","領収書","","回線")
   out=close.export_month_end_package(s,2026,11,Path(td)/"out")
   self.assertTrue(Path(out["html"]).exists());self.assertTrue(Path(out["csv"]).exists());self.assertTrue(Path(out["json"]).exists())
   s.close()
 def test_accuracy_gate(self):
  truths=[acc.ReceiptTruth("1","2026-11-01","店A","1100","100","通信費",True)]
  preds=[acc.ReceiptPrediction("1","2026-11-01","店A","1100","100",("通信費",),True,False)]
  m=acc.evaluate(truths,preds)
  self.assertEqual(m["unsafe_auto_post_count"],0)
  self.assertEqual(m["account_top1_pct"],100.0)
  self.assertFalse(acc.release_gate(m)["pass"])
  self.assertFalse(acc.release_gate(m,benchmark_source="user_owned_local_labeled")["pass"])
  self.assertEqual(m["high_risk_cases"],1)
if __name__=="__main__":unittest.main()
