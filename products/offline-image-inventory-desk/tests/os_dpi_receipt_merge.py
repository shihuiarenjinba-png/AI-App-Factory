"""Combine independently captured *real Windows OS DPI* EXE receipts.

Run on two extracted, SHA-bound evidence bundles captured at 125% (120 DPI)
and 150% (144 DPI). One Windows session cannot prove both display scales.
This is a review-only integrity check, NOT a substitute for authenticated
artifact provenance, local human QA, or buyer validation.
"""
import argparse
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import tempfile

_SHA40 = re.compile(r"[0-9a-f]{40}\Z")
_SHA64 = re.compile(r"[0-9a-f]{64}\Z")
_SESSION = re.compile(r"[0-9a-f]{32}\Z")
_SHOTS = ("01_exe_initial_en", "01b_exe_demo_en", "02_exe_baseline",
          "03_exe_comparison", "04_exe_japanese", "05_exe_restarted",
          "06_exe_read_error", "07_exe_read_denied")


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _load(path):
    path = Path(path)
    _require(not path.is_symlink(), "EVIDENCE_SYMLINK_REJECTED")
    _require(path.is_file() and 0 < path.stat().st_size <= 262144,
             "EVIDENCE_MISSING_OR_OVERSIZED")
    raw = path.read_bytes()
    return json.loads(raw.decode("utf-8-sig")), hashlib.sha256(raw).hexdigest()


def _one(gate_path, target):
    gate_path = Path(gate_path)
    _require(not gate_path.parent.is_symlink(), "EVIDENCE_SYMLINK_REJECTED")
    gate, gate_sha = _load(gate_path)
    _require(type(gate) is dict and gate.get("evidence_version") == 2,
             "OS_DPI_EVIDENCE_VERSION_MISMATCH")
    _require(_SESSION.fullmatch(str(gate.get("session_id", ""))) is not None,
             "OS_DPI_SESSION_MISSING")
    _require(_SHA40.fullmatch(str(gate.get("source_sha", ""))) is not None
             and _SHA64.fullmatch(str(gate.get("exe_sha256", ""))) is not None,
             "OS_DPI_SOURCE_OR_EXE_SHA_INVALID")
    _require(gate.get("classification") == "CLOUD_WINDOWS_OS_DPI_EVIDENCE_NOT_LOCAL_NOT_HUMAN"
             and gate.get("human_buyers_observed") == 0
             and gate.get("market_score") == 64
             and gate.get("why_pay_verified") is False
             and gate.get("market_fit") == "MARKET_FIT_HOLD"
             and gate.get("not_local_gui_pass") is True
             and gate.get("not_msix") is True
             and gate.get("os_dpi_125_150_both_proven") is False,
             "OS_DPI_REVIEW_ONLY_GATE_INVALID")
    when = datetime.fromisoformat(gate.get("observed_at_utc", ""))
    _require(when.tzinfo is not None and when.utcoffset().total_seconds() == 0,
             "OS_DPI_CAPTURE_TIME_INVALID")
    obs = gate.get("observation")
    expected = {125: 120, 150: 144}[target]
    _require(type(obs) is dict and obs.get("not_tk_scaling") is True
             and obs.get("per_monitor_v2_aware") is True
             and type(obs.get("system_dpi")) is int
             and type(obs.get("monitor_dpi_x")) is int
             and type(obs.get("monitor_dpi_y")) is int
             and (obs["system_dpi"], obs["monitor_dpi_x"], obs["monitor_dpi_y"])
             == (expected, expected, expected),
             "OS_DPI_REAL_MEASUREMENT_MISMATCH")
    targets = gate.get("targets")
    _require(type(targets) is dict and set(targets) == {"125", "150"},
             "OS_DPI_TARGETS_INVALID")
    record = targets[str(target)]
    other = targets[str(150 if target == 125 else 125)]
    _require(record.get("target_percent") == target
             and record.get("actual_os_dpi_proven") is True
             and record.get("packaged_gui_e2e") is True
             and record.get("status") == "CLOUD_REAL_OS_DPI_GUI_E2E_PASS_NOT_LOCAL_NOT_HUMAN"
             and other.get("packaged_gui_e2e") is False,
             "OS_DPI_SINGLE_SESSION_GUI_GATE_INVALID")
    replay_dir = gate_path.parent / ("real-os-dpi-%d" % target)
    _require(not replay_dir.is_symlink(), "EVIDENCE_SYMLINK_REJECTED")
    replay_path = replay_dir / "packaged-exe-e2e-receipt.json"
    replay, replay_sha = _load(replay_path)
    _require(record.get("replay_receipt_sha256") == replay_sha,
             "OS_DPI_REPLAY_RECEIPT_HASH_MISMATCH")
    _require(replay.get("classification") == "CLOUD_WINDOWS_PACKAGED_EXE_E2E"
             and replay.get("source_sha") == gate["source_sha"]
             and replay.get("exe_sha256") == gate["exe_sha256"]
             and replay.get("not_source_tk_smoke") is True
             and replay.get("not_local_gui_pass") is True
             and replay.get("source_images_untouched") is True
             and replay.get("read_denied_fail_closed") is True
             and _SHA64.fullmatch(str(replay.get("client_html_sha256", ""))) is not None
             and replay.get("fixture_sha256_before") == replay.get("fixture_sha256_after")
             and replay.get("market_fit") == "MARKET_FIT_HOLD"
             and replay.get("market_score") == 64
             and replay.get("why_pay_verified") is False,
             "OS_DPI_PACKAGED_EXE_REPLAY_INVALID")
    _require(replay.get("display_pixels") == [1024, 768],
             "OS_DPI_DISPLAY_1024x768_NOT_PROVEN")
    work = replay.get("actual_windows_work_area")
    _require(type(work) is list and len(work) == 4
             and all(type(v) is int for v in work)
             and work[0] >= 0 and work[1] >= 0
             and 850 <= work[2] - work[0] <= 1024
             and 600 <= work[3] - work[1] <= 768,
             "OS_DPI_WORK_AREA_INVALID")
    shots = replay.get("screenshots")
    _require(type(shots) is dict and all(key in shots for key in _SHOTS),
             "OS_DPI_GUI_SCREENSHOTS_MISSING")
    for key in _SHOTS:
        data = shots[key]
        _require(type(data) is dict and _SHA64.fullmatch(str(data.get("sha256", ""))) is not None,
                 "OS_DPI_SCREENSHOT_SHA_INVALID")
        shot = replay_dir / (key + ".png")
        _require(not shot.is_symlink() and shot.is_file() and shot.stat().st_size <= 20000000,
                 "OS_DPI_SCREENSHOT_MISSING_OR_UNSAFE")
        raw = shot.read_bytes()
        _require(hashlib.sha256(raw).hexdigest() == data["sha256"]
                 and raw[:16] == b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
                 and len(raw) >= 24,
                 "OS_DPI_SCREENSHOT_HASH_OR_FORMAT_MISMATCH")
        width, height = struct.unpack(">II", raw[16:24])
        _require(width == data.get("width") and height == data.get("height")
                 and 850 <= width <= 1024 and 600 <= height <= 768,
                 "OS_DPI_SCREENSHOT_CLIPPED")
    return {"target_percent": target, "session_id": gate["session_id"],
            "source_sha": gate["source_sha"], "exe_sha256": gate["exe_sha256"],
            "os_dpi": expected, "observed_at_utc": gate["observed_at_utc"],
            "gate_receipt_sha256": gate_sha, "packaged_replay_sha256": replay_sha,
            "screenshots_verified": len(_SHOTS)}


