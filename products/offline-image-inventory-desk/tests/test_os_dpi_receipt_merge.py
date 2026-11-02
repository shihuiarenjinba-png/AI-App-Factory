"""Synthetic contract fixtures only; NOT actual OS-DPI evidence."""
import hashlib
import json
from pathlib import Path
import struct
import tempfile
import unittest
import zlib

from os_dpi_receipt_merge import merge_receipts, _SHOTS

SOURCE = "a" * 40
EXE = "b" * 64


def _png():
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)
    raw = b"".join(b"\x00" + b"\x10\x20\x30" * 900 for _ in range(650))
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 900, 650, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")


def fixture(root, target, session):
    base = root / str(target)
    base.mkdir()
    sub = base / ("real-os-dpi-%s" % target)
    sub.mkdir()
    shots = {}
    png = _png()
    for key in _SHOTS:
        (sub / (key + ".png")).write_bytes(png)
        shots[key] = {"sha256": hashlib.sha256(png).hexdigest(), "width": 900, "height": 650}
    replay = {
        "classification": "CLOUD_WINDOWS_PACKAGED_EXE_E2E",
        "source_sha": SOURCE, "exe_sha256": EXE,
        "not_source_tk_smoke": True, "not_local_gui_pass": True,
        "source_images_untouched": True, "read_denied_fail_closed": True,
        "client_html_sha256": "c" * 64,
        "fixture_sha256_before": {"baseline": {"a.png": "d" * 64}},
        "fixture_sha256_after": {"baseline": {"a.png": "d" * 64}},
        "market_fit": "MARKET_FIT_HOLD", "market_score": 64,
        "why_pay_verified": False, "display_pixels": [1024, 768],
        "actual_windows_work_area": [0, 0, 1024, 720], "screenshots": shots,
    }
    raw = json.dumps(replay).encode()
    (sub / "packaged-exe-e2e-receipt.json").write_bytes(raw)
    other = 150 if target == 125 else 125
    gate = {
        "evidence_version": 2, "session_id": session,
        "observed_at_utc": "2026-11-02T12:00:00+00:00",
        "classification": "CLOUD_WINDOWS_OS_DPI_EVIDENCE_NOT_LOCAL_NOT_HUMAN",
        "source_sha": SOURCE, "exe_sha256": EXE,
        "human_buyers_observed": 0, "market_score": 64,
        "why_pay_verified": False, "market_fit": "MARKET_FIT_HOLD",
        "not_local_gui_pass": True, "not_msix": True,
        "os_dpi_125_150_both_proven": False,
        "observation": {"not_tk_scaling": True, "per_monitor_v2_aware": True,
                        "system_dpi": {125: 120, 150: 144}[target],
                        "monitor_dpi_x": {125: 120, 150: 144}[target],
                        "monitor_dpi_y": {125: 120, 150: 144}[target]},
        "targets": {
            str(target): {"target_percent": target, "actual_os_dpi_proven": True,
                          "packaged_gui_e2e": True,
                          "status": "CLOUD_REAL_OS_DPI_GUI_E2E_PASS_NOT_LOCAL_NOT_HUMAN",
                          "replay_receipt_sha256": hashlib.sha256(raw).hexdigest()},
            str(other): {"target_percent": other, "actual_os_dpi_proven": False,
                         "packaged_gui_e2e": False, "status": "OS_DPI_NOT_PROVEN_HOLD"},
        },
    }
    path = base / "os-dpi-gate.json"
    path.write_text(json.dumps(gate), encoding="utf-8")
    return path


class CrossSessionMergeContract(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.a = fixture(self.root, 125, "1" * 32)
        self.b = fixture(self.root, 150, "2" * 32)

    def change(self, path, edit):
        data = json.loads(path.read_text())
        edit(data)
        path.write_text(json.dumps(data), encoding="utf-8")

    def test_two_distinct_real_dpi_contracts(self):
        result = merge_receipts(self.a, self.b)
        self.assertTrue(result["os_dpi_125_150_both_proven"])
        self.assertEqual(result["market_fit"], "MARKET_FIT_HOLD")
        self.assertEqual(result["human_buyers_observed"], 0)
        self.assertTrue(result["artifact_provenance_requires_independent_review"])

    def test_one_session_cannot_claim_both(self):
        self.change(self.b, lambda x: x.update(session_id="1" * 32))
        with self.assertRaisesRegex(ValueError, "NOT_INDEPENDENT"):
            merge_receipts(self.a, self.b)

    def test_wrong_os_dpi_rejected(self):
        self.change(self.a, lambda x: x["observation"].update(system_dpi=96))
        with self.assertRaisesRegex(ValueError, "MEASUREMENT_MISMATCH"):
            merge_receipts(self.a, self.b)

    def test_tk_simulation_cannot_pass(self):
        self.change(self.a, lambda x: x["observation"].update(not_tk_scaling=False))
        with self.assertRaisesRegex(ValueError, "MEASUREMENT_MISMATCH"):
            merge_receipts(self.a, self.b)

    def test_different_exe_rejected(self):
        self.change(self.b, lambda x: x.update(exe_sha256="e" * 64))
        with self.assertRaisesRegex(ValueError, "REPLAY_INVALID"):
            merge_receipts(self.a, self.b)

    def test_replay_tamper_rejected(self):
        p = self.a.parent / "real-os-dpi-125" / "packaged-exe-e2e-receipt.json"
        p.write_text(p.read_text() + " ")
        with self.assertRaisesRegex(ValueError, "HASH_MISMATCH"):
            merge_receipts(self.a, self.b)

    def test_screenshot_tamper_rejected(self):
        p = self.a.parent / "real-os-dpi-125" / "01_exe_initial_en.png"
        p.write_bytes(p.read_bytes() + b"altered")
        with self.assertRaisesRegex(ValueError, "HASH_OR_FORMAT_MISMATCH"):
            merge_receipts(self.a, self.b)

    def test_missing_screenshot_rejected(self):
        p = self.a.parent / "real-os-dpi-125" / "07_exe_read_denied.png"
        p.unlink()
        with self.assertRaisesRegex(ValueError, "SCREENSHOT_MISSING_OR_UNSAFE"):
            merge_receipts(self.a, self.b)

    def test_false_market_promotion_rejected(self):
        self.change(self.a, lambda x: x.update(market_fit="SALE_READY"))
        with self.assertRaisesRegex(ValueError, "REVIEW_ONLY_GATE_INVALID"):
            merge_receipts(self.a, self.b)

    def test_single_100_percent_runner_rejected(self):
        self.change(self.b, lambda x: x["targets"]["150"].update(packaged_gui_e2e=False))
        with self.assertRaisesRegex(ValueError, "GUI_GATE_INVALID"):
            merge_receipts(self.a, self.b)


if __name__ == "__main__":
    unittest.main()
