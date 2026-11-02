"""Contract tests: synthetic evidence never implies five actual buyer responses."""
import csv
import importlib.util
from pathlib import Path
import tempfile
import unittest

MODULE = Path(__file__).resolve().parents[1] / "buyer_validation_evidence.py"
spec = importlib.util.spec_from_file_location("buyer_validation_evidence", MODULE)
kit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(kit)


class BuyerEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.exe = self.root / "sample.exe"
        self.exe.write_bytes(b"MZ" + b"test-only-EXE-placeholder")
        self.out = self.root / "kit"
        self.source = "a" * 40

    def make(self):
        return kit.prepare(self.out, self.exe, self.source)

    def test_synthetic_four_states_and_no_human_answers(self):
        manifest = self.make()
        self.assertEqual(manifest["market_score"], 64)
        self.assertFalse(manifest["why_pay_verified"])
        self.assertEqual(manifest["human_response_count"], 0)
        self.assertEqual(set(kit.verify(self.out)["fixture_changes"].values()),
                         {"ADDED", "REMOVED", "MODIFIED", "UNCHANGED"})
        self.assertEqual((self.out / "baseline" / "same.png").read_bytes()[:8],
                         bytes.fromhex("89504e470d0a1a0a"))
        with (self.out / "participant-responses.csv").open(newline="", encoding="utf-8") as f:
            self.assertEqual(list(csv.DictReader(f)), [])
        self.assertEqual((self.out / "events.jsonl").read_text(), "")
        self.assertEqual((self.out / "read-error" / "invalid.png").read_bytes(),
                         b"NOT_A_PNG_TEST_FIXTURE")

    def test_tamper_detected_and_never_overwrite(self):
        self.make()
        with self.assertRaises(ValueError):
            self.make()
        (self.out / "delivery" / "added.png").write_bytes(b"corrupt")
        with self.assertRaisesRegex(AssertionError, "SOURCE_IMAGES_MODIFIED"):
            kit.verify(self.out)

    def test_read_error_fixture_is_separate_and_protected(self):
        self.make()
        self.assertFalse((self.out / "delivery" / "invalid.png").exists())
        (self.out / "read-error" / "invalid.png").write_bytes(b"changed")
        with self.assertRaisesRegex(AssertionError, "SOURCE_IMAGES_MODIFIED"):
            kit.verify(self.out)

    def test_exe_sha_tamper_detected(self):
        self.make()
        (self.out / "offline-image-inventory-desk.exe").write_bytes(b"MZmodified")
        with self.assertRaisesRegex(AssertionError, "PACKAGED_EXE_SHA_MISMATCH"):
            kit.verify(self.out)

    def test_manual_timing_and_error_log_not_auto_filled(self):
        self.make()
        with self.assertRaisesRegex(ValueError, "No matching phase start"):
            kit.record_event(self.out, "P01", "product", "stop", 0, 0)
        kit.record_event(self.out, "P01", "product", "start")
        kit.record_event(self.out, "P01", "product", "error", note="observed")
        event = kit.record_event(self.out, "P01", "product", "stop", 9, 1)
        self.assertEqual(event["clicks"], 9)
        self.assertEqual(event["errors"], 1)
        self.assertGreaterEqual(event["elapsed_sec"], 0)
        with self.assertRaisesRegex(ValueError, "No matching phase start"):
            kit.record_event(self.out, "P01", "product", "stop", 9, 1)
        self.assertEqual(kit.verify(self.out)["response_rows"], 0)

    def test_uncoached_journey_contract_has_no_fake_answers(self):
        manifest = self.make()
        self.assertEqual(manifest["journey_protocol"], "UNCOACHED_DELIVERY_JOURNEY_V1")
        self.assertEqual(tuple(manifest["required_phases"]), kit.PHASES)
        self.assertIn("first_30sec", kit.PHASES)
        self.assertIn("recipient_review", kit.PHASES)
        with (self.out / "participant-responses.csv").open(newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            self.assertIn("recipient_can_identify_changes", reader.fieldnames)
            self.assertEqual(list(reader), [])
        self.assertEqual(kit.verify(self.out)["response_rows"], 0)

    def test_extra_non_png_or_nested_fixture_refused(self):
        self.make()
        extra = self.out / "delivery" / "alternate.jpg"
        extra.write_bytes(b"untracked alternate image")
        with self.assertRaisesRegex(AssertionError, "SOURCE_IMAGES_MODIFIED"):
            kit.verify(self.out)
        extra.unlink()
        nested = self.out / "baseline" / "other-samples"
        nested.mkdir()
        with self.assertRaisesRegex(AssertionError, "SOURCE_IMAGES_MODIFIED"):
            kit.verify(self.out)
        nested.rmdir()
        self.assertTrue(kit.verify(self.out)["source_unchanged"])

    def test_fixture_symlink_cannot_reuse_same_bytes(self):
        self.make()
        target = self.out / "baseline" / "same.png"
        original = target.read_bytes()
        identical = self.root / "identical-copy.png"
        identical.write_bytes(original)
        target.unlink()
        try:
            target.symlink_to(identical)
        except (OSError, NotImplementedError):
            self.skipTest("Symlink creation not permitted on this runner")
        with self.assertRaisesRegex(AssertionError, "SOURCE_IMAGES_MODIFIED"):
            kit.verify(self.out)
        target.unlink()
        target.write_bytes(original)
        self.assertTrue(kit.verify(self.out)["source_unchanged"])

    def test_rejects_unverified_input(self):
        with self.assertRaisesRegex(ValueError, "Exact 40"):
            kit.prepare(self.out, self.exe, "not-a-sha")
        self.assertFalse(self.out.exists())


if __name__ == "__main__":
    unittest.main()
