"""Audit must expose only manually observed metrics, never fake buyer success."""
import csv
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(ROOT))
import buyer_validation_evidence as kit
import buyer_validation_audit as auditor


class BuyerAuditTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.folder = Path(tmp.name)
        exe = self.folder / "fake.exe"
        exe.write_bytes(b"MZ" + b"test-only")
        self.out = self.folder / "kit"
        kit.prepare(self.out, exe, "b" * 40)

    def test_blank_kit_is_not_real_buyers(self):
        result = auditor.audit(self.out)
        self.assertEqual(result["status"], "NOT_RUN")
        self.assertEqual(result["response_rows"], 0)
        self.assertEqual(result["complete_observed_phase_sets"], 0)
        self.assertFalse(result["why_pay_verified"])
        self.assertEqual(result["market_score"], 64)

    def test_manual_timing_and_partial_session_never_promotes(self):
        kit.record_event(self.out, "P01", "product", "start")
        kit.record_event(self.out, "P01", "product", "error", note="dialog")
        kit.record_event(self.out, "P01", "product", "stop", 8, 1)
        result = auditor.audit(self.out)
        self.assertEqual(result["status"], "HUMAN_REVIEW_REQUIRED")
        self.assertEqual(result["sessions"]["P01"]["phases"]["product"]["clicks"], 8)
        self.assertFalse(result["sessions"]["P01"]["all_phases_complete"])
        self.assertFalse(result["why_pay_verified"])

    def test_duplicate_participant_rejected(self):
        with (self.out / "participant-responses.csv").open("a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            for _ in range(2):
                writer.writerow(["P01"] + [""] * (len(kit.FIELDS) - 1))
        with self.assertRaisesRegex(ValueError, "duplicate"):
            auditor.audit(self.out)

    def test_orphan_error_event_rejected(self):
        (self.out / "events.jsonl").write_text(
            '{"participant":"P01","phase":"product","action":"error","utc":"2026-11-02T00:00:00+00:00"}\n',
            encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "outside active"):
            auditor.audit(self.out)

    def test_tampered_elapsed_rejected(self):
        kit.record_event(self.out, "P01", "free", "start")
        kit.record_event(self.out, "P01", "free", "stop", 2, 0)
        import json
        p = self.out / "events.jsonl"
        events = [json.loads(line) for line in p.read_text().splitlines()]
        events[-1]["elapsed_sec"] = 90000
        p.write_text("\n".join(json.dumps(x) for x in events) + "\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Invalid observed metrics"):
            auditor.audit(self.out)


if __name__ == "__main__":
    unittest.main()
