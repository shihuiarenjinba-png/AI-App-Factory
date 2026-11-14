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

def find_tax_button(main):
    """ttk buttons are not necessarily native Win32 Button children."""
    ui = Desktop(backend="uia").window(handle=main.handle)
    controls = ui.descendants(control_type="Button")
    matches = [c for c in controls if "US tax / fixed assets" in c.window_text()]
    if len(matches) == 1 and matches[0].is_visible() and matches[0].is_enabled():
        return matches[0]
    diagnostics = {"uia_buttons": [{"name": c.window_text(), "type": c.element_info.control_type,
                                      "rectangle": str(c.rectangle())} for c in controls],
                   "win32_children": [{"class": c.class_name(), "text": c.window_text(),
                                       "rectangle": str(c.rectangle())} for c in main.descendants()]}
    (OUT / "native_controls_diagnostic.json").write_text(json.dumps(diagnostics, indent=2), encoding="utf-8")
    capture("native_tax_button_missing")
    # Tk/ttk widgets appear as unnamed TkChild HWNDs on this runner.
    # The captured runner screenshot and Win32 tree identify the tax action
    # between Add transaction and Export CSV in the left Transaction pane.
    # Derive the target from the live pane geometry, never screen pixels.
    pane_candidates = [c for c in main.descendants()
                       if c.class_name() == "TkChild" and
                       170 <= c.rectangle().width() <= 260 and
                       c.rectangle().height() >= 400]
    if len(pane_candidates) != 1:
        raise AssertionError(f"Transaction pane ambiguous: {len(pane_candidates)}")
    pane = pane_candidates[0].rectangle()
    buttons = [c for c in main.descendants()
               if c.class_name() == "TkChild" and
               c.rectangle().left >= pane.left and
               c.rectangle().right <= pane.right and
               c.rectangle().width() >= pane.width() * .70 and
               20 <= c.rectangle().height() <= 32]
    buttons.sort(key=lambda c: c.rectangle().top)
    # The four consecutive full-width actions are Browse, Suggest,
    # Add transaction, Tax review; the next row is split Export/Backup.
    if len(buttons) != 4:
        raise AssertionError(f"Unexpected transaction action layout: {len(buttons)}")
    if not all(25 <= buttons[i+1].rectangle().top - buttons[i].rectangle().top <= 40
               for i in range(3)):
        raise AssertionError("Transaction action row spacing changed")
    target = buttons[-1]
    if not target.is_visible() or not target.is_enabled():
        raise AssertionError("Tax action not visible/enabled")
    return target

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
        find_tax_button(main).click_input()
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
