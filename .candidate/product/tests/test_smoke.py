"""Headless image inventory functional tests."""
import csv, struct, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import main as app

class Tests(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory();self.addCleanup(t.cleanup);self.d=Path(t.name)
        self.png=self.d/"a.png"
        self.png.write_bytes(b"\x89PNG\r\n\x1a\n"+struct.pack(">I",13)+b"IHDR"+struct.pack(">II",640,480)+b"\x08\x02\x00\x00\x00")
    def test_png(self):
        r=app.inspect_image(self.png);self.assertEqual((r["format"],r["width"],r["height"]),("PNG",640,480))
    def test_gif(self):
        p=self.d/"a.gif";p.write_bytes(b"GIF89a"+struct.pack("<HH",320,240))
        self.assertEqual(app.inspect_image(p)["height"],240)
    def test_bmp(self):
        p=self.d/"a.bmp";p.write_bytes(b"BM"+b"\0"*12+struct.pack("<I",40)+struct.pack("<ii",64,-32))
        self.assertEqual(app.inspect_image(p)["height"],32)
    def test_jpeg(self):
        p=self.d/"a.jpg";p.write_bytes(b"\xff\xd8\xff\xc0\x00\x0b\x08\x00\x28\x00\x50\x03\x01\x11\x00\xff\xd9")
        self.assertEqual(app.inspect_image(p)["width"],80)
    def test_bad_jpeg_segment(self):
        p=self.d/"a.jpg";p.write_bytes(b"\xff\xd8\xff\xe0\xff\xff")
        with self.assertRaises(ValueError):app.inspect_image(p)
    def test_no_jpeg_frame(self):
        p=self.d/"a.jpg";p.write_bytes(b"\xff\xd8\xff\xd9")
        with self.assertRaises(ValueError):app.inspect_image(p)
    def test_bad_png(self):
        p=self.d/"bad.png";p.write_bytes(b"\x89PNG\r\n\x1a\n"+b"\0"*16)
        with self.assertRaises(ValueError):app.inspect_image(p)
    def test_bad_gif(self):
        p=self.d/"bad.gif";p.write_bytes(b"GIF89a")
        with self.assertRaises(ValueError):app.inspect_image(p)
    def test_bad_bmp(self):
        p=self.d/"bad.bmp";p.write_bytes(b"BM"+b"\0"*24)
        with self.assertRaises(ValueError):app.inspect_image(p)
    def test_zero_dimension(self):
        p=self.d/"bad.png";p.write_bytes(b"\x89PNG\r\n\x1a\n"+struct.pack(">I",13)+b"IHDR"+struct.pack(">II",0,10))
        with self.assertRaises(ValueError):app.inspect_image(p)
    def test_unsupported(self):
        p=self.d/"a.txt";p.write_text("hello")
        with self.assertRaises(ValueError):app.inspect_image(p)
    def test_missing(self):
        with self.assertRaises(FileNotFoundError):app.inspect_image(self.d/"missing")
    def test_symlink(self):
        p=self.d/"link.png"
        try:p.symlink_to(self.png)
        except (OSError,NotImplementedError):return
        with self.assertRaises(ValueError):app.inspect_image(p)
    def test_oversize(self):
        p=self.d/"big.png"
        with p.open("wb") as f:f.truncate(app.MAX_BYTES+1)
        with self.assertRaises(ValueError):app.inspect_image(p)
    def test_scan_partial(self):
        rows,errors=app.scan([self.png,self.png,self.d/"missing"])
        self.assertEqual((len(rows),len(errors)),(1,2))
    def test_scan_limit(self):
        with self.assertRaises(ValueError):app.scan([self.png]*201)
    def test_append_preserves_snapshot_if_old_file_disappears(self):
        old = app.inspect_image(self.png)
        self.png.unlink()
        new = self.d / "new.gif"
        new.write_bytes(b"GIF89a" + struct.pack("<HH", 12, 34))
        rows, errors = app.append_images([old], [new])
        self.assertEqual(errors, [])
        self.assertEqual(rows[0], old)
        self.assertEqual((rows[1]["width"], rows[1]["height"]), (12, 34))

    def test_append_duplicate_does_not_modify_existing_rows(self):
        old = app.inspect_image(self.png)
        rows, errors = app.append_images([old], [self.png])
        self.assertEqual(rows, [old])
        self.assertEqual(len(errors), 1)
        self.assertIn("Duplicate", errors[0][1])

    def test_append_bad_new_file_preserves_existing_rows(self):
        old = app.inspect_image(self.png)
        rows, errors = app.append_images([old], [self.d / "missing.png"])
        self.assertEqual(rows, [old])
        self.assertEqual(len(errors), 1)

    def test_session_roundtrip(self):
        rows=[app.inspect_image(self.png)];p=self.d/"s.json";app.save_session(p,rows)
        self.assertEqual(app.load_session(p)["paths"],[str(self.png)])
    def test_backup(self):
        rows=[app.inspect_image(self.png)];p=self.d/"s.json"
        app.save_session(p,rows);app.save_session(p,rows);p.write_text("{broken")
        self.assertEqual(app.recover_session(p)["paths"],[str(self.png)])
    def test_invalid_schema(self):
        for value in ({"schema":True,"paths":[]},{"schema":1,"paths":["relative"]},
                      {"schema":1,"paths":["/a","/a"]},{"schema":1,"paths":[],"extra":1}):
            with self.assertRaises(ValueError):app.validate_session(value)
    def test_csv_and_source_protection(self):
        rows=[app.inspect_image(self.png)];p=self.d/"out.csv";before=self.png.read_bytes()
        app.export_csv(p,rows)
        with p.open(encoding="utf-8",newline="") as f:self.assertEqual(list(csv.DictReader(f))[0]["width"],"640")
        with self.assertRaises(ValueError):app.export_csv(self.png,rows)
        self.assertEqual(self.png.read_bytes(),before)
    def test_empty_export(self):
        with self.assertRaises(ValueError):app.export_csv(self.d/"out.csv",[])
    def test_output_symlink(self):
        p=self.d/"link.csv"
        try:p.symlink_to(self.png)
        except (OSError,NotImplementedError):return
        with self.assertRaises(ValueError):app.export_csv(p,[app.inspect_image(self.png)])
    def msix_row(self, fmt="PNG", width=1366, height=768, size=1000):
        return {"path":str(self.png),"format":fmt,"width":width,"height":height,"bytes":size}

    def test_msix_landscape_basic_candidate_is_not_certification(self):
        code,reason=app.check_msix_screenshot(self.msix_row())
        self.assertEqual(code,"BASIC_CANDIDATE")
        self.assertIn("review",reason.lower())

    def test_msix_rejects_jpeg_even_at_valid_dimensions(self):
        self.assertEqual(app.check_msix_screenshot(self.msix_row(fmt="JPEG"))[0],"FAIL_FORMAT")

    def test_msix_rejects_small_landscape(self):
        self.assertEqual(app.check_msix_screenshot(self.msix_row(width=1024,height=768))[0],"FAIL_DIMENSIONS")

    def test_msix_portrait_requires_manual_review_not_false_reject(self):
        self.assertEqual(app.check_msix_screenshot(self.msix_row(width=768,height=1366))[0],"REVIEW_PORTRAIT")
        self.assertEqual(app.check_msix_screenshot(self.msix_row(width=600,height=1000))[0],"FAIL_DIMENSIONS")

    def test_msix_size_boundary_is_manual_review(self):
        self.assertEqual(app.check_msix_screenshot(self.msix_row(size=49_999_999))[0],"BASIC_CANDIDATE")
        for size in (50_000_000,50_000_001,50*1024*1024):
            self.assertEqual(app.check_msix_screenshot(self.msix_row(size=size))[0],"REVIEW_SIZE_LIMIT")
        self.assertEqual(app.check_msix_screenshot(self.msix_row(size=50*1024*1024+1))[0],"FAIL_SIZE")

    def test_msix_summary_over_ten_is_warning_not_certification(self):
        rows=[self.msix_row() for _ in range(11)]
        report=app.msix_summary(rows)
        self.assertTrue(report["over_limit"])
        self.assertEqual(report["issues"],0)
        self.assertEqual(report["counts"]["BASIC_CANDIDATE"],11)

    def test_msix_csv_preserves_image_and_protects_source(self):
        row=self.msix_row(fmt="JPEG")
        path=self.d/"msix-report.csv"
        before=self.png.read_bytes()
        app.export_msix_csv(path,[row])
        with path.open(encoding="utf-8",newline="") as stream:
            report=list(csv.DictReader(stream))
        self.assertEqual(report[0]["msix_check"],"FAIL_FORMAT")
        self.assertEqual(report[0]["profile_source"],app.MSIX_PROFILE_URL)
        self.assertEqual(report[0]["desktop_limit"],"10")
        self.assertEqual(self.png.read_bytes(),before)
        with self.assertRaises(ValueError):
            app.export_msix_csv(self.png,[row])

    def test_msix_csv_empty_is_rejected(self):
        with self.assertRaises(ValueError):app.export_msix_csv(self.d/"empty.csv",[])

    def test_filter_dimensions_capacity_orientation_and_original_index(self):
        rows=[
            self.msix_row(width=1600,height=900,size=3*1048576),
            self.msix_row(width=900,height=1600,size=1048576),
            self.msix_row(width=1024,height=1024,size=512),
            self.msix_row(width=2000,height=1000,size=1048576),
        ]
        self.assertEqual([i for i,_ in app.select_inventory(rows,orientation="landscape")],[0,3])
        self.assertEqual([i for i,_ in app.select_inventory(rows,orientation="portrait")],[1])
        self.assertEqual([i for i,_ in app.select_inventory(rows,orientation="square")],[2])
        self.assertEqual([i for i,_ in app.select_inventory(rows,min_width=1366,min_height=768,
                           max_bytes=2*1048576)],[3])
        self.assertEqual(len(rows),4)

    def test_filter_issues_only_and_preserves_source_rows(self):
        rows=[self.msix_row(),self.msix_row(fmt="JPEG"),self.msix_row(width=900)]
        original=[dict(row) for row in rows]
        self.assertEqual([i for i,_ in app.select_inventory(rows,issues_only=True)],[1,2])
        self.assertEqual(rows,original)

    def test_filter_rejects_invalid_inputs(self):
        row=[self.msix_row()]
        for kwargs in ({"orientation":"diagonal"},{"min_width":-1},
                       {"min_height":True},{"max_bytes":0},
                       {"max_bytes":float("nan")},{"issues_only":1}):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ValueError):app.select_inventory(row,**kwargs)

    def test_msix_batch_over_limit_is_explicit_in_export(self):
        rows=[self.msix_row() for _ in range(11)]
        self.assertTrue(app.msix_summary(rows)["over_limit"])
        p=self.d/"batch.csv"
        app.export_msix_csv(p,rows)
        with p.open(encoding="utf-8",newline="") as f:
            report=list(csv.DictReader(f))
        self.assertEqual(len(report),11)
        self.assertEqual({r["batch_check"] for r in report},{"REVIEW_BATCH_LIMIT"})
        self.assertEqual({r["msix_check"] for r in report},{"BASIC_CANDIDATE"})
        app.export_msix_csv(p,rows[:10])
        with p.open(encoding="utf-8",newline="") as f:
            report=list(csv.DictReader(f))
        self.assertEqual({r["batch_check"] for r in report},{""})

    def test_bilingual(self):
        self.assertEqual(set(app.LABELS["ja"]),set(app.LABELS["en"]))
        self.assertTrue(callable(app.main))
if __name__=="__main__":unittest.main()
