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
    def test_bilingual(self):
        self.assertEqual(set(app.LABELS["ja"]),set(app.LABELS["en"]))
        self.assertTrue(callable(app.main))
if __name__=="__main__":unittest.main()