def merge_receipts(dpi125, dpi150):
    a, b = _one(dpi125, 125), _one(dpi150, 150)
    _require(a["session_id"] != b["session_id"], "OS_DPI_SESSIONS_NOT_INDEPENDENT")
    _require(a["source_sha"] == b["source_sha"]
             and a["exe_sha256"] == b["exe_sha256"],
             "OS_DPI_EXACT_EXE_OR_SOURCE_MISMATCH")
    return {"classification": "TWO_WINDOWS_OS_DPI_SESSIONS_REVIEW_ONLY_NOT_HUMAN",
            "source_sha": a["source_sha"], "exe_sha256": a["exe_sha256"],
            "os_dpi_125_150_both_proven": True,
            "sessions": {"125": a, "150": b},
            "human_buyers_observed": 0, "why_pay_verified": False,
            "market_score": 64, "market_fit": "MARKET_FIT_HOLD",
            "not_local_human_qa": True, "not_msix": True,
            "artifact_provenance_requires_independent_review": True}


def write_atomic(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=".dpi-receipt-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dpi125", type=Path, required=True,
                        help="os-dpi-gate.json from an actual 125% Windows OS session")
    parser.add_argument("--dpi150", type=Path, required=True,
                        help="os-dpi-gate.json from an actual 150% Windows OS session")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = merge_receipts(args.dpi125, args.dpi150)
    write_atomic(args.out, result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
