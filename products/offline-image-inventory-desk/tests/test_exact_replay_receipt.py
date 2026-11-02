"""Synthetic negative fixtures for the pinned EXE QA evidence gate."""
import csv
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from verify_exact_replay import verify, EvidenceError

SOURCE = "70ed475c1621a9955dafe5cc39562915c6cfd424"
EXPECTED = {"ADDED": 1, "REMOVED": 1, "MODIFIED": 1, "UNCHANGED": 1}


class ExactReplayEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.exe = self.root / "review.exe"
        self.exe.write_bytes(b"MZ synthetic executable fixture")
        self.digest = hashlib.sha256(self.exe.read_bytes()).hexdigest()
        self.exe_receipt = self.root / "exe-receipt.json"
        self.evidence = self.root / "evidence"
        self.evidence.mkdir()
        self.source = {
            "stage": "REVIEW_ONLY_UNSIGNED_EXE", "source_sha": SOURCE,
            "sha256": self.digest, "bytes": self.exe.stat().st_size,
            "market_fit": "MARKET_FIT_HOLD", "registration_type": "MSIX_OR_PWA_APP",
            "identity_status": "NOT_BOUND"
        }
        hashes = {"same.png": "a" * 64, "modified.png": "b" * 64,
                  "removed.png": "c" * 64}
        self.packaged = {
            "classification": "CLOUD_WINDOWS_PACKAGED_EXE_E2E",
            "not_source_tk_smoke": True, "not_local_gui_pass": True,
            "source_sha": SOURCE, "exe_sha256": self.digest,
            "exe_bytes": self.exe.stat().st_size,
            "source_images_untouched": True, "read_denied_fail_closed": True,
            "fixture_sha256_before": {"baseline": hashes, "delivery": hashes},
            "fixture_sha256_after": {"baseline": hashes, "delivery": hashes},
            "screenshots": {}, "market_fit": "MARKET_FIT_HOLD",
            "market_score": 64, "why_pay_verified": False,
            "checks": ["packaged EXE process started PID=42",
                       "packaged CSV/JSON/TXT contents validated",
                       "packaged HTML local customer previews validated",
                       "real Windows exclusive-file read denial fail-closed; stale export blocked"]
        }
        for name in ("01_exe_initial_en", "04_exe_japanese", "05_exe_restarted",
                     "06_exe_read_error", "07_exe_read_denied"):
            png = self.evidence / (name + ".png")
            png.write_bytes(("synthetic " + name).encode())
            self.packaged["screenshots"][name] = {
                "sha256": hashlib.sha256(png.read_bytes()).hexdigest(),
                "width": 1024, "height": 768
            }
        (self.evidence / "packaged-changes.json").write_text(
            json.dumps({"summary": EXPECTED}), encoding="utf-8")
        with (self.evidence / "packaged-changes.csv").open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["change"])
            for key in EXPECTED:
                writer.writerow([key])
        (self.evidence / "packaged-summary-ja.txt").write_text(
            "日時の限界 お客様への確認ポイント 次の操作: 名前変更", encoding="utf-8")
        html_path = self.evidence / "packaged-client-ja.html"
        html_path.write_text(
            '<meta content="default-src \'none\'"><h1>納品画像の確認レポート</h1>'
            '<img src="data:image/png;base64,AAAA">', encoding="utf-8")
        self.packaged["client_html_sha256"] = hashlib.sha256(
            html_path.read_bytes()).hexdigest()
        self.save()

    def save(self):
        self.exe_receipt.write_text(json.dumps(self.source), encoding="utf-8")
        (self.evidence / "packaged-exe-e2e-receipt.json").write_text(
            json.dumps(self.packaged), encoding="utf-8")

    def check(self):
        self.save()
        return verify(self.exe, self.exe_receipt, self.evidence, SOURCE,
                      13101545092, 41349965924)

    def test_valid_synthetic_fixture_is_not_human_pass(self):
        receipt = self.check()
        self.assertEqual(receipt["human_buyers_observed"], 0)
        self.assertFalse(receipt["why_pay_verified"])
        self.assertTrue(receipt["not_local_gui_pass"])

    def test_exe_tamper_rejected(self):
        self.exe.write_bytes(b"MZ tampered")
        with self.assertRaisesRegex(EvidenceError, "EXE_SHA_MISMATCH"):
            self.check()

    def test_source_mismatch_rejected(self):
        self.source["source_sha"] = "0" * 40
        with self.assertRaisesRegex(EvidenceError, "SOURCE_RECEIPT_MISMATCH"):
            self.check()

    def test_read_denial_missing_rejected(self):
        self.packaged["read_denied_fail_closed"] = False
        with self.assertRaisesRegex(EvidenceError, "READ_DENIAL_UNVERIFIED"):
            self.check()

    def test_source_image_modified_rejected(self):
        self.packaged["fixture_sha256_after"]["delivery"] = {"same.png": "0" * 64}
        with self.assertRaisesRegex(EvidenceError, "SOURCE_IMAGES_MODIFIED"):
            self.check()

    def test_fake_market_pass_rejected(self):
        self.packaged["why_pay_verified"] = True
        with self.assertRaisesRegex(EvidenceError, "FABRICATED_MARKET_PASS"):
            self.check()

    def test_small_window_rejected(self):
        self.packaged["screenshots"]["04_exe_japanese"]["width"] = 900
        with self.assertRaisesRegex(EvidenceError, "SCREENSHOT_BELOW_1024x768"):
            self.check()

    def test_missing_output_rejected(self):
        (self.evidence / "packaged-changes.csv").unlink()
        with self.assertRaises(FileNotFoundError):
            self.check()

    def test_html_tamper_rejected(self):
        (self.evidence / "packaged-client-ja.html").write_text(
            "<script>evil()</script>", encoding="utf-8")
        with self.assertRaisesRegex(EvidenceError, "CUSTOMER_HTML_INCOMPLETE"):
            self.check()

    def test_missing_negative_screenshot_rejected(self):
        (self.evidence / "07_exe_read_denied.png").unlink()
        with self.assertRaisesRegex(EvidenceError, "SCREENSHOT_MISMATCH"):
            self.check()


if __name__ == "__main__":
    unittest.main()
