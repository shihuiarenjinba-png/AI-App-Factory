"""Native Windows EXE first-use smoke; no source files or Store state changed."""
import hashlib
import csv
import tempfile
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback

from pywinauto import Desktop, keyboard

exe = Path(sys.argv[1]).resolve()
out = Path(sys.argv[2]).resolve()
out.mkdir(parents=True, exist_ok=True)
source = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
assert source == os.environ["EXPECTED_SOURCE_SHA"], "Not an exact raw source checkout"
assert exe.is_file(), "Native EXE missing"
receipt = {
    "source_sha": source,
    "exe_sha256": hashlib.sha256(exe.read_bytes()).hexdigest(),
    "exe_name": exe.name,
    "steps": [],
    "result": "FAIL",
}
proc = None
try:
    proc = subprocess.Popen([str(exe)], cwd=str(exe.parent))
    window = Desktop(backend="uia").window(title_re=".*File Integrity Ledger.*")
    window.wait("visible", timeout=45)
    window.set_focus()
    time.sleep(1)
    assert proc.poll() is None, "EXE exited before first-use capture"
    rect = window.rectangle()
    assert rect.width() >= 850 and rect.height() >= 620, "Unexpected GUI geometry"
    receipt["window_rectangle"] = [rect.left, rect.top, rect.right, rect.bottom]
    receipt["window_title"] = window.window_text()
    window.capture_as_image().save(out / "01-first-use.png")
    assert (out / "01-first-use.png").stat().st_size > 1000
    receipt["steps"].append("native_exe_first_use_visible_and_screenshot_saved")

    # Exercise native GUI against disposable fixtures only, never real user files.
    with tempfile.TemporaryDirectory(prefix="integrity-native-e2e-") as folder:
        work = Path(folder)
        target = work / "fixture.txt"
        target.write_bytes(b"integrity-original\\n")
        baseline = {
            "schema": 1, "kind": "file-integrity-ledger",
            "entries": [{"path": str(target), "size": target.stat().st_size,
                         "sha256": hashlib.sha256(target.read_bytes()).hexdigest()}],
        }
        baseline_path = work / "baseline.json"
        baseline_path.write_text(json.dumps(baseline), encoding="utf-8")

        def open_baseline():
            # Tk's common file picker is a native Win32 dialog, not a child of
            # the app's UIA tree. Use the Win32 backend for dialogs and keep UIA
            # for the main application window.
            window.set_focus()
            keyboard.send_keys("^o")
            dialog = Desktop(backend="win32").window(title_re=".*Open snapshot.*")
            dialog.wait("visible", timeout=15)
            edits = dialog.descendants(control_type="Edit")
            assert edits, "Open snapshot dialog has no filename edit"
            edits[-1].set_edit_text(str(baseline_path))
            dialog.child_window(title="Open", control_type="Button").click_input()
            dialog.wait_not("visible", timeout=15)
            time.sleep(0.7)
            texts = [x.window_text() for x in window.descendants() if x.window_text()]
            combined = " ".join(texts)
            assert "Snapshot loaded" in combined, (
                "Snapshot open did not reach the loaded state: " + combined[:500]
            )

        def verify_expected(label, expected):
            window.set_focus()
            keyboard.send_keys("^r")
            time.sleep(0.7)
            if expected != "UNCHANGED":
                warning = Desktop(backend="win32").window(title_re=".*Verify now.*")
                warning.wait("visible", timeout=12)
                warning.capture_as_image().save(out / f"{label}-warning.png")
                warning.child_window(title="OK", control_type="Button").click_input()
                warning.wait_not("visible", timeout=10)
            texts = [x.window_text() for x in window.descendants() if x.window_text()]
            combined = " ".join(texts)
            assert expected in combined, f"{label}: expected {expected}, observed {combined[:500]}"
            window.capture_as_image().save(out / f"{label}.png")
            receipt["steps"].append(f"{label}:{expected}")

        open_baseline()
        receipt["steps"].append("native_snapshot_opened")
        verify_expected("02-unchanged", "UNCHANGED")
        target.write_bytes(b"integrity-changed\\n")
        verify_expected("03-modified", "MODIFIED")
        target.unlink()
        verify_expected("04-missing", "MISSING")
        assert not target.exists(), "Fixture deletion did not occur"
        receipt["steps"].append("fixture_only_no_user_files_accessed")
    window.close()
    proc.wait(timeout=15)
    assert proc.returncode == 0, f"Native EXE exit code {proc.returncode}"
    receipt["steps"].append("native_normal_exit")
    receipt["visual_review_required"] = True
    receipt["result"] = "PASS"
except BaseException as exc:
    receipt["error"] = str(exc)
    (out / "failure-traceback.txt").write_text(traceback.format_exc(), encoding="utf-8")
    if proc is not None and proc.poll() is None:
        try:
            window.capture_as_image().save(out / "failure-window.png")
        except Exception:
            pass
    raise
finally:
    if proc is not None and proc.poll() is None:
        proc.kill()
        proc.wait(timeout=10)
    (out / "receipt.json").write_text(json.dumps(receipt, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print(json.dumps(receipt, ensure_ascii=False))
