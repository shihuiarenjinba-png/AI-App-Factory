"""Deterministic, synthetic buyer-test kit. Never manufactures human answers.

Usage:
  python buyer_validation_evidence.py prepare --out PATH --exe PATH --source-sha SHA
  python buyer_validation_evidence.py verify --out PATH
  python buyer_validation_evidence.py event --out PATH --participant P01 --phase product --action start
  python buyer_validation_evidence.py event --out PATH --participant P01 --phase product --action stop --clicks 12 --errors 0
All event recording is manual, outside CI. Keep identifiable participant data offline.
"""
import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import struct
import zlib

FIELDS = ("participant_id", "role", "existing_tool", "monthly_deliveries",
          "task_success_free", "task_success_product", "time_free_sec",
          "time_product_sec", "clicks_free", "clicks_product",
          "assisted_steps", "critical_errors", "client_accepts_txt",
          "source_unchanged", "willingness_to_pay_JPY", "reason_to_pay",
          "reason_not_to_pay", "interview_date", "consent",
          "first_30sec_goal_understood", "recipient_can_identify_changes",
          "recipient_can_explain_limits", "recipient_feedback")
EXPECTED = {"same.png": "UNCHANGED", "modified.png": "MODIFIED",
            "removed.png": "REMOVED", "added.png": "ADDED"}
PHASES = ("free", "first_30sec", "product", "delivery",
          "recipient_review", "restart", "read_error")


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def make_png(path, rgb):
    width, height = 24, 18

    def chunk(kind, payload):
        return (struct.pack(">I", len(payload)) + kind + payload
                + struct.pack(">I", zlib.crc32(kind + payload) & 0xffffffff))
    pixels = b"".join(b"\x00" + bytes(rgb) * width for _ in range(height))
    Path(path).write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(pixels)) + chunk(b"IEND", b""))


def image_hashes(root):
    return {p.relative_to(root).as_posix(): digest(p)
            for p in sorted(root.rglob("*.png"))}


def verify_fixture_inventory(folder, expected_names):
    """Reject extra files, nested folders and links before hashing buyer fixtures.

    Hashing only *.png would otherwise miss an added JPG or a directory
    containing alternate samples, making the five-person task non-identical.
    """
    if not folder.is_dir() or folder.is_symlink():
        raise AssertionError("SOURCE_IMAGES_MODIFIED: fixture folder missing or linked")
    entries = list(folder.iterdir())
    if (set(p.name for p in entries) != set(expected_names)
            or any(p.is_symlink() or not p.is_file() for p in entries)):
        raise AssertionError("SOURCE_IMAGES_MODIFIED: fixture inventory changed")


