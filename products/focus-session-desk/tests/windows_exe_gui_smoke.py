"""Windows-native EXE GUI smoke for Focus Session Desk; fail closed on missing evidence."""
import hashlib
import contextlib
import traceback
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from pywinauto import Desktop
from pywinauto.keyboard import send_keys

exe = Path(sys.argv[1]).resolve()
out = Path(sys.argv[2]).resolve()
out.mkdir(parents=True, exist_ok=True)
assert exe.is_file(), f"Missing real EXE: {exe}"
sha = hashlib.sha256(exe.read_bytes()).hexdigest()
source = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
assert source == os.environ["EXPECTED_SOURCE_SHA"], "Source SHA mismatch"
appdata = Path(os.environ["APPDATA"])
state = appdata / "FocusSessionDesk" / "state.json"
assert not state.exists(), "Expected isolated fresh state"
proc = subprocess.Popen([str(exe)], cwd=str(exe.parent))
receipt = {"source_sha": source, "exe_sha256": sha, "exe_name": exe.name, "steps": []}
try:
    window = Desktop(backend="uia").window(title_re=".*集中セッション.*|.*Focus Session Desk.*")
    window.wait("visible", timeout=45)
    window.set_focus()
    window.capture_as_image().save(out / "01-first-launch.png")
    receipt["steps"].append("native_exe_visible")
    # Window activation can move focus away from the task entry on Windows CI.
    # Target the actual native task Entry explicitly (the last Edit, after minutes).
    edits = window.descendants(control_type="Edit")
    # Tk/ttk controls may be exposed as a single top-level HWND on hosted Windows.
    # Do not require UIA Edit peers: activate the visible task-entry area instead.
    if edits:
        edits[-1].click_input()
        receipt["task_entry_target"] = "uia_last_edit"
    else:
        # Tkinter on hosted Windows exposes widgets as unnamed Pane peers.
        # Locate the wide task-entry pane by its geometry within the task row,
        # rather than requiring a named UIA Button that does not exist.
        win_rect = window.rectangle()
        panes = []
        for control in window.descendants(control_type="Pane"):
            rect = control.rectangle()
            width, height = rect.right - rect.left, rect.bottom - rect.top
            if (0.30 * win_rect.width() < width < 0.75 * win_rect.width()
                    and 15 <= height <= 40
                    and rect.top > win_rect.top + 0.70 * win_rect.height()
                    and rect.bottom < win_rect.bottom - 35):
                panes.append((control, rect))
        assert len(panes) == 1, "Expected one task-entry Pane; found " + repr(
            [[r.left, r.top, r.right, r.bottom] for _, r in panes])
        rect = panes[0][1]
        x, y = (rect.left + rect.right) // 2, (rect.top + rect.bottom) // 2
        from pywinauto.mouse import click
        click(coords=(x, y))
        receipt["task_entry_target"] = "geometry_verified_uia_pane"
        receipt["task_entry_rectangle"] = [rect.left, rect.top, rect.right, rect.bottom]
        receipt["task_entry_click_xy"] = [x, y]
    send_keys("^a{BACKSPACE}Focus smoke task{ENTER}", with_spaces=True, pause=0.08)
    deadline = time.time() + 12
    while time.time() < deadline:
        if state.exists():
            data = json.loads(state.read_text(encoding="utf-8"))
            if len(data["tasks"]) == 1:
                break
        time.sleep(0.3)
    else:
        raise AssertionError("Native Add/Enter did not persist task")
    assert data["tasks"][0]["title"] == "Focus smoke task"
    receipt["steps"].append("task_added_and_persisted")
    window.capture_as_image().save(out / "02-task-added.png")
    # Switch language via actual native button.
    window.child_window(title="English", control_type="Button").click_input()
    time.sleep(0.8)
    assert json.loads(state.read_text(encoding="utf-8"))["language"] == "en"
    receipt["steps"].append("native_language_switch_en")
    window.capture_as_image().save(out / "03-english.png")
    # Start/pause/resume/reset through the native UI, not direct Python model calls.
    for label, expected in (("Start", "running"), ("Pause", "paused"), ("Resume", "running"), ("Reset", "idle")):
        window.child_window(title=label, control_type="Button").click_input()
        time.sleep(0.6)
        saved = json.loads(state.read_text(encoding="utf-8"))
        assert saved["session"] == ("interrupted" if expected in ("running", "paused") else "idle"), (label, saved)
        receipt["steps"].append("native_" + label.lower())
    window.capture_as_image().save(out / "04-reset.png")
    # Persisted task progress is visible in GUI text, not inferred from saved JSON.
    texts = [c.window_text() for c in window.descendants()]
    assert any("Progress: 0/1 complete (0%)" in t for t in texts), "Missing GUI progress label"
    receipt["steps"].append("gui_progress_0_of_1")
    window.close()
    proc.wait(timeout=15)
    assert proc.returncode == 0, f"EXE exited with {proc.returncode}"
    receipt["steps"].append("native_normal_exit")
    receipt["result"] = "PASS"
finally:
    # Preserve actionable evidence even if UIA cannot expose Tkinter widgets.
    if sys.exc_info()[0] is not None:
        receipt["failure_type"] = sys.exc_info()[0].__name__
        receipt["failure_detail"] = str(sys.exc_info()[1])
        (out / "failure-traceback.txt").write_text(
            "".join(traceback.format_exception(*sys.exc_info())), encoding="utf-8"
        )
        with contextlib.suppress(Exception):
            window.capture_as_image().save(out / "failure-window.png")
        with contextlib.suppress(Exception):
            with (out / "uia-tree.txt").open("w", encoding="utf-8") as stream:
                with contextlib.redirect_stdout(stream):
                    window.print_control_identifiers(depth=8)
        with contextlib.suppress(Exception):
            controls = []
            for control in window.descendants():
                rect = control.rectangle()
                controls.append({"name": control.window_text(), "type": control.element_info.control_type,
                                 "rectangle": [rect.left, rect.top, rect.right, rect.bottom]})
            (out / "uia-controls.json").write_text(
                json.dumps(controls, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            # Surface diagnostic control names in the job log as well as the artifact.
            # The artifact is not always directly inspectable by automated supervisors.
            print("GUI_DIAGNOSTIC_CONTROLS=" + json.dumps(controls[:100], ensure_ascii=False), flush=True)
            print("GUI_DIAGNOSTIC_WINDOW_RECT=" + str(window.rectangle()), flush=True)
    if proc.poll() is None:
        proc.kill()
        proc.wait(timeout=10)
    receipt.setdefault("result", "FAIL")
    (out / "receipt.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps(receipt, ensure_ascii=False))
assert receipt["result"] == "PASS"
