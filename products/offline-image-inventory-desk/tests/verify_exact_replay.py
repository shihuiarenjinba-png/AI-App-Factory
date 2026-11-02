"""Fail-closed evidence gate for a pinned, previously uploaded Windows EXE artifact.

This checks *machine* evidence only. It never upgrades MARKET_FIT or claims
human buyer observations, certification, local GUI QA, or an installed MSIX.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path


class EvidenceError(ValueError):
    pass


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _load(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def _require(condition, message):
    if not condition:
        raise EvidenceError(message)


def verify(exe, exe_receipt, evidence_dir, source_sha, artifact_id, run_id):
    exe = Path(exe)
    evidence_dir = Path(evidence_dir)
    source = _load(exe_receipt)
    packaged = _load(evidence_dir / "packaged-exe-e2e-receipt.json")
    digest = _sha(exe)
    _require(len(source_sha) == 40 and all(c in "0123456789abcdef" for c in source_sha),
             "INVALID_SOURCE_SHA")
    _require(source.get("source_sha") == source_sha, "SOURCE_RECEIPT_MISMATCH")
    _require(source.get("sha256") == digest, "EXE_SHA_MISMATCH")
    _require(source.get("bytes") == exe.stat().st_size, "EXE_SIZE_MISMATCH")
    _require(source.get("stage") == "REVIEW_ONLY_UNSIGNED_EXE", "NOT_UNSIGNED_REVIEW_EXE")
    _require(source.get("registration_type") == "MSIX_OR_PWA_APP", "ROUTING_MISMATCH")
    _require(source.get("identity_status") == "NOT_BOUND", "UNEXPECTED_IDENTITY")
    _require(source.get("market_fit") == "MARKET_FIT_HOLD", "INVALID_MARKET_GATE")
    _require(packaged.get("classification") == "CLOUD_WINDOWS_PACKAGED_EXE_E2E",
             "NOT_PACKAGED_EXE_QA")
    _require(packaged.get("not_local_gui_pass") is True
             and packaged.get("not_source_tk_smoke") is True, "FALSE_QA_CLASSIFICATION")
    _require(packaged.get("source_sha") == source_sha
             and packaged.get("exe_sha256") == digest
             and packaged.get("exe_bytes") == exe.stat().st_size, "REPLAY_PROVENANCE_MISMATCH")
    _require(packaged.get("market_fit") == "MARKET_FIT_HOLD"
             and packaged.get("market_score") == 64
             and packaged.get("why_pay_verified") is False, "FABRICATED_MARKET_PASS")
    _require(packaged.get("source_images_untouched") is True
             and packaged.get("fixture_sha256_before") == packaged.get("fixture_sha256_after"),
             "SOURCE_IMAGES_MODIFIED")
    _require(packaged.get("read_denied_fail_closed") is True, "READ_DENIAL_UNVERIFIED")
    before = packaged["fixture_sha256_before"]
    _require(set(before) == {"baseline", "delivery"}
             and all(isinstance(v, dict) and len(v) >= 3
                     and all(len(h) == 64 for h in v.values()) for v in before.values()),
             "INVALID_SOURCE_HASH_FIXTURE")
    expected = {"ADDED": 1, "REMOVED": 1, "MODIFIED": 1, "UNCHANGED": 1}
    changes = _load(evidence_dir / "packaged-changes.json")
    _require(changes.get("summary") == expected, "FOUR_CHANGE_MISMATCH")
    with (evidence_dir / "packaged-changes.csv").open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    _require(len(rows) == 4, "CSV_ROW_COUNT_MISMATCH")
    report = (evidence_dir / "packaged-summary-ja.txt").read_text(encoding="utf-8")
    _require(all(x in report for x in ("日時の限界", "お客様への確認ポイント", "次の操作:", "名前変更")),
             "CUSTOMER_TXT_INCOMPLETE")
    client_html_path = evidence_dir / "packaged-client-ja.html"
    client_html = client_html_path.read_text(encoding="utf-8")
    _require("納品画像の確認レポート" in client_html
             and "data:image/png;base64," in client_html
             and "default-src 'none'" in client_html
             and "<script" not in client_html
             and 'src="http' not in client_html, "CUSTOMER_HTML_INCOMPLETE")
    _require(packaged.get("client_html_sha256") == _sha(client_html_path),
             "CUSTOMER_HTML_SHA_MISMATCH")
    shots = packaged.get("screenshots", {})
    for key in ("01_exe_initial_en", "04_exe_japanese", "05_exe_restarted",
                "06_exe_read_error", "07_exe_read_denied"):
        record = shots.get(key, {})
        path = evidence_dir / (key + ".png")
        _require(path.is_file() and record.get("sha256") == _sha(path),
                 "SCREENSHOT_MISMATCH_" + key)
        _require(record.get("width", 0) >= 1024 and record.get("height", 0) >= 768,
                 "SCREENSHOT_BELOW_1024x768_" + key)
    checks = packaged.get("checks", [])
    _require(any("real Windows exclusive-file read denial fail-closed" in x for x in checks),
             "READ_DENIAL_LOG_MISSING")
    _require(any("packaged CSV/JSON/TXT contents validated" in x for x in checks),
             "EXPORT_LOG_MISSING")
    _require(any("packaged HTML local customer previews validated" in x for x in checks),
             "CUSTOMER_HTML_LOG_MISSING")
    _require(any("packaged EXE process started" in x for x in checks),
             "PACKAGED_LAUNCH_LOG_MISSING")
    _require(isinstance(artifact_id, int) and artifact_id > 0
             and isinstance(run_id, int) and run_id > 0, "ARTIFACT_ID_MISSING")
    return {
        "classification": "PINNED_ARTIFACT_CLOUD_WINDOWS_BUYER_TASK_QA",
        "artifact_id": artifact_id, "artifact_run_id": run_id,
        "source_sha": source_sha, "exe_sha256": digest,
        "checks": ["pinned_exe_hash", "four_changes", "ja_en_1024x768",
                   "csv_json_txt_html", "restart", "malformed_read_fail_closed",
                   "real_read_denied_fail_closed", "source_images_sha_unchanged"],
        "human_buyers_observed": 0, "why_pay_verified": False,
        "market_score": 64, "market_fit": "MARKET_FIT_HOLD",
        "not_local_gui_pass": True, "not_msix": True, "not_store_certified": True,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--exe", required=True, type=Path)
    parser.add_argument("--exe-receipt", required=True, type=Path)
    parser.add_argument("--evidence", required=True, type=Path)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--artifact-id", type=int, required=True)
    parser.add_argument("--run-id", type=int, required=True)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    receipt = verify(args.exe, args.exe_receipt, args.evidence,
                     args.source_sha, args.artifact_id, args.run_id)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(receipt, indent=2, ensure_ascii=False) + "\n",
                        encoding="utf-8")
    print(json.dumps(receipt, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
