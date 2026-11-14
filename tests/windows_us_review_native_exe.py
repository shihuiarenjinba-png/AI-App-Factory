"""Native Windows modal evidence for US-only PyInstaller EXE. No dialog mocking."""
import hashlib
import json
import os
import sqlite3
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

def ledger_snapshot():
    """Hash a consistent SQLite logical snapshot, not an unverified assertion."""
    db = Path(os.environ["APPDATA"]) / "USFreelanceLedger" / "books.sqlite3"
    if not db.is_file():
        raise AssertionError("Expected isolated US ledger database is missing")
    with sqlite3.connect(str(db)) as conn:
        with sqlite3.connect(":memory:") as snapshot:
            conn.backup(snapshot)
            dump = "\\n".join(snapshot.iterdump()).encode("utf-8")
    return {"path": str(db), "sha256": hashlib.sha256(dump).hexdigest()}

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
    """Use a verified native control, including UIA and mnemonic-prefixed labels."""
    def normalized(text):
        return text.replace("&", "").replace("_", "").strip().lower()

    candidates = []
    for backend in ("win32", "uia"):
        try:
            dialog = Desktop(backend=backend).window(handle=window.handle)
            for control in dialog.descendants():
                try:
                    if normalized(control.window_text()) != label.lower():
                        continue
                    if backend == "win32" and control.class_name() != "Button":
                        continue
                    if backend == "uia" and control.element_info.control_type != "Button":
                        continue
                    if control.is_visible() and control.is_enabled():
                        candidates.append((backend, control))
                except Exception:
                    continue
        except Exception:
            continue
    if candidates:
        # Both backends may expose the same button; prefer Win32.
        candidates[0][1].click_input()
        return

    diagnostics = {"label": label, "modal_title": window.window_text(),
                   "modal_handle": window.handle, "controls": {}}
    for backend in ("win32", "uia"):
        try:
            dialog = Desktop(backend=backend).window(handle=window.handle)
            diagnostics["controls"][backend] = [
                {"text": c.window_text(), "class": c.class_name(),
                 "rectangle": str(c.rectangle())}
                for c in dialog.descendants()
            ]
        except Exception as exc:
            diagnostics["controls"][backend] = {"error": repr(exc)}
    (OUT / ("native_modal_" + label.lower() + "_diagnostic.json")).write_text(
        json.dumps(diagnostics, indent=2), encoding="utf-8")
    capture("native_modal_" + label.lower() + "_missing")
    raise AssertionError(f"Expected one visible enabled native {label} button; found 0")

def run_case(accept):
    p = subprocess.Popen([str(EXE)], cwd=str(EXE.parent))
    try:
        main = wait_window("Freelance Ledger US")
        main.set_focus()
        ledger_before = ledger_snapshot()
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
            # Verify native USD arithmetic result, not only consent.
            from pywinauto.keyboard import send_keys
            def answer_dialog(dialog, value):
                dialog.set_focus()
                send_keys("^a")
                send_keys(str(value), with_spaces=True)
                send_keys("{ENTER}")
                time.sleep(.5)

            answer_dialog(mode, "sales tax")
            answer_dialog(wait_window("Sales tax"), "100")
            answer_dialog(wait_window("Sales tax"), "8")
            answer_dialog(wait_window("Sales tax"), "Fixture jurisdiction")
            result = wait_window("REVIEW REQUIRED — Sales tax")
            result_text = "\\n".join([result.window_text()] +
                [child.window_text() for child in result.descendants()])
            for expected in ("Tax USD 8.0", "Gross USD 108.0",
                             "REVIEW REQUIRED", "No posting"):
                if expected.lower() not in result_text.lower():
                    capture("native_usd_result_mismatch")
                    raise AssertionError(
                        f"Native USD result missing {expected!r}: {result_text!r}")
            after = capture("native_usd_result_verified")
            click_named(result, "OK")
            calculation = {"inputs": {"amount_usd": 100, "manual_rate_percent": 8,
                                       "jurisdiction": "Fixture jurisdiction"},
                           "expected": {"tax_usd": 8, "gross_usd": 108},
                           "observed_dialog": result_text,
                           "screenshot": after,
                           "scope": "arithmetic only; not a legal tax-rate assertion"}
        else:
            after = capture("native_declined_main")
            assert not any("Tax / fixed assets" in w.window_text()
                           for w in Desktop(backend="win32").windows()
                           if w.is_visible() and w.handle != main.handle)
        ledger_after = ledger_snapshot()
        if ledger_before["sha256"] != ledger_after["sha256"]:
            raise AssertionError("Tax review consent changed the US ledger database")
        records.append({"case": "approve" if accept else "decline",
                        "dialog_method": "native Win32 click_input, no monkeypatch",
                        "before": before, "after": after, "no_posting": True,
                        "ledger_before": ledger_before, "ledger_after": ledger_after,
                        **({"usd_sales_tax_result": calculation} if accept else {})})
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
        "scope": "native consent and fixed-input USD sales-tax arithmetic; not legal tax advice"
    }, indent=2), encoding="utf-8")
