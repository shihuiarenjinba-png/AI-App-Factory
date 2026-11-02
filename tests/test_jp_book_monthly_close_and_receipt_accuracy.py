import importlib.util,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def load(name,path):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);sys.modules[s.name]=m;s.loader.exec_module(m);return m
core=load("jp_book_core_close",ROOT/"products"/"jp-bookkeeping-desk"/"core.py")
close=load("jp_book_monthly_close",ROOT/"products"/"jp-bookkeeping-desk"/"monthly_close.py")
acc=load("jp_book_receipt_accuracy",ROOT/"products"/"jp-bookkeeping-desk"/"receipt_accuracy.py")
class T(unittest.TestCase):
 def test_monthly_package(self):
  with tempfile.TemporaryDirectory() as td:
   s=core.Store(Path(td)/"x.db")
   s.post("2026-11-01","売上",[("1100","10000",""),("4000","","10000")])
   out=close.export_month_end_package(s,2026,11,Path(td)/"out")
   self.assertTrue(Path(out["html"]).exists());self.assertTrue(Path(out["csv"]).exists());self.assertTrue(Path(out["json"]).exists())
   self.assertTrue(s.balance_check()["balanced"]);s.close()
 def test_month_cutoff_and_prior_year_unclosed_profit(self):
  import json
  with tempfile.TemporaryDirectory() as td:
   s=core.Store(Path(td)/"period.db")
   try:
    s.post("2025-12-31","前年の未振替売上",[("1100","1000",""),("4000","","1000")])
    s.post("2026-01-05","一月売上",[("1100","10000",""),("4000","","10000")])
    s.post("2026-01-20","一月経費",[("5200","3000",""),("1100","","3000")])
    s.post("2026-02-10","二月売上",[("1100","7000",""),("4000","","7000")])
    s.post("2026-03-01","三月の後日仕訳",[("1100","9000",""),("4000","","9000")])
    jan=close.export_month_end_package(s,2026,1,Path(td)/"jan")
    feb=close.export_month_end_package(s,2026,2,Path(td)/"feb")
    j=json.loads(Path(jan["json"]).read_text(encoding="utf-8"))
    f=json.loads(Path(feb["json"]).read_text(encoding="utf-8"))
    self.assertEqual(j["as_of_date"],"2026-01-31")
    self.assertEqual(j["journal_lines"],4)
    self.assertEqual(j["pnl_month"]["利益"],7000)
    self.assertEqual(j["pnl_year_to_date"]["利益"],7000)
    self.assertEqual(j["balance_sheet"]["資産"],8000)
    self.assertEqual(j["balance_sheet"]["前期以前の未振替損益"],1000)
    self.assertTrue(j["balance_check"]["bs_balanced"])
    self.assertEqual(f["pnl_month"]["利益"],7000)
    self.assertEqual(f["pnl_year_to_date"]["利益"],14000)
    self.assertEqual(f["balance_sheet"]["資産"],15000)
    self.assertTrue(f["balance_check"]["balanced"])
    self.assertTrue(f["month_balance_check"]["balanced"])
    self.assertIn("未処理証憑",Path(jan["html"]).read_text(encoding="utf-8"))
    self.assertIn("当月損益",Path(jan["html"]).read_text(encoding="utf-8"))
    s.post("2026-01-25","一月遡及訂正",[("5200","1000",""),("1100","","1000")])
    corrected=close.export_month_end_package(s,2026,1,Path(td)/"jan-corrected")
    c=json.loads(Path(corrected["json"]).read_text(encoding="utf-8"))
    self.assertEqual(c["pnl_month"]["利益"],6000)
    self.assertEqual(c["balance_sheet"]["資産"],7000)
    self.assertTrue(c["balance_check"]["bs_balanced"])
    self.assertEqual(j["pnl_month"]["利益"],7000) # prior export is immutable
    with self.assertRaises(ValueError):
     close.export_month_end_package(s,2026,13,Path(td)/"bad")
   finally:s.close()
 def test_future_receipt_is_current_queue_not_historical_month_end(self):
  import json
  with tempfile.TemporaryDirectory() as td:
   s=core.Store(Path(td)/"receipts.db")
   try:
    s.post("2026-01-15","一月売上",[("1100","1000",""),("4000","","1000")])
    self.assertEqual(s.enqueue_receipts(["future-receipt.png"]),1)
    s.conn.execute("UPDATE receipt_queue SET created_at='2026-12-01 09:00:00' WHERE file_path='future-receipt.png'")
    s.conn.commit()
    result=close.export_month_end_package(s,2026,1,Path(td)/"jan")
    data=json.loads(Path(result["json"]).read_text(encoding="utf-8"))
    self.assertEqual(data["unprocessed_receipts"],1)
    self.assertEqual(data["unprocessed_receipts_scope"],"CURRENT_QUEUE_ALL_DATES_NOT_HISTORICAL_AS_OF")
    # This new receipt has a verified enqueue event after January; a manually
    # edited legacy created_at must not replace the append-only event timestamp.
    self.assertEqual(data["unprocessed_receipts_as_of_month_end"],0)
    self.assertEqual(data["receipt_history_status"],"VERIFIED_HISTORY_ONLY")
    html=Path(result["html"]).read_text(encoding="utf-8")
    self.assertIn("現在の未処理証憑 1件",html)
    self.assertIn("月末時点の未処理証憑：0件",html)
    self.assertTrue(data["balance_check"]["balanced"])
   finally:s.close()
 def test_unsafe_autopost_fails(self):
  truths=[acc.ReceiptTruth("1","2026-11-01","店A","5000",None,None,True)]
  preds=[acc.ReceiptPrediction("1","2026-11-01","店A","5000",None,(),False,True)]
  m=acc.evaluate(truths,preds)
  self.assertEqual(m["unsafe_auto_post_count"],1)
  self.assertFalse(acc.release_gate(m)["pass"])
if __name__=="__main__":unittest.main()
