"""Real Windows desktop smoke for the US Ledger novice REVIEW REQUIRED flow.

Runs the actual Tk window, physically clicks the review button and native
message-box buttons, enters manual USD values in the real dialogs, and saves
screenshots plus a hash-bound receipt. It uses a temporary APPDATA sandbox and
must never post a ledger transaction or alter the JP sentinel database.
"""
from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone

from PIL import ImageGrab


if sys.platform != "win32":
    raise SystemExit("US Ledger GUI smoke requires a Windows desktop runner")

ROOT = Path(__file__).resolve().parents[1]
US = ROOT / "products" / "us-freelance-ledger"
sys.path.insert(0, str(US))
import main as us_main  # noqa: E402


user32 = ctypes.windll.user32
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
BM_CLICK = 0x00F5


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", wintypes.LONG),
        ("top", wintypes.LONG),
        ("right", wintypes.LONG),
        ("bottom", wintypes.LONG),
    ]


ENUM_WINDOWS_PROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
ENUM_CHILD_PROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


def _title(hwnd: int) -> str:
    length = user32.GetWindowTextLengthW(hwnd)
    buffer = ctypes.create_unicode_buffer(max(1, length + 1))
    user32.GetWindowTextW(hwnd, buffer, len(buffer))
    return buffer.value


def _find_window(title: str) -> int | None:
    found: list[int] = []

    @ENUM_WINDOWS_PROC
    def visit(hwnd, _):
        if user32.IsWindowVisible(hwnd) and _title(hwnd) == title:
            found.append(hwnd)
            return False
        return True

    user32.EnumWindows(visit, 0)
    return found[0] if found else None


def _wait_window(title: str, timeout: float = 8.0) -> int:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        hwnd = _find_window(title)
        if hwnd:
            return hwnd
        time.sleep(0.05)
    raise TimeoutError(f"Windows dialog not found: {title}")


def _click_screen(x: int, y: int) -> None:
    if not user32.SetCursorPos(x, y):
        raise OSError("SetCursorPos failed")
    time.sleep(0.08)
    user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    time.sleep(0.04)
    user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)


def _click_dialog_button(hwnd: int, label: str) -> None:
    matches: list[int] = []

    @ENUM_CHILD_PROC
    def visit(child, _):
        caption = _title(child).replace("&", "").strip().casefold()
        if caption == label.casefold():
            matches.append(child)
            return False
        return True

    user32.EnumChildWindows(hwnd, visit, 0)
    if not matches:
        raise RuntimeError(f"Dialog button not found: {label} in {_title(hwnd)!r}")
    rect = RECT()
    if not user32.GetWindowRect(matches[0], ctypes.byref(rect)):
        raise OSError(f"GetWindowRect failed for {label}")
    _click_screen((rect.left + rect.right) // 2, (rect.top + rect.bottom) // 2)


def _walk(widget):
    for child in widget.winfo_children():
        yield child
        yield from _walk(child)


def _find_tk_toplevel(app, title: str):
    deadline = time.monotonic() + 8.0
    while time.monotonic() < deadline:
        for child in app.winfo_children():
            if isinstance(child, us_main.tk.Toplevel) and child.title() == title:
                return child
        time.sleep(0.05)
    raise TimeoutError(f"Tk dialog not found: {title}")


def _fill_tk_dialog(app, title: str, value: str, screenshot: str, capture) -> None:
    dialog = _find_tk_toplevel(app, title)
    widgets = list(_walk(dialog))
    entries = [
        widget for widget in widgets
        if isinstance(widget, (us_main.tk.Entry, us_main.ttk.Entry))
    ]
    buttons = [
        widget for widget in widgets
        if isinstance(widget, (us_main.tk.Button, us_main.ttk.Button))
        and widget.cget("text") == "OK"
    ]
    if len(entries) != 1 or len(buttons) != 1:
        raise RuntimeError(
            f"Expected one Entry and one OK button in {title!r}; "
            f"found {len(entries)} and {len(buttons)}"
        )
    entry = entries[0]
    entry.delete(0, "end")
    entry.insert(0, value)
    entry.focus_force()
    app.update_idletasks()
    capture(screenshot)
    _click_widget(buttons[0])


def _find_review_button(app):
    expected = "US tax — REVIEW REQUIRED"
    matches = [
        widget for widget in _walk(app)
        if isinstance(widget, us_main.ttk.Button)
        and widget.cget("text") == expected
    ]
    if len(matches) != 1:
        raise RuntimeError(f"Expected one review button, found {len(matches)}")
    return matches[0]


def _click_widget(widget) -> None:
    widget.update_idletasks()
    if not widget.winfo_ismapped():
        raise RuntimeError("Review button is not mapped/visible")
    x = widget.winfo_rootx() + widget.winfo_width() // 2
    y = widget.winfo_rooty() + widget.winfo_height() // 2
    _click_screen(x, y)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(ROOT), *args],
        check=True, capture_output=True, text=True, timeout=30,
    ).stdout.strip()


