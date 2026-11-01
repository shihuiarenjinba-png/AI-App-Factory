"""Product-specific regression fixtures for read-only image delivery evidence."""
import csv, hashlib, json, struct, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import main as app
import snapshot_compare as snap

class SnapshotTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        self.base=Path(tmp.name);self.folder=self.base/"photos";self.folder.mkdir()
    def image(self,name,w=640,h=480,tail=b""):
        p=self.folder/name;p.parent.mkdir(parents=True,exist_ok=True)
        p.write_bytes(b"\x89PNG\r\n\x1a\n"+struct.pack(">I",13)+b"IHDR"+struct.pack(">II",w,h)+b"\x08\x02\x00\x00\x00"+tail)
        return p
    def capture(self):return snap.capture_folder(self.folder,app.inspect_image)
    def test_repeat_deterministic(self):
        self.image("a.png");a=self.capture()
        self.assertEqual(a,self.capture())
        self.assertEqual(snap.compare_snapshots(a,a)["summary"]["UNCHANGED"],1)
    def test_added_removed_same_name_changed(self):
        p=self.image("a.png",tail=b"first");self.image("gone.png");old=self.capture()
        p.write_bytes(p.read_bytes().replace(b"first",b"other"))
        (self.folder/"gone.png").unlink();self.image("new.png")
        report=snap.compare_snapshots(old,self.capture())
        self.assertEqual(report["summary"],{"ADDED":1,"REMOVED":1,"MODIFIED":1,"UNCHANGED":0})
        self.assertEqual([r["status"] for r in report["changes"]],["MODIFIED","REMOVED","ADDED"])
    def test_dimension_change(self):
        self.image("same.png",100,100);old=self.capture();self.image("same.png",200,100)
        self.assertEqual(snap.compare_snapshots(old,self.capture())["summary"]["MODIFIED"],1)
    def test_order_recursive(self):
        self.image("z.png");self.image("a/second.png");self.image("a/first.png")
        self.assertEqual([r["relative_path"] for r in self.capture()["files"]],["a/first.png","a/second.png","z.png"])
    def test_symlink_file_fail_closed(self):
        p=self.image("target.png");link=self.folder/"linked.png"
        try:link.symlink_to(p)
        except (OSError,NotImplementedError):self.skipTest("No symlink permission")
        result=self.capture();self.assertTrue(result["errors"])
        with self.assertRaises(ValueError):snap.compare_snapshots(result,result)
    def test_symlink_directory_fail_closed(self):
        other=self.base/"other";other.mkdir();link=self.folder/"linkdir"
        try:link.symlink_to(other,target_is_directory=True)
        except (OSError,NotImplementedError):self.skipTest("No symlink permission")
        self.assertTrue(self.capture()["errors"])
    def test_read_error_fail_closed(self):
        self.image("a.png")
        def denied(path):raise PermissionError("denied")
        result=snap.capture_folder(self.folder,denied)
        self.assertEqual(result["errors"][0]["error"],"PermissionError")
        with self.assertRaises(ValueError):snap.compare_snapshots(result,result)
    def test_changed_during_scan(self):
        self.image("a.png")
        def mutate(path):
            info=app.inspect_image(path);path.write_bytes(path.read_bytes()+b"changed");return info
        self.assertTrue(snap.capture_folder(self.folder,mutate)["errors"])
    def test_csv_json_restart_and_image_unchanged(self):
        p=self.image("a.png");original=p.read_bytes();old=self.capture()
        saved=self.base/"baseline.json";snap.write_snapshot(saved,old,app.atomic_write)
        loaded=snap.load_snapshot(saved);self.assertEqual(loaded,old)
        report=snap.compare_snapshots(loaded,self.capture())
        c,j=self.base/"report.csv",self.base/"report.json"
        snap.write_comparison(c,report,app.atomic_write)
        snap.write_comparison(j,report,app.atomic_write)
        with c.open(encoding="utf-8",newline="") as f:
            self.assertEqual(list(csv.DictReader(f))[0]["status"],"UNCHANGED")
        self.assertEqual(json.loads(j.read_text(encoding="utf-8")),report)
        self.assertEqual(p.read_bytes(),original)
        for forbidden in (self.folder/"report.csv",p):
            with self.assertRaises(ValueError):snap.write_comparison(forbidden,report,app.atomic_write)
        self.assertEqual(p.read_bytes(),original)
    def test_same_name_other_root(self):
        p=self.image("a.png",tail=b"first");old=self.capture()
        other=self.base/"other";other.mkdir()
        (other/"a.png").write_bytes(p.read_bytes().replace(b"first",b"other"))
        new=snap.capture_folder(other,app.inspect_image)
        self.assertEqual(snap.compare_snapshots(old,new)["summary"]["MODIFIED"],1)
    def test_invalid_paths_and_duplicate(self):
        self.image("a.png");old=self.capture()
        for name in ("../bad.png","/abs.png","C:/bad.png","x\\bad.png"):
            bad=json.loads(json.dumps(old));bad["files"][0]["relative_path"]=name
            with self.assertRaises(ValueError):snap.validate_snapshot(bad)
        bad=json.loads(json.dumps(old));bad["files"].append(dict(bad["files"][0]))
        with self.assertRaises(ValueError):snap.validate_snapshot(bad)
    def test_limit(self):
        for i in range(201):self.image("%03d.png"%i)
        with self.assertRaisesRegex(ValueError,"More than 200"):self.capture()
    def test_full_content_sha(self):
        p=self.image("a.png",tail=b"hello")
        self.assertEqual(self.capture()["files"][0]["sha256"],hashlib.sha256(p.read_bytes()).hexdigest())


    def test_delivery_summary_export_and_restart(self):
        p=self.image("a.png",tail=b"first");self.image("gone.png")
        old=self.capture();old_sha=hashlib.sha256(p.read_bytes()).hexdigest()
        p.write_bytes(p.read_bytes().replace(b"first",b"other"))
        (self.folder/"gone.png").unlink();added=self.image("new.png")
        report=snap.compare_snapshots(old,self.capture())
        from datetime import datetime, timezone
        moment=datetime(2026,11,1,14,0,tzinfo=timezone.utc)
        txt=snap.render_delivery_summary(report,"en",moment)
        self.assertEqual(txt,snap.render_delivery_summary(report,"en",moment))
        for marker in ("Added 1","Removed 1","Modified 1","2026-11-01 14:00:00 UTC",
                       "Time limitation","Read/link errors: 0","no deletion",old_sha,
                       hashlib.sha256(p.read_bytes()).hexdigest(),
                       hashlib.sha256(added.read_bytes()).hexdigest()):
            self.assertIn(marker,txt)
        self.assertIn("日時の限界",snap.render_delivery_summary(report,"ja",moment))
        before={f.name:f.read_bytes() for f in self.folder.glob("*.png")}
        output=self.base/"summary.txt"
        snap.write_delivery_summary(output,report,app.atomic_write,"ja")
        self.assertIn("SHA-256",output.read_text(encoding="utf-8"))
        self.assertEqual(before,{f.name:f.read_bytes() for f in self.folder.glob("*.png")})
        with self.assertRaises(ValueError):
            snap.write_delivery_summary(self.folder/"summary.txt",report,app.atomic_write)

    def test_summary_errors_and_1024_width(self):
        self.image("a.png");old=self.capture();report=snap.compare_snapshots(old,self.capture())
        import copy
        corrupt=copy.deepcopy(report);corrupt["summary"]["ADDED"]=1
        with self.assertRaises(ValueError):snap.render_delivery_summary(corrupt)
        corrupt=copy.deepcopy(report);corrupt["changes"][0]["old_sha256"]="invalid"
        with self.assertRaises(ValueError):snap.render_delivery_summary(corrupt)
        def denied(path):raise PermissionError("denied")
        with self.assertRaises(ValueError):
            snap.compare_snapshots(old,snap.capture_folder(self.folder,denied))
        link=self.folder/"linked.png"
        try:link.symlink_to(self.folder/"a.png")
        except (OSError,NotImplementedError):pass
        else:
            with self.assertRaises(ValueError):snap.compare_snapshots(old,self.capture())
        source=Path(app.__file__).read_text(encoding="utf-8")
        self.assertIn('root.geometry("1024x768")',source)
        self.assertIn('summarybar=ttk.Frame(body)',source)
        self.assertIn('command=self.export_delivery_summary',source)


    def test_failed_rescan_clears_previous_exportable_report(self):
        """A prior successful comparison must never be exportable after read failure."""
        from unittest.mock import Mock, patch
        self.image("a.png")
        baseline=self.capture()
        fake=Mock()
        fake.baseline=baseline
        fake.comparison=snap.compare_snapshots(baseline,baseline)
        fake.root=object()
        fake.status=Mock()
        fake.t=lambda key: app.LABELS["en"][key]
        fake.error=Mock()
        with patch.object(app.filedialog,"askdirectory",return_value=str(self.folder)), \
             patch.object(app,"inspect_image",side_effect=PermissionError("denied")):
            app.Desk.compare_folder(fake)
        self.assertIsNone(fake.comparison)
        fake.error.assert_called_once()
        fake.status.set.assert_called_with(app.LABELS["en"]["snap_failed"])

if __name__=="__main__":unittest.main()
