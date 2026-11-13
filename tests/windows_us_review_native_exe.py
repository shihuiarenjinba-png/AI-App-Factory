"""Native Windows modal evidence for US-only PyInstaller EXE. No dialog mocking."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

from PIL import ImageGrab
from pywinauto import Desktop, Application

OUT = Path("app-smoke-evidence")
OUT.mkdir(exist_ok=True)
EXE = Path("app-smoke-dist/USFreelanceLedgerSmoke.exe").resolve()
os.environ["APPDATA"] = str(Path(os.environ["RUNNER_TEMP"]) / "us-ledger-native")
Path(os.environ["APPDATA"]).mkdir(parents=True, exist_ok=True)
records = []

def capture(label):
    path = OUT / (label + ".png")
    ImageGrab.grab().save(path)
    return {"file": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}

def wait_window(title, timeout=25):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        matches = [w for w in Desktop(backend="win32").windows()
                   if title.lower() in w.window_text().lower() and w.is_visible()]
        if matches:
            return matches[0]
        time.sleep(.4)
    raise AssertionError("Native window not found: " + title)

def click_named(window, label):
    matches = [c for c in window.descendants(class_name="Button")
               if c.window_text().strip().lower() == label.lower()]
    if len(matches) != 1:
        raise AssertionError(f"Expected one native {label} button; found {len(matches)}")
    matches[0].click_input()

def run_case(accept):
    p = subprocess.Popen([str(EXE)], cwd=str(EXE.parent))
    try:
        main = wait_window("Freelance Ledger US")
        main.set_focus()
        buttons = [b for b in main.descendants(class_name="Button")
                   if "US tax / fixed assets" in b.window_text()]
        if len(buttons) != 1:
            raise AssertionError(f"Tax action button count: {len(buttons)}")
        buttons[0].click_input()
        modal = wait_window("REVIEW REQUIRED")
        if "manual estimate" not in modal.window_text().lower() and not any(
            "manual estimate" in c.window_text().lower() for c in modal.descendants()
        ):
            raise AssertionError("Tax review warning text missing")
        before = capture("native_review_" + ("approve" if accept else "decline"))
        click_named(modal, "Yes" if accept else "No")
        time.sleep(.8)
        if accept:
            mode = wait_window("Tax / fixed assets")
            after = capture("native_approved_mode")
            # Cancel the mode prompt: verify native consent without posting.
            click_named(mode, "Cancel")
            time.sleep(.5)
        else:
            after = capture("native_declined_main")
            assert not any("Tax / fixed assets" in w.window_text()
                           for w in Desktop(backend="win32").windows()
                           if w.is_visible() and w.handle != main.handle)
        records.append({"case": "approve" if accept else "decline",
                        "dialog_method": "native Win32 click_input, no monkeypatch",
                        "before": before, "after": after, "no_posting": True})
    finally:
        subprocess.run(["taskkill", "/PID", str(p.pid), "/T", "/F"],
                       capture_output=True, text=True, timeout=15)

try:
    run_case(False)
    run_case(True)
finally:
    (OUT / "native_receipt.json").write_text(json.dumps({
        "source_sha": os.environ.get("GITHUB_SHA"), "scenarios": records,
        "exe_sha256": hashlib.sha256(EXE.read_bytes()).hexdigest(),
        "scope": "native modal consent only; USD calculation result not yet validated"
    }, indent=2), encoding="utf-8")
