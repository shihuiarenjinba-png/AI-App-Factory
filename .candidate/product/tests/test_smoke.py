"""Headless image inventory functional tests."""
import csv, os, struct, sys, tempfile, unittest
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

    def test_store_review_preset_clears_stale_filters_and_shows_issues(self):
        class Var:
            def __init__(self,value):self.value=value
            def set(self,value):self.value=value
            def get(self):return self.value
        desk=app.Desk.__new__(app.Desk)
        desk.orientation=Var("portrait");desk.min_width=Var("2000")
        desk.min_height=Var("1000");desk.max_mib=Var("1")
        desk.preflight=Var(False);desk.issues=Var(False)
        desk.active_filter={"orientation":"portrait","min_width":2000,
                            "min_height":1000,"max_bytes":1048576}
        calls=[]
        desk.localize=lambda:calls.append("localize")
        desk.refresh=lambda:calls.append("refresh")
        desk.store_review_preset()
        self.assertTrue(desk.preflight.get() and desk.issues.get())
        self.assertEqual(desk.active_filter,{"orientation":"all","min_width":0,
                                            "min_height":0,"max_bytes":None})
        self.assertEqual([desk.orientation.get(),desk.min_width.get(),
                          desk.min_height.get(),desk.max_mib.get()],["all","","",""])
        self.assertEqual(calls,["localize","refresh"])

    def test_duplicate_groups_hash_equal_bytes_without_mutation(self):
        second=self.d/"second.png"
        third=self.d/"third.png"
        second.write_bytes(self.png.read_bytes())
        changed=bytearray(self.png.read_bytes());changed[-1]^=1
        third.write_bytes(changed)
        original=[self.png.read_bytes(),second.read_bytes(),third.read_bytes()]
        rows=[app.inspect_image(p) for p in (self.png,second,third)]
        groups,errors=app.find_duplicate_groups(rows)
        self.assertEqual(errors,[])
        self.assertEqual(groups,{0:"D1",1:"D1"})
        self.assertEqual(original,[self.png.read_bytes(),second.read_bytes(),third.read_bytes()])

    def test_duplicate_groups_skip_changed_or_missing_files(self):
        second=self.d/"second.png"
        second.write_bytes(self.png.read_bytes())
        rows=[app.inspect_image(p) for p in (self.png,second)]
        second.write_bytes(second.read_bytes()+b"x")
        groups,errors=app.find_duplicate_groups(rows)
        self.assertEqual(groups,{})
        self.assertEqual(len(errors),1)
        self.assertIn("size",errors[0][1].lower())
        second.unlink()
        groups,errors=app.find_duplicate_groups(rows)
        self.assertEqual(groups,{})
        self.assertEqual(len(errors),1)

    def test_duplicate_groups_reject_stale_same_size_identical_bytes(self):
        """An identical re-save is still stale and must not receive a D-group."""
        copy=self.d/"copy.png"
        copy.write_bytes(self.png.read_bytes())
        rows=[app.inspect_image(p) for p in (self.png,copy)]
        original=copy.read_bytes()
        copy.write_bytes(original)
        changed_ns=rows[1]["modified_ns"]+5_000_000_000
        os.utime(copy,ns=(changed_ns,changed_ns))
        groups,errors=app.find_duplicate_groups(rows)
        self.assertEqual(groups,{})
        self.assertEqual(len(errors),1)
        self.assertIn("since inventory scan",errors[0][1])
        report,summary=app.build_review_report(rows)
        stale=next(r for r in report if r["path"]==str(copy))
        self.assertEqual(stale["source_check"],"SOURCE_CHANGED")
        self.assertTrue(stale["duplicate_scan_error"])
        self.assertEqual(summary["duplicate_files"],0)
        self.assertEqual(summary["hash_errors"],1)
        self.assertEqual(copy.read_bytes(),original)

    def test_duplicate_groups_accept_rescanned_same_size_copy(self):
        copy=self.d/"copy.png"
        copy.write_bytes(self.png.read_bytes())
        rows=[app.inspect_image(p) for p in (self.png,copy)]
        changed_ns=rows[1]["modified_ns"]+5_000_000_000
        os.utime(copy,ns=(changed_ns,changed_ns))
        self.assertEqual(app.find_duplicate_groups(rows)[0],{})
        refreshed=[app.inspect_image(p) for p in (self.png,copy)]
        groups,errors=app.find_duplicate_groups(refreshed)
        self.assertEqual(errors,[])
        self.assertEqual(groups,{0:"D1",1:"D1"})

    def test_duplicate_groups_legacy_rows_without_timestamp(self):
        copy=self.d/"copy.png"
        copy.write_bytes(self.png.read_bytes())
        rows=[app.inspect_image(p) for p in (self.png,copy)]
        for row in rows:row.pop("modified_ns")
        groups,errors=app.find_duplicate_groups(rows)
        self.assertEqual(errors,[])
        self.assertEqual(groups,{0:"D1",1:"D1"})

    def test_duplicate_groups_reject_symlinks_and_invalid_inventory(self):
        link=self.d/"linked.png"
        try:link.symlink_to(self.png)
        except (OSError,NotImplementedError):return
        rows=[app.inspect_image(self.png),dict(app.inspect_image(self.png),path=str(link))]
        groups,errors=app.find_duplicate_groups(rows)
        self.assertEqual(groups,{})
        self.assertEqual(len(errors),1)
        self.assertIn("Symlink",errors[0][1])
        for bad in (None,{},[{}]*201):
            with self.assertRaises(ValueError):app.find_duplicate_groups(bad)

    def test_find_duplicates_resets_stale_filters_and_issues_only(self):
        class Var:
            def __init__(self,value):self.value=value
            def set(self,value):self.value=value
            def get(self):return self.value
        desk=app.Desk.__new__(app.Desk)
        desk.rows=[app.inspect_image(self.png)]
        desk.orientation=Var("portrait");desk.min_width=Var("2000")
        desk.min_height=Var("1000");desk.max_mib=Var("1")
        desk.issues=Var(True)
        desk.active_filter={"orientation":"portrait","min_width":2000,
                            "min_height":1000,"max_bytes":1048576}
        desk.duplicate_groups={};desk.duplicates_only=False
        class Status:
            def set(self,value):self.value=value
        desk.status=Status()
        desk.t=lambda key:app.LABELS["en"][key]
        desk.refresh=lambda:None
        desk.error=lambda exc:self.fail(str(exc))
        desk.find_duplicates()
        self.assertTrue(desk.duplicates_only)
        self.assertFalse(desk.issues.get())
        self.assertEqual(desk.active_filter,{"orientation":"all","min_width":0,
                                            "min_height":0,"max_bytes":None})

    def test_selected_issue_action_is_bilingual_and_duplicate_safe(self):
        class Var:
            def __init__(self,value):self.value=value
            def get(self):return self.value
        class Tree:
            def selection(self):return ("0",)
        class Status:
            def set(self,value):self.value=value
        desk=app.Desk.__new__(app.Desk)
        desk.rows=[self.msix_row(fmt="JPEG")]
        desk.tree=Tree();desk.status=Status()
        desk.preflight=Var(True);desk.duplicate_groups={0:"D1"}
        desk.t=lambda key:app.LABELS[desk.language][key]
        desk.language="en"
        desk.show_selection_details()
        self.assertIn("Use a PNG screenshot",desk.status.value)
        self.assertIn("D1",desk.status.value)
        self.assertIn("review before deleting",desk.status.value)
        desk.language="ja"
        desk.show_selection_details()
        self.assertIn("PNG形式",desk.status.value)
        self.assertIn("D1",desk.status.value)
        self.assertIn("削除前に確認",desk.status.value)
        desk.preflight=Var(False)
        desk.show_selection_details()
        self.assertIn("Store要確認",desk.status.value)

    def test_selected_issue_empty_selection_is_noop(self):
        class EmptyTree:
            def selection(self):return ()
        desk=app.Desk.__new__(app.Desk)
        desk.tree=EmptyTree()
        desk.show_selection_details()


    def test_review_report_prioritizes_issues_and_exact_duplicates(self):
        copy=self.d/"copy.png"
        copy.write_bytes(self.png.read_bytes())
        good=self.d/"store.png"
        good.write_bytes(b"\x89PNG\r\n\x1a\n"+struct.pack(">I",13)+
                         b"IHDR"+struct.pack(">II",1366,768)+b"\x08\x02\x00\x00\x00")
        rows=[app.inspect_image(good),app.inspect_image(self.png),app.inspect_image(copy)]
        report,summary=app.build_review_report(rows)
        self.assertEqual(summary["images"],3)
        self.assertEqual(summary["duplicate_files"],2)
        self.assertEqual(summary["duplicate_groups"],1)
        self.assertEqual(summary["attention"],2)
        self.assertEqual([r["original_index"] for r in report],[2,3,1])
        self.assertEqual([r["duplicate_group"] for r in report],["D1","D1",""])
        self.assertEqual(report[-1]["needs_review"],"NO")
        self.assertEqual(report[-1]["msix_check"],"BASIC_CANDIDATE")

    def test_review_csv_is_read_only_and_reviewable(self):
        copy=self.d/"copy.png"
        copy.write_bytes(self.png.read_bytes())
        rows=[app.inspect_image(p) for p in (self.png,copy)]
        before=[p.read_bytes() for p in (self.png,copy)]
        output=self.d/"review.csv"
        summary=app.export_review_csv(output,rows)
        with output.open(encoding="utf-8",newline="") as stream:
            report=list(csv.DictReader(stream))
        self.assertEqual(summary["attention"],2)
        self.assertEqual([r["duplicate_group"] for r in report],["D1","D1"])
        self.assertEqual({r["needs_review"] for r in report},{"YES"})
        self.assertTrue(all(r["profile_source"]==app.MSIX_PROFILE_URL for r in report))
        self.assertEqual(before,[p.read_bytes() for p in (self.png,copy)])
        with self.assertRaises(ValueError):
            app.export_review_csv(self.png,rows)
        self.assertEqual(before,[p.read_bytes() for p in (self.png,copy)])

    def test_review_report_exposes_stale_duplicate_source(self):
        copy=self.d/"copy.png"
        copy.write_bytes(self.png.read_bytes())
        rows=[app.inspect_image(p) for p in (self.png,copy)]
        copy.write_bytes(copy.read_bytes()+b"x")
        report,summary=app.build_review_report(rows)
        self.assertEqual(summary["hash_errors"],1)
        self.assertEqual(summary["duplicate_files"],0)
        self.assertTrue(any(r["duplicate_scan_error"] for r in report))
        self.assertEqual({r["needs_review"] for r in report},{"YES"})

    def test_review_report_flags_stale_single_source_and_recovers_after_rescan(self):
        good=self.d/"single-store.png"
        good.write_bytes(b"\x89PNG\r\n\x1a\n"+struct.pack(">I",13)+
                         b"IHDR"+struct.pack(">II",1366,768)+b"\x08\x02\x00\x00\x00")
        snapshot=app.inspect_image(good)
        initial,initial_summary=app.build_review_report([snapshot])
        self.assertEqual(initial[0]["source_check"],"SOURCE_MATCH")
        self.assertEqual(initial[0]["needs_review"],"NO")
        good.write_bytes(good.read_bytes()+b"x")
        stale,summary=app.build_review_report([snapshot])
        self.assertEqual(stale[0]["msix_check"],"BASIC_CANDIDATE")
        self.assertEqual(stale[0]["source_check"],"SOURCE_CHANGED")
        self.assertEqual(stale[0]["needs_review"],"YES")
        self.assertEqual(summary["stale_sources"],1)
        self.assertIn("rescan",stale[0]["source_action"].lower())
        refreshed,summary=app.build_review_report([app.inspect_image(good)])
        self.assertEqual(refreshed[0]["source_check"],"SOURCE_MATCH")
        self.assertEqual(summary["stale_sources"],0)

    def test_review_report_flags_same_size_source_rewrite(self):
        snapshot=app.inspect_image(self.png)
        original=self.png.read_bytes()
        self.png.write_bytes(original[:-1]+bytes([original[-1]^1]))
        # Force a distinguishable mtime even on coarse-timestamp filesystems.
        changed_ns=snapshot["modified_ns"]+5_000_000_000
        os.utime(self.png,ns=(changed_ns,changed_ns))
        report,summary=app.build_review_report([snapshot])
        self.assertEqual(report[0]["source_check"],"SOURCE_CHANGED")
        self.assertIn("modification time",report[0]["source_action"])
        self.assertEqual(report[0]["needs_review"],"YES")
        self.assertEqual(summary["stale_sources"],1)
        self.assertEqual(self.png.read_bytes(),original[:-1]+bytes([original[-1]^1]))

    def test_review_report_legacy_snapshot_without_mtime_is_supported(self):
        snapshot=app.inspect_image(self.png)
        snapshot.pop("modified_ns")
        report,summary=app.build_review_report([snapshot])
        self.assertEqual(report[0]["source_check"],"SOURCE_MATCH")
        self.assertEqual(summary["stale_sources"],0)

    def test_review_report_flags_missing_source_even_without_duplicates(self):
        row=app.inspect_image(self.png)
        self.png.unlink()
        report,summary=app.build_review_report([row])
        self.assertEqual(report[0]["source_check"],"SOURCE_UNAVAILABLE")
        self.assertEqual(report[0]["needs_review"],"YES")
        self.assertEqual(summary["stale_sources"],1)

    def test_review_csv_exposes_stale_source_without_touching_images(self):
        row=app.inspect_image(self.png)
        self.png.write_bytes(self.png.read_bytes()+b"extra")
        before=self.png.read_bytes()
        summary=app.export_review_csv(self.d/"stale.csv",[row])
        with (self.d/"stale.csv").open(encoding="utf-8",newline="") as f:
            csv_rows=list(csv.DictReader(f))
        self.assertEqual(csv_rows[0]["source_check"],"SOURCE_CHANGED")
        self.assertEqual(csv_rows[0]["needs_review"],"YES")
        self.assertEqual(summary["stale_sources"],1)
        self.assertEqual(self.png.read_bytes(),before)

    def test_review_report_overlimit_and_empty(self):
        with self.assertRaises(ValueError):app.build_review_report([])
        with self.assertRaises(ValueError):app.export_review_csv(self.d/"empty.csv",[])
        rows=[dict(self.msix_row(),bytes=1000+i) for i in range(11)]
        report,summary=app.build_review_report(rows)
        self.assertTrue(summary["over_limit"])
        self.assertEqual(summary["attention"],11)
        self.assertEqual({r["batch_check"] for r in report},{"REVIEW_BATCH_LIMIT"})

    def test_bilingual(self):
        self.assertEqual(set(app.LABELS["ja"]),set(app.LABELS["en"]))
        self.assertTrue(callable(app.main))
if __name__=="__main__":unittest.main()