def run(output: Path) -> dict:
    if output.exists() or output.is_symlink():
        raise ValueError("Refusing to overwrite existing GUI evidence")
    output.mkdir(parents=True, exist_ok=False)
    source_sha = _git("rev-parse", "HEAD")
    expected_sha = os.environ.get("EXPECTED_SOURCE_SHA", source_sha)
    if source_sha != expected_sha:
        raise ValueError(
            f"GUI checkout is not exact PR source HEAD: {source_sha} != {expected_sha}"
        )

    state = {
        "errors": [],
        "review_prompts": [],
        "simple_dialogs": [],
        "result_dialogs": [],
        "screenshots": [],
    }
    real_askyesno = us_main.messagebox.askyesno
    real_askstring = us_main.simpledialog.askstring
    real_askfloat = us_main.simpledialog.askfloat
    real_showinfo = us_main.messagebox.showinfo
    real_confirm = us_main.confirm_us_tax_review
    app = None

    def capture(name: str) -> None:
        path = output / name
        ImageGrab.grab().save(path)
        state["screenshots"].append({
            "file": name,
            "sha256": _sha256(path),
            "bytes": path.stat().st_size,
        })

    def schedule_dialog(title: str, screenshot: str, *, button=None, text=None) -> None:
        def action():
            try:
                if button is not None:
                    hwnd = _wait_window(title)
                    user32.SetForegroundWindow(hwnd)
                    time.sleep(0.12)
                    capture(screenshot)
                    _click_dialog_button(hwnd, button)
                else:
                    _fill_tk_dialog(app, title, text or "", screenshot, capture)
            except Exception as exc:  # make CI fail instead of hanging on a modal dialog
                state["errors"].append(f"{title}: {type(exc).__name__}: {exc}")
                if app is not None:
                    app.after(100, app.close)

        app.after(600, action)

    def automated_askyesno(title, message, parent=None):
        index = len(state["review_prompts"])
        if index > 1:
            raise RuntimeError("Unexpected extra REVIEW REQUIRED confirmation")
        expected = index == 1  # first run declines; second run approves
        state["review_prompts"].append({
            "title": title,
            "message": message,
            "expected_decision": "APPROVE" if expected else "DECLINE",
        })
        schedule_dialog(
            title,
            f"review-required-{'approve' if expected else 'decline'}.png",
            button="Yes" if expected else "No",
        )
        result = real_askyesno(title, message, parent=parent)
        state["review_prompts"][index]["actual_result"] = bool(result)
        if result is not expected:
            raise AssertionError(f"Unexpected review result for {expected=}: {result=}")
        if not expected and state["simple_dialogs"]:
            raise AssertionError("Declining review opened a calculator dialog")
        return result

    askstring_values = ["sales tax", "California"]
    askfloat_values = [100.0, 7.5]

    def automated_askstring(title, prompt, parent=None, **kwargs):
        if not askstring_values:
            raise RuntimeError(f"Unexpected askstring dialog: {title} / {prompt}")
        value = askstring_values.pop(0)
        state["simple_dialogs"].append({
            "kind": "string", "title": title, "prompt": prompt, "value": value,
        })
        schedule_dialog(
            title,
            f"input-{len(state['simple_dialogs'])}.png",
            text=value,
        )
        result = real_askstring(title, prompt, parent=parent, **kwargs)
        if result != value:
            raise AssertionError(f"Dialog returned {result!r}, expected {value!r}")
        return result

    def automated_askfloat(title, prompt, parent=None, **kwargs):
        if not askfloat_values:
            raise RuntimeError(f"Unexpected askfloat dialog: {title} / {prompt}")
        value = askfloat_values.pop(0)
        state["simple_dialogs"].append({
            "kind": "float", "title": title, "prompt": prompt, "value": value,
        })
        schedule_dialog(
            title,
            f"input-{len(state['simple_dialogs'])}.png",
            text=str(value),
        )
        result = real_askfloat(title, prompt, parent=parent, **kwargs)
        if result is None or abs(float(result) - value) > 1e-9:
            raise AssertionError(f"Dialog returned {result!r}, expected {value!r}")
        return result

    def automated_showinfo(title, message, parent=None, **kwargs):
        index = len(state["result_dialogs"])
        state["result_dialogs"].append({"title": title, "message": message})
        screenshot = (
            "decline-result.png" if index == 0 else "approved-result.png"
        )
        schedule_dialog(title, screenshot, button="OK")
        if parent is None:
            result = real_showinfo(title, message, **kwargs)
        else:
            result = real_showinfo(title, message, parent=parent, **kwargs)
        if index == 0:
            app.after(500, lambda: _click_widget(review_button))
        elif index == 1:
            app.after(500, app.close)
        else:
            state["errors"].append(f"Unexpected extra result dialog: {title}")
            app.after(100, app.close)
        return result

    with tempfile.TemporaryDirectory(prefix="us-ledger-review-gui-") as tmp:
        appdata = Path(tmp)
        os.environ["APPDATA"] = str(appdata)

        jp_dir = appdata / "JPFreelanceLedger"
        jp_dir.mkdir()
        jp_db = jp_dir / "books.sqlite3"
        jp_connection = sqlite3.connect(jp_db)
        try:
            jp_connection.execute(
                "CREATE TABLE sentinel (value TEXT NOT NULL)"
            )
            jp_connection.execute("INSERT INTO sentinel VALUES ('JP-KEEP')")
            jp_connection.commit()
        finally:
            jp_connection.close()
        jp_before = jp_db.read_bytes()
        jp_before_sha = hashlib.sha256(jp_before).hexdigest()

        app = us_main.App()
        app.update_idletasks()
        app.update()
        app.lift()
        app.focus_force()
        app.update()
        review_button = _find_review_button(app)
        capture("main-window.png")

        us_main.confirm_us_tax_review = (
            lambda parent: real_confirm(parent, askyesno=automated_askyesno)
        )
        us_main.simpledialog.askstring = automated_askstring
        us_main.simpledialog.askfloat = automated_askfloat
        us_main.messagebox.showinfo = automated_showinfo

        app.after(1200, lambda: _click_widget(review_button))

        def timeout():
            state["errors"].append("GUI smoke timeout")
            app.close()

        app.after(30000, timeout)
        app.mainloop()

        if state["errors"]:
            raise RuntimeError("; ".join(state["errors"]))
        if len(state["review_prompts"]) != 2:
            raise AssertionError("Expected one decline and one approve confirmation")
        if [item["expected_decision"] for item in state["review_prompts"]] != [
            "DECLINE", "APPROVE"
        ]:
            raise AssertionError("Review decisions were not exercised in order")
        if len(state["simple_dialogs"]) != 4 or askstring_values or askfloat_values:
            raise AssertionError("Expected mode, amount, rate and jurisdiction dialogs")
        if len(state["result_dialogs"]) != 2:
            raise AssertionError("Expected visible decline and approved result dialogs")

        decline_result = state["result_dialogs"][0]
        approved_result = state["result_dialogs"][1]
        if decline_result["title"] != "US tax calculation canceled":
            raise AssertionError("Decline result title was not visible")
        if "No calculator was opened" not in decline_result["message"]:
            raise AssertionError("Decline result did not explain that calculation was skipped")
        if "no ledger entry was created" not in decline_result["message"]:
            raise AssertionError("Decline result did not explain the no-write boundary")
        for required in (
            "REVIEW REQUIRED", "Tax USD 7.50", "Gross USD 107.50", "No posting"
        ):
            if required not in approved_result["title"] + " " + approved_result["message"]:
                raise AssertionError(f"Approved result missing required text: {required}")

        if jp_db.read_bytes() != jp_before:
            raise AssertionError("US GUI flow changed the JP sentinel database")
        us_db = appdata / "USFreelanceLedger" / "books.sqlite3"
        if not us_db.is_file():
            raise AssertionError("US APPDATA database was not created")
        read_conn = sqlite3.connect(us_db)
        try:
            transactions = read_conn.execute(
                "SELECT COUNT(*) FROM transactions"
            ).fetchone()[0]
            audit_entries = read_conn.execute(
                "SELECT COUNT(*) FROM audit_log"
            ).fetchone()[0]
        finally:
            read_conn.close()
        if transactions != 0 or audit_entries != 0:
            raise AssertionError(
                f"Review-only GUI changed ledger: transactions={transactions}, "
                f"audit_entries={audit_entries}"
            )

        receipt = {
            "schema_version": 1,
            "stage": "US_LEDGER_WINDOWS_GUI_REVIEW_SMOKE",
            "status": "PASS",
            "source_repository": "shihuiarenjinba-png/AI-App-Factory",
            "source_branch": (
                os.environ.get("GITHUB_HEAD_REF")
                or os.environ.get("GITHUB_REF_NAME", "")
            ),
            "source_sha": source_sha,
            "expected_source_sha": expected_sha,
            "main_py_sha256": _sha256(US / "main.py"),
            "core_py_sha256": _sha256(US / "core.py"),
            "review_decisions": state["review_prompts"],
            "manual_dialogs": state["simple_dialogs"],
            "result_dialogs": state["result_dialogs"],
            "ledger_transactions_after_review": transactions,
            "ledger_audit_entries_after_review": audit_entries,
            "jp_sentinel_unchanged": True,
            "jp_sentinel_sha256": jp_before_sha,
            "screenshots": state["screenshots"],
            "completed_at_utc": datetime.now(timezone.utc).isoformat(),
        }
        receipt_path = output / "gui-review-receipt.json"
        receipt_path.write_text(
            json.dumps(receipt, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        receipt_sha = _sha256(receipt_path)
        print("US_LEDGER_GUI_REVIEW_PASS", json.dumps({
            "source_sha": source_sha,
            "receipt_sha256": receipt_sha,
            "screenshots": [item["file"] for item in state["screenshots"]],
            "ledger_transactions": transactions,
            "ledger_audit_entries": audit_entries,
            "jp_sentinel_unchanged": True,
        }, ensure_ascii=False, sort_keys=True))
        return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        run(args.output)
        return 0
    except Exception as exc:
        print(
            "US_LEDGER_GUI_REVIEW_HOLD: "
            + type(exc).__name__ + ": " + str(exc)[:500],
            file=sys.stderr,
        )
        raise


if __name__ == "__main__":
    raise SystemExit(main())
