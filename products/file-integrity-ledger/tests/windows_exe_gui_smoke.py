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
            window.type_keys("^o", set_foreground=True)
            receipt["steps"].append("native_open_accelerator_sent")
            # Wait for the actual native picker and interact with its edit control.
            # Sending Alt+N and Enter without verifying focus previously left the
            # picker open, causing a false failure at the UNCHANGED assertion.
            picker = None
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                desktop = Desktop(backend="uia")
                candidates = list(desktop.windows()) + list(window.descendants())
                dialogs = [w for w in candidates
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
                open_buttons = [b for b in picker.descendants(control_type="Button")
                                if b.element_info.automation_id == "1" and b.is_visible()]
                if len(open_buttons) == 1:
                    open_buttons[0].click_input()
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
            # Re-enumerate live dialogs instead of trusting a cached UIAWrapper.
            # A destroyed picker can retain stale element visibility in UIA.
            picker_handle = picker.handle
            close_deadline = time.monotonic() + 15
            while time.monotonic() < close_deadline:
                live = [w for w in Desktop(backend="uia").windows()
                        if w.handle == picker_handle
                        and w.element_info.class_name == "#32770"
                        and w.is_visible()]
                if not live:
                    break
                time.sleep(0.25)
            else:
                visible = [(w.window_text(), w.element_info.class_name)
                           for w in Desktop(backend="uia").windows() if w.is_visible()]
                raise AssertionError(f"Snapshot picker remained open; windows={visible!r}")
            window.wait("visible", timeout=15)
            # Tkinter/ttk rows are not reliably exposed by UIA on hosted runners.
            # Capture a post-open image and control inventory before failing closed;
            # picker closure alone is NOT evidence that the snapshot was loaded.
            window.capture_as_image().save(out / "02-after-open.png")
            texts = [x.window_text() for x in window.descendants() if x.window_text()]
            (out / "after-open-controls.json").write_text(
                json.dumps({"visible_texts": texts, "target": str(target),
                            "window_title": window.window_text()}, indent=2), encoding="utf-8")
            # UIA cannot read ttk.Treeview on hosted runners. Do not treat
            # absent UIA text as a failed load; subsequent GUI-driven CSV
            # exports must prove the actual loaded path and status instead.
            receipt["steps"].append("post_open_screenshot_captured_csv_proof_pending")

        def verify_expected(label, expected):
            window.set_focus()
            keyboard.send_keys("^r")
            time.sleep(1)
            if expected != "UNCHANGED":
                # The warning is advisory and may be exposed under a native
                # dialog title, or not shown when the app already refreshed.
                # Do not make the title a proxy for verification success:
                # the GUI-exported CSV status is asserted below.
                warning_deadline = time.monotonic() + 3
                while time.monotonic() < warning_deadline:
                    dialogs = [w for w in Desktop(backend="uia").windows()
                               if w.is_visible() and w.handle != window.handle
                               and (w.element_info.class_name == "#32770"
                                    or "Verify now" in w.window_text())]
                    if dialogs:
                        dialog = dialogs[-1]
                        buttons = [b for b in dialog.descendants(control_type="Button")
                                   if b.is_visible() and
                                   (b.window_text().strip().lower() in ("ok", "&ok", "はい")
                                    or b.element_info.automation_id == "2")]
                        if buttons:
                            buttons[0].click_input()
                        else:
                            dialog.set_focus()
                            keyboard.send_keys("{ENTER}")
                        receipt["steps"].append(f"{label}:advisory_dialog_dismissed")
                        break
                    time.sleep(0.2)
            window.capture_as_image().save(out / f"{label}.png")

            # The app's explicit Ctrl+E binding is stable across Tk themes,
            # accessibility providers, and Windows runner focus traversal.
            # A Tk messagebox may disable its parent without exposing the
            # expected title or #32770 UIA class. Fail closed on unknown modals.
            if not window.is_enabled():
                modals = [w for w in Desktop(backend="uia").windows()
                          if w.is_visible() and w.handle != window.handle
                          and w.process_id() == proc.pid]
                (out / f"{label}-blocking-modal.json").write_text(
                    json.dumps({"windows": [(w.window_text(), w.element_info.class_name)
                                            for w in modals]}, indent=2), encoding="utf-8")
                if not modals:
                    # UIA sometimes omits native Tk messageboxes on hosted
                    # runners. Enumerate actual Win32 top-level windows owned
                    # by this EXE, rather than assuming UIA sees every modal.
                    import win32gui
                    import win32process
                    native_handles = []
                    def collect_modal(hwnd, _):
                        if not win32gui.IsWindowVisible(hwnd) or hwnd == window.handle:
                            return
                        _, pid = win32process.GetWindowThreadProcessId(hwnd)
                        if pid == proc.pid:
                            native_handles.append(hwnd)
                    win32gui.EnumWindows(collect_modal, None)
                    (out / f"{label}-win32-modal.json").write_text(
                        json.dumps({"handles": [
                            {"handle": h, "title": win32gui.GetWindowText(h),
                             "class": win32gui.GetClassName(h)}
                            for h in native_handles]}, indent=2), encoding="utf-8")
                    assert len(native_handles) == 1, (
                        f"{label}: disabled app without unique native modal")
                    # This modal is reached only after the read-only Verify
                    # action. Acknowledge the identified dialog, then require
                    # the parent to become enabled and CSV evidence to match.
                    modal = Desktop(backend="win32").window(handle=native_handles[0])
                    modal.set_focus()
                    keyboard.send_keys("{ENTER}")
                    deadline_enabled = time.monotonic() + 8
                    while time.monotonic() < deadline_enabled and not window.is_enabled():
                        time.sleep(0.2)
                    assert window.is_enabled(), f"{label}: native modal did not close"
                    receipt["steps"].append(f"{label}:win32_modal_acknowledged")
                else:
                    modal = modals[-1]
                    modal.capture_as_image().save(out / f"{label}-blocking-modal.png")
                    ok = [b for b in modal.descendants(control_type="Button")
                          if b.is_visible() and b.is_enabled()
                          and (b.window_text().strip().lower().replace("&", "") in ("ok", "はい")
                               or b.element_info.automation_id in ("1", "2"))]
                    assert len(ok) == 1, f"{label}: modal has no unambiguous OK button"
                    ok[0].click_input()
                    deadline_enabled = time.monotonic() + 8
                    while time.monotonic() < deadline_enabled and not window.is_enabled():
                        time.sleep(0.2)
                    assert window.is_enabled(), f"{label}: app remains disabled after modal OK"
                    receipt["steps"].append(f"{label}:blocking_modal_acknowledged")
            window.set_focus()
            window.click_input(coords=(40, 65))
            keyboard.send_keys("^e")
            receipt["steps"].append(f"{label}:native_export_accelerator_sent")
            export_picker = None
            deadline = time.monotonic() + 12
            while time.monotonic() < deadline:
                dialogs = [w for w in Desktop(backend="uia").windows() + window.descendants()
                           if w.is_visible() and (w.element_info.class_name == "#32770"
                           or w.window_text().strip() in ("Export CSV", "CSV出力"))]
                if dialogs:
                    export_picker = dialogs[-1]
                    break
                time.sleep(0.25)
            if export_picker is None:
                # Capture the actual desktop state before a bounded second
                # accelerator attempt. This distinguishes focus loss from a
                # missing picker without manufacturing CSV output.
                visible = [(w.window_text(), w.element_info.class_name)
                           for w in Desktop(backend="uia").windows() if w.is_visible()]
                (out / f"{label}-export-not-open.json").write_text(
                    json.dumps({"visible_windows": visible, "process_alive": proc.poll() is None,
                                "target": str(target)}, indent=2), encoding="utf-8")
                window.capture_as_image().save(out / f"{label}-export-not-open.png")
                window.set_focus()
                keyboard.send_keys("^e")
                retry_deadline = time.monotonic() + 8
                while time.monotonic() < retry_deadline:
                    dialogs = [w for w in Desktop(backend="uia").windows() + window.descendants()
                               if w.is_visible() and (w.element_info.class_name == "#32770"
                               or w.window_text().strip() in ("Export CSV", "CSV出力"))]
                    if dialogs:
                        export_picker = dialogs[-1]
                        break
                    time.sleep(0.25)
            assert export_picker is not None, f"{label}: GUI CSV export picker not opened; diagnostic captured"
            csv_path = work / f"{label}.csv"
            edits = export_picker.descendants(control_type="Edit")
            if edits:
                filename = next((e for e in edits if e.element_info.automation_id in ("1001", "1148")), edits[-1])
                filename.set_edit_text(str(csv_path))
                buttons = [b for b in export_picker.descendants(control_type="Button")
                           if b.element_info.automation_id == "1" and b.is_visible()]
                if len(buttons) == 1:
                    buttons[0].click_input()
                else:
                    filename.set_focus()
                    keyboard.send_keys("{ENTER}")
            else:
                # Some native Save As dialogs expose no UIA Edit descendants.
                # Try the Win32 filename field before a focused keyboard fallback.
                from pywinauto import Application
                win32_edits = []
                try:
                    native = Application(backend="win32").connect(handle=export_picker.handle).window(handle=export_picker.handle)
                    win32_edits = native.descendants(class_name="Edit")
                except Exception:
                    pass
                if win32_edits:
                    win32_edits[-1].set_edit_text(str(csv_path))
                    win32_edits[-1].set_focus()
                    keyboard.send_keys("{ENTER}")
                else:
                    export_picker.set_focus()
                    keyboard.send_keys("%n")
                    keyboard.send_keys(str(csv_path), with_spaces=True, vk_packet=True)
                    keyboard.send_keys("{ENTER}")
            # A native Save As dialog may accept Enter as filename completion
            # rather than Save. Explicitly activate Save when still open.
            picker_handle = export_picker.handle
            if not csv_path.exists():
                live = [w for w in Desktop(backend="uia").windows()
                        if w.handle == picker_handle and w.is_visible()]
                if live:
                    save_buttons = [b for b in live[0].descendants(control_type="Button")
                                    if b.is_visible() and
                                    (b.element_info.automation_id == "1" or
                                     b.window_text().strip().lower() in ("save", "&save"))]
                    if len(save_buttons) == 1:
                        save_buttons[0].click_input()
                    else:
                        live[0].set_focus()
                        keyboard.send_keys("%s")
            deadline = time.monotonic() + 12
            while time.monotonic() < deadline and not csv_path.exists():
                time.sleep(0.25)
            if not csv_path.exists():
                # Preserve concrete evidence before failing closed; never
                # substitute an independently generated CSV for GUI output.
                visible = [(w.window_text(), w.element_info.class_name)
                           for w in Desktop(backend="uia").windows() if w.is_visible()]
                (out / f"{label}-save-diagnostic.json").write_text(
                    json.dumps({"requested_path": str(csv_path),
                                "work_files": [p.name for p in work.iterdir()],
                                "visible_windows": visible}, indent=2), encoding="utf-8")
                try:
                    Desktop(backend="uia").window(handle=picker_handle).capture_as_image().save(
                        out / f"{label}-save-picker.png")
                except Exception:
                    pass
            assert csv_path.exists(), f"{label}: GUI did not write CSV"
            with csv_path.open(encoding="utf-8-sig", newline="") as stream:
                rows = list(csv.DictReader(stream))
            assert len(rows) == 1, f"{label}: expected exactly one CSV row, got {rows!r}"
            assert rows[0]["path"] == str(target), f"{label}: wrong fixture path"
            assert rows[0]["status"] == expected, (
                f"{label}: expected {expected}, got {rows[0]['status']}")
            receipt["steps"].append(f"{label}:{expected}:gui_csv_verified")
            receipt.setdefault("csv_evidence", {})[label] = rows[0]
            (out / f"{label}.csv").write_bytes(csv_path.read_bytes())

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
