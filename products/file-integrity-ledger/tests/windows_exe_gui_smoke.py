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
            window.set_focus()
            # Tk/ttk child widgets are not exposed as UIA Button controls on
            # hosted Windows runners. Use the application's bound accelerator,
            # after explicitly focusing the Tk client area (not the title bar).
            # The native picker below is the observable proof that it worked.
            window.click_input(coords=(40, 65))
            keyboard.send_keys("^o")
            receipt["steps"].append("native_open_accelerator_sent")
            # Wait for the actual native picker and interact with its edit control.
            # Sending Alt+N and Enter without verifying focus previously left the
            # picker open, causing a false failure at the UNCHANGED assertion.
            picker = None
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                dialogs = [w for w in Desktop(backend="uia").windows()
                           if w.is_visible() and w.element_info.class_name == "#32770"]
                if dialogs:
                    picker = dialogs[-1]
                    break
                time.sleep(0.25)
            if picker is None:
                visible = [(w.window_text(), w.element_info.class_name)
                           for w in Desktop(backend="uia").windows() if w.is_visible()]
                raise AssertionError(f"Native picker not found; windows: {visible!r}")
            # Some hosted Windows pickers expose no UIA Edit control.
            # Try UIA, Win32, then the keyboard filename shortcut.
            edits = picker.descendants(control_type="Edit")
            if edits:
                filename = next((e for e in edits if e.element_info.automation_id == "1148"), edits[-1])
                filename.set_edit_text(str(baseline_path))
                open_button = picker.child_window(auto_id="1", control_type="Button")
                if open_button.exists(timeout=2):
                    open_button.click_input()
                else:
                    filename.set_focus()
                    keyboard.send_keys("{ENTER}")
            else:
                from pywinauto import Application
                win32_edits = []
                try:
                    native = Application(backend="win32").connect(handle=picker.handle).window(handle=picker.handle)
                    win32_edits = native.descendants(class_name="Edit")
                except Exception:
                    pass
                if win32_edits:
                    win32_edits[-1].set_edit_text(str(baseline_path))
                    keyboard.send_keys("{ENTER}")
                else:
                    picker.set_focus()
                    keyboard.send_keys("%n")
                    keyboard.send_keys(str(baseline_path), with_spaces=True, vk_packet=True)
                    keyboard.send_keys("{ENTER}")
            # Desktop.windows() yields UIAWrapper instances, not WindowSpecification.
            # UIAWrapper has no wait_not(); poll actual visibility.
            close_deadline = time.monotonic() + 15
            while time.monotonic() < close_deadline:
                try:
                    if not picker.is_visible():
                        break
                except (RuntimeError, LookupError, OSError):
                    break  # Destroyed native dialog also means closed.
                time.sleep(0.25)
            else:
                visible = [(w.window_text(), w.element_info.class_name)
                           for w in Desktop(backend="uia").windows() if w.is_visible()]
                raise AssertionError(f"Snapshot picker remained open; windows={visible!r}")
            window.wait("visible", timeout=15)
            texts = [x.window_text() for x in window.descendants() if x.window_text()]
            assert str(target) in " ".join(texts), "Snapshot picker closed without loading fixture"

        def verify_expected(label, expected):
            window.set_focus()
            keyboard.send_keys("^r")
            time.sleep(0.7)
            if expected != "UNCHANGED":
                warning = Desktop(backend="uia").window(title_re=".*Verify now.*")
                warning.wait("visible", timeout=12)
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
