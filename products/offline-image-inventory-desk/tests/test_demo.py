"""Independent regression of first-run sample, without real buyer answers."""
import csv
import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import demo_samples
import main as app
import snapshot_compare as snapshots


class DemoTests(unittest.TestCase):
    def test_four_changes_and_original_sha_after_exports(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            before,after=demo_samples.populate_demo(root)
            original=(demo_samples.hashes(before),demo_samples.hashes(after))
            baseline=snapshots.capture_folder(before,app.inspect_image)
            current=snapshots.capture_folder(after,app.inspect_image)
            self.assertFalse(baseline["errors"])
            self.assertFalse(current["errors"])
            report=snapshots.compare_snapshots(baseline,current)
            self.assertEqual(report["summary"],{"ADDED":1,"REMOVED":1,"MODIFIED":1,"UNCHANGED":1})
            self.assertEqual({r["relative_path"]:r["status"] for r in report["changes"]},
                             demo_samples.EXPECTED)
            for ext in ("csv","json"):
                output=root/("sample."+ext)
                snapshots.write_comparison(output,report,app.atomic_write)
                self.assertTrue(output.is_file())
            txt=root/"sample.txt"
            snapshots.write_delivery_summary(txt,report,app.atomic_write,"ja")
            self.assertIn("お客様への確認ポイント",txt.read_text(encoding="utf-8"))
            with (root/"sample.csv").open(encoding="utf-8",newline="") as f:
                self.assertEqual(len(list(csv.DictReader(f))),4)
            self.assertEqual(json.loads((root/"sample.json").read_text(encoding="utf-8"))["summary"],report["summary"])
            self.assertEqual(original,(demo_samples.hashes(before),demo_samples.hashes(after)))
            self.assertEqual(len(list(root.rglob("*.png"))),6)

    def test_refuses_existing_nonempty_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            original=root/"private.txt"
            original.write_text("do not change",encoding="utf-8")
            with self.assertRaises(ValueError):
                demo_samples.populate_demo(root)
            self.assertEqual(original.read_text(encoding="utf-8"),"do not change")

    def test_demo_is_not_buyer_evidence(self):
        self.assertIn("SAMPLE",app.LABELS["en"]["snap_demo_done"])
        self.assertIn("見本",app.LABELS["ja"]["snap_demo_done"])
        self.assertIn("1.",app.LABELS["en"]["snap_intro"])
        self.assertIn("1.",app.LABELS["ja"]["snap_intro"])
        self.assertNotIn("why_pay_verified",Path(demo_samples.__file__).read_text(encoding="utf-8"))
        self.assertTrue(callable(app.Desk.try_demo))


if __name__=="__main__":
    unittest.main()
