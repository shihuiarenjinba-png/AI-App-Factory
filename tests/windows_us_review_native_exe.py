"""Native Windows modal evidence for the US-only PyInstaller EXE.

Consent is exercised through the real Yes/No message box. After approval,
the actual Tk entry dialogs receive a small deterministic sales-tax example;
the final native result dialog is checked for USD output and REVIEW REQUIRED.
No ledger transaction is posted and no Store/MSIX state is touched.
"""
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import time

from PIL import ImageGrab
from pywinauto import Desktop, keyboard

OUT = Path("app-smoke-evidence")
OUT.mkdir(exist_ok=True)
EXE = Path("app-smoke-dist/USFreelanceLedgerSmoke.exe").resolve()
APPDATA = Path(os.environ["RUNNER_TEMP"]) / "us-ledger-native"
os.environ["APPDATA"] = str(APPDATA)
APPDATA.mkdir(parents=True, exist_ok=True)
DB_PATH = APPDATA / "USFreelanceLedger" / "books.sqlite3"
records = []


def capture(label):
    path = OUT / (label + ".png")
    ImageGrab.grab().save(path)
    return {"file": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def wait_window(title, timeout=25):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        matches = [
            w for w in Desktop(backend="win32").windows()
            if title.lower() in w.window_text().lower() and w.is_visible()
        ]
        if matches:
            return matches[0]
        time.sleep(.3)
    visible = [
        w.window_text() for w in Desktop(backend="win32").windows()
        if w.is_visible() and w.window_text()
    ]
    raise AssertionError(f"Native/Tk window not found: {title}; visible={visible[:20]}")


def find_tax_button(main):
    """ttk buttons are not necessarily native Win32 Button children."""
    ui = Desktop(backend="uia").window(handle=main.handle)
    controls = ui.descendants(control_type="Button")
    matches = [c for c in controls if "US tax / fixed assets" in c.window_text()]
    if len(matches) == 1 and matches[0].is_visible() and matches[0].is_enabled():
        return matches[0]
    diagnostics = {
        "uia_buttons": [
            {"name": c.window_text(), "type": c.element_info.control_type,
             "rectangle": str(c.rectangle())}
            for c in controls
        ],
        "win32_children": [
            {"class": c.class_name(), "text": c.window_text(),
             "rectangle": str(c.rectangle())}
            for c in main.descendants()
        ],
    }
    (OUT / "native_controls_diagnostic.json").write_text(
        json.dumps(diagnostics, indent=2), encoding="utf-8"
    )
    capture("native_tax_button_missing")
    # Tk/ttk widgets appear as unnamed TkChild HWNDs on this runner.
    pane_candidates = [
        c for c in main.descendants()
        if c.class_name() == "TkChild"
        and 170 <= c.rectangle().width() <= 260
        and c.rectangle().height() >= 400
    ]
    if len(pane_candidates) != 1:
        raise AssertionError(f"Transaction pane ambiguous: {len(pane_candidates)}")
    pane = pane_candidates[0].rectangle()
    buttons = [
        c for c in main.descendants()
        if c.class_name() == "TkChild"
        and c.rectangle().left >= pane.left
        and c.rectangle().right <= pane.right
        and c.rectangle().width() >= pane.width() * .70
        and 20 <= c.rectangle().height() <= 32
    ]
    buttons.sort(key=lambda c: c.rectangle().top)
    if len(buttons) != 4:
        raise AssertionError(f"Unexpected transaction action layout: {len(buttons)}")
    if not all(
        25 <= buttons[i + 1].rectangle().top - buttons[i].rectangle().top <= 40
        for i in range(3)
    ):
        raise AssertionError("Transaction action row spacing changed")
    target = buttons[-1]
    if not target.is_visible() or not target.is_enabled():
        raise AssertionError("Tax action not visible/enabled")
    return target


def click_named(window, label):
    """Click a visible native Win32/UIA button by its accessible label."""
    def normalized(value):
        return value.replace("&", "").replace("_", "").strip().lower()

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
    if not candidates:
        raise AssertionError(
            f"Expected visible enabled native {label} button in {window.window_text()}"
        )
    # Both backends may expose the same button; prefer Win32.
    candidates[0][1].click_input()


def enter_tk_dialog(title, value):
    """Enter deterministic text in the real Tk simpledialog and submit it.

    Tk simpledialog buttons are not consistently exposed with accessible names
    by the hosted Windows runner. The entry has focus on creation, so keyboard
    input is more reliable than guessing the unnamed Cancel/OK HWND.
    """
    dialog = wait_window(title, timeout=20)
    dialog.set_focus()
    keyboard.send_keys(value, with_spaces=True, pause=0.025)
    keyboard.send_keys("{ENTER}")
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        try:
            if not dialog.is_visible():
                return
        except Exception:
            return
        time.sleep(.2)
    raise AssertionError(f"Tk dialog did not close after input: {title}")


def read_dialog_text(window):
    values = [window.window_text()]
    for backend in ("win32", "uia"):
        try:
            dialog = Desktop(backend=backend).window(handle=window.handle)
            for control in dialog.descendants():
                try:
                    value = control.window_text().strip()
                    if value:
                        values.append(value)
                except Exception:
                    continue
        except Exception:
            continue
    return "\n".join(dict.fromkeys(values))


def transaction_count():
    if not DB_PATH.is_file():
        raise AssertionError(f"US database was not created: {DB_PATH}")
    connection = sqlite3.connect(DB_PATH)
    try:
        return int(connection.execute("SELECT COUNT(*) FROM transactions").fetchone()[0])
    finally:
        connection.close()


def stop_app(main, process):
    try:
        if main is not None and main.is_visible():
            main.close()
    except Exception:
        pass
    try:
        process.wait(timeout=8)
    except subprocess.TimeoutExpired:
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            capture_output=True, text=True, timeout=15
        )
        try:
            process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            raise AssertionError("US Ledger EXE process tree did not stop")