def prepare(out, exe, source_sha):
    out = Path(out).resolve()
    exe = Path(exe).resolve()
    if out.exists():
        raise ValueError("Refusing to overwrite a buyer evidence package")
    if not exe.is_file() or exe.suffix.lower() != ".exe":
        raise ValueError("A real packaged Windows EXE is required")
    if len(source_sha) != 40 or any(c not in "0123456789abcdef" for c in source_sha.lower()):
        raise ValueError("Exact 40-character source SHA required")
    out.mkdir(parents=True)
    base, revised = out / "baseline", out / "delivery"
    base.mkdir()
    revised.mkdir()
    for name, rgb in (("same.png", (5, 10, 15)),
                      ("modified.png", (20, 40, 60)),
                      ("removed.png", (80, 100, 120))):
        make_png(base / name, rgb)
        shutil.copyfile(base / name, revised / name)
    make_png(revised / "modified.png", (200, 10, 20))
    (revised / "removed.png").unlink()
    make_png(revised / "added.png", (10, 210, 30))
    # Separate failure fixture: intentionally invalid image, never inserted into
    # the valid four-state delivery. Comparing this folder must fail closed.
    error_folder = out / "read-error"
    error_folder.mkdir()
    for file in revised.glob("*.png"):
        shutil.copyfile(file, error_folder / file.name)
    (error_folder / "invalid.png").write_bytes(b"NOT_A_PNG_TEST_FIXTURE")
    shutil.copyfile(exe, out / "offline-image-inventory-desk.exe")
    with (out / "participant-responses.csv").open("w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow(FIELDS)  # no fake participant rows
    (out / "events.jsonl").write_text("", encoding="utf-8")
    manifest = {
        "classification": "SYNTHETIC_BUYER_TEST_KIT_NOT_REAL_BUYER_EVIDENCE",
        "source_sha": source_sha,
        "exe_sha256": digest(out / "offline-image-inventory-desk.exe"),
        "fixture_expected": EXPECTED,
        "journey_protocol": "UNCOACHED_DELIVERY_JOURNEY_V1",
        "required_phases": list(PHASES),
        "baseline_sha256": image_hashes(base),
        "delivery_sha256": image_hashes(revised),
        "read_error_sha256": image_hashes(error_folder),
        "human_response_count": 0,
        "why_pay_verified": False,
        "market_score": 64,
        "market_fit": "MARKET_FIT_HOLD",
        "not_local_gui_pass": True,
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    (out / "README.txt").write_text(
        "Offline Image Inventory Desk - independent buyer test (NOT RUN)\n"
        "Use 1024x768 Windows; run packaged EXE, not main.py. Test EN and JA.\n"
        "Unprompted task: You received a revised image folder. Produce a client-readable\n"
        "change record without altering original images. Compare free tool first.\n"
        "Compare the free/current tool first. Observe the first 30 seconds of\n"
        "uncoached product use; then record baseline, compare delivery and save\n"
        "client HTML with previews. Hand HTML to an uncoached recipient and\n"
        "record what they understood. Restart/reopen, then compare read-error/\n"
        "(invalid.png); stale results must not export. Optional TXT/CSV/JSON.\n"
        "Log free, first_30sec, product, delivery, recipient_review, restart,\n"
        "read_error phases in that order; record clicks/errors, real answers.\n"
        "Use event command to time phases. Log real responses in CSV only after test.\n"
        "Run verify after every session to check original image SHA-256.\n"
        "Never upload client images, identifiable responses or paid-test records to GitHub.\n"
        "Hosted Windows CI is NOT LOCAL_GUI_PASS or purchase evidence.\n",
        encoding="utf-8")
    verify(out)
    return manifest


def verify(out):
    out = Path(out).resolve()
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    if manifest["fixture_expected"] != EXPECTED:
        raise AssertionError("Unexpected fixture contract")
    if (manifest.get("journey_protocol") != "UNCOACHED_DELIVERY_JOURNEY_V1"
            or manifest.get("required_phases") != list(PHASES)):
        raise AssertionError("Buyer journey protocol mismatch")
    for name in ("baseline", "delivery", "read-error"):
        expected_names = set(manifest[name.replace("-", "_") + "_sha256"])
        if name == "read-error":
            expected_names.add("invalid.png")
        verify_fixture_inventory(out / name, expected_names)
    if image_hashes(out / "baseline") != manifest["baseline_sha256"]:
        raise AssertionError("SOURCE_IMAGES_MODIFIED: baseline")
    if image_hashes(out / "delivery") != manifest["delivery_sha256"]:
        raise AssertionError("SOURCE_IMAGES_MODIFIED: delivery")
    if image_hashes(out / "read-error") != manifest["read_error_sha256"]:
        raise AssertionError("SOURCE_IMAGES_MODIFIED: read-error fixture")
    if (out / "read-error" / "invalid.png").read_bytes() != b"NOT_A_PNG_TEST_FIXTURE":
        raise AssertionError("Read-error fixture no longer invalid")
    if digest(out / "offline-image-inventory-desk.exe") != manifest["exe_sha256"]:
        raise AssertionError("PACKAGED_EXE_SHA_MISMATCH")
    b, d = manifest["baseline_sha256"], manifest["delivery_sha256"]
    observed = {n: ("ADDED" if n not in b else "REMOVED" if n not in d else
                    "UNCHANGED" if b[n] == d[n] else "MODIFIED")
                for n in sorted(set(b) | set(d))}
    if observed != EXPECTED:
        raise AssertionError("Synthetic change fixture incorrect")
    with (out / "participant-responses.csv").open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if tuple(reader.fieldnames or ()) != FIELDS:
            raise AssertionError("Participant response schema mismatch")
        rows = list(reader)
    if manifest["human_response_count"] != 0 or manifest["why_pay_verified"] is not False:
        raise AssertionError("Kit must never claim buyer validation")
    return {"source_unchanged": True, "fixture_changes": observed,
            "response_rows": len(rows), "exe_sha256": manifest["exe_sha256"]}


def record_event(out, participant, phase, action, clicks=None, errors=None, note=""):
    out = Path(out).resolve()
    verify(out)
    if participant not in ("P01", "P02", "P03", "P04", "P05"):
        raise ValueError("Use anonymous participant ID P01-P05")
    if phase not in PHASES or action not in ("start", "stop", "error"):
        raise ValueError("Unknown phase/action")
    if action == "stop" and (clicks is None or errors is None):
        raise ValueError("Stop requires observed clicks and errors, never guessed")
    if clicks is not None and clicks < 0 or errors is not None and errors < 0:
        raise ValueError("Counts must be nonnegative")
    path = out / "events.jsonl"
    events = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    previous = [e for e in events if e["participant"] == participant and e["phase"] == phase]
    if action == "start" and previous and previous[-1]["action"] != "stop":
        raise ValueError("Previous phase not finished")
    if action == "stop":
        starts = [e for e in previous if e["action"] == "start"]
        stops = [e for e in previous if e["action"] == "stop"]
        if not starts or len(starts) <= len(stops):
            raise ValueError("No matching phase start")
    now = datetime.now(timezone.utc)
    entry = {"participant": participant, "phase": phase, "action": action,
             "utc": now.isoformat(), "clicks": clicks, "errors": errors, "note": note}
    if action == "stop":
        started = datetime.fromisoformat(starts[-1]["utc"])
        entry["elapsed_sec"] = round((now - started).total_seconds(), 2)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("prepare", "verify", "event"))
    parser.add_argument("--out", required=True)
    parser.add_argument("--exe")
    parser.add_argument("--source-sha")
    parser.add_argument("--participant")
    parser.add_argument("--phase")
    parser.add_argument("--action")
    parser.add_argument("--clicks", type=int)
    parser.add_argument("--errors", type=int)
    parser.add_argument("--note", default="")
    args = parser.parse_args()
    if args.command == "prepare":
        result = prepare(args.out, args.exe, args.source_sha)
    elif args.command == "verify":
        result = verify(args.out)
    else:
        result = record_event(args.out, args.participant, args.phase,
                              args.action, args.clicks, args.errors, args.note)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
