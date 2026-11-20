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
from pywinauto.mouse import click

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
    # Tk/ttk buttons are unnamed Pane peers on this Windows runner. Resolve
    # the unique footer language button by measured window-relative geometry.
    def click_native_pane(area, *, expected_width=(60, 100)):
        win = window.rectangle()
        candidates = []
        for control in window.descendants(control_type="Pane"):
            rect = control.rectangle()
            width, height = rect.right - rect.left, rect.bottom - rect.top
            if (expected_width[0] <= width <= expected_width[1]
                    and 15 <= height <= 40 and area(rect, win)):
                candidates.append(rect)
        assert len(candidates) == 1, "Ambiguous native Pane target: " + repr(
            [[r.left, r.top, r.right, r.bottom] for r in candidates])
        r = candidates[0]
        click(coords=((r.left + r.right) // 2, (r.top + r.bottom) // 2))
        return [r.left, r.top, r.right, r.bottom]

    # UIA exposes Tk/ttk widgets as unnamed Pane peers; clicking their UIA
    # rectangles did not activate the language button on the Windows runner.
    # Use Tk's native keyboard focus traversal instead. In build(), the task
    # Entry is followed by six task buttons and then the language button.
    receipt["language_before"] = json.loads(state.read_text(encoding="utf-8"))["language"]
    assert receipt["language_before"] == "ja"
    entry_rect = receipt["task_entry_rectangle"] if receipt["task_entry_target"] == "geometry_verified_uia_pane" else None
    if entry_rect is None:
        # The actual task entry is the last Edit in this UI, when exposed.
        er = edits[-1].rectangle()
        entry_rect = [er.left, er.top, er.right, er.bottom]
    click(coords=((entry_rect[0] + entry_rect[2]) // 2,
                  (entry_rect[1] + entry_rect[3]) // 2))
    send_keys("{TAB 7}{SPACE}", pause=0.12)
    deadline = time.time() + 5
    while time.time() < deadline:
        if json.loads(state.read_text(encoding="utf-8"))["language"] == "en":
            break
        time.sleep(0.2)
    else:
        window.capture_as_image().save(out / "language-keyboard-failed.png")
        raise AssertionError("Native keyboard focus traversal did not persist en")
    receipt["language_method"] = "task_entry_tab_7_space"
    receipt["steps"].append("native_language_switch_en")
    window.capture_as_image().save(out / "03-english.png")
    # Start/pause/resume/reset through the native UI, not direct Python model calls.
    def w_top(win, rect):
        return (win.top + 0.28 * win.height() < rect.top < win.top + 0.40 * win.height())

    for label, expected in (("Start", "running"), ("Pause", "paused"), ("Resume", "running"), ("Reset", "idle")):
        # Native timer row: duration, start, pause/resume, reset. Use the
        # measured Pane row, not inaccessible UIA Button names.
        index = {"Start": 1, "Pause": 2, "Resume": 2, "Reset": 3}[label]
        win = window.rectangle()
        row = sorted((c.rectangle() for c in window.descendants(control_type="Pane")
                      if 60 <= c.rectangle().width() <= 100
                      and 15 <= c.rectangle().height() <= 40
                      and w_top(win, c.rectangle())), key=lambda r: r.left)
        assert len(row) == 4, "Expected four timer controls; got " + repr(
            [[r.left, r.top, r.right, r.bottom] for r in row])
        r = row[index]
        click(coords=((r.left + r.right) // 2, (r.top + r.bottom) // 2))
        time.sleep(0.6)
        saved = json.loads(state.read_text(encoding="utf-8"))
        assert saved["session"] == ("interrupted" if expected in ("running", "paused") else "idle"), (label, saved)
        receipt["steps"].append("native_" + label.lower())
    window.capture_as_image().save(out / "04-reset.png")
    # Tk labels are unnamed Pane peers on this Windows runner, so UIA
    # window_text() cannot verify the progress string. Preserve a real native
    # screenshot for visual review and independently assert persisted counts.
    # Do not misreport this as machine-verified GUI text.
    saved = json.loads(state.read_text(encoding="utf-8"))
    assert len(saved["tasks"]) == 1 and not saved["tasks"][0]["done"], saved["tasks"]
    progress_image = window.capture_as_image()
    progress_image.save(out / "05-progress-review-required.png")
    receipt["progress_expected_text"] = "Progress: 0/1 complete (0%)"
    receipt["progress_evidence"] = "05-progress-review-required.png"
    receipt["progress_visual_review_required"] = True
    receipt["steps"].append("progress_state_verified_screenshot_captured")
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