def run_case(accept):
    process = subprocess.Popen([str(EXE)], cwd=str(EXE.parent))
    main = None
    try:
        main = wait_window("Freelance Ledger US")
        main.set_focus()
        find_tax_button(main).click_input()
        review = wait_window("REVIEW REQUIRED — US tax calculation")
        review_text = read_dialog_text(review)
        assert "manual estimate" in review_text.lower(), review_text
        assert "not a tax return or filing" in review_text.lower(), review_text
        before = capture("native_review_" + ("approve" if accept else "decline"))
        click_named(review, "Yes" if accept else "No")
        time.sleep(.5)

        if not accept:
            after = capture("native_declined_main")
            visible_titles = [
                w.window_text() for w in Desktop(backend="win32").windows()
                if w.is_visible()
            ]
            assert not any(
                title in ("Tax / fixed assets", "Sales tax") for title in visible_titles
            ), f"Decline opened a calculator: {visible_titles}"
            stop_app(main, process)
            count = transaction_count()
            assert count == 0, f"Decline path posted {count} transaction(s)"
            records.append({
                "case": "decline",
                "consent_dialog": "native Win32 Yes/No",
                "decision": "No",
                "before": before,
                "after": after,
                "transaction_count": count,
                "no_posting": count == 0,
            })
            return

        # Approval must open the actual calculator; then exercise a small,
        # deterministic USD calculation and verify its visible result.
        enter_tk_dialog("Tax / fixed assets", "sales tax")
        enter_tk_dialog("Sales tax", "100")
        enter_tk_dialog("Sales tax", "7.5")
        enter_tk_dialog("Sales tax", "California")
        result = wait_window("REVIEW REQUIRED — Sales tax")
        result_text = read_dialog_text(result)
        for required in (
            "Jurisdiction: California",
            "Tax USD 7.50",
            "Gross USD 107.50",
            "REVIEW REQUIRED",
            "nexus/taxability is not determined",
            "No posting",
        ):
            assert required in result_text, f"Missing {required!r} in result: {result_text}"
        after = capture("native_approved_usd_result")
        click_named(result, "OK")
        stop_app(main, process)
        count = transaction_count()
        assert count == 0, f"Review-only calculation posted {count} transaction(s)"
        records.append({
            "case": "approve",
            "consent_dialog": "native Win32 Yes/No",
            "decision": "Yes",
            "before": before,
            "after": after,
            "result_text": result_text,
            "expected": {"net_usd": "100.00", "rate_percent": "7.5",
                         "tax_usd": "7.50", "gross_usd": "107.50"},
            "transaction_count": count,
            "no_posting": count == 0,
        })
    finally:
        if process.poll() is None:
            stop_app(main, process)


try:
    run_case(False)
    run_case(True)
finally:
    checkout_sha = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], text=True
    ).strip()
    event_head_sha = None
    event_path = os.environ.get("GITHUB_EVENT_PATH")
    if event_path and Path(event_path).is_file():
        try:
            event = json.loads(Path(event_path).read_text(encoding="utf-8"))
            event_head_sha = event.get("pull_request", {}).get("head", {}).get("sha")
        except (OSError, ValueError, AttributeError):
            event_head_sha = None
    receipt = {
        "checkout_sha": checkout_sha,
        "pr_head_sha": event_head_sha,
        "scenarios": records,
        "exe_sha256": hashlib.sha256(EXE.read_bytes()).hexdigest() if EXE.is_file() else None,
        "smoke_script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "result": "PASS" if len(records) == 2 and all(r["no_posting"] for r in records) else "FAIL",
        "scope": "native consent Yes/No plus visible USD review result; no posting; no MSIX/Store",
    }
    (OUT / "native_receipt.json").write_text(
        json.dumps(receipt, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
print(json.dumps(receipt, ensure_ascii=False))
