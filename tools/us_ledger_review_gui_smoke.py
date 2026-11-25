"""Real Windows Tk GUI smoke for the US ledger REVIEW REQUIRED gate.

This runs the committed Python source on a Windows desktop session. It does
not claim a native EXE, signed package, Store identity, or tax advice.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import time
from typing import Any

from PIL import ImageGrab
from pywinauto import Desktop, mouse
from pywinauto.keyboard import send_keys

ROOT = Path(__file__).resolve().parents[1]
PRODUCT = ROOT / "products" / "us-freelance-ledger"
MAIN = PRODUCT / "main.py"
REVIEW_TITLE = "REVIEW REQUIRED — US tax calculation"
CALC_TITLE = "Tax / fixed assets"
RESULT_TITLE = "REVIEW REQUIRED — Sales tax"
BUTTON_TITLE = "US tax / fixed assets — REVIEW REQUIRED"

REQUEST = {
    "calculation": "sales tax",
    "amount_usd": "100.00",
    "jurisdiction_rate_percent": "8.0",
    "jurisdiction": "Fixture jurisdiction",
    "expected_tax_usd": "8.00",
    "expected_gross_usd": "108.00",
}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def wait_window(title: str, timeout: float = 20.0):
    spec = Desktop(backend="win32").window(title=title)
    spec.wait("exists visible", timeout=timeout)
    return spec


def wait_window_closed(window, timeout: float = 10.0) -> None:
    window.wait_not("exists", timeout=timeout)


def wait_title_absent(title: str, timeout: float = 3.0) -> bool:
    deadline = time.monotonic() + timeout
    desktop = Desktop(backend="win32")
    while time.monotonic() < deadline:
        visible = []
        for window in desktop.windows():
            try:
                if window.is_visible() and window.window_text() == title:
                    visible.append(window)
            except Exception:
                continue
        if not visible:
            return True
        time.sleep(0.1)
    return False


def visible_windows() -> list[dict[str, Any]]:
    rows = []
    for window in Desktop(backend="win32").windows():
        try:
            if window.is_visible():
                rect = window.rectangle()
                rows.append({
                    "title": window.window_text(),
                    "class_name": window.class_name(),
                    "rect": [rect.left, rect.top, rect.right, rect.bottom],
                })
        except Exception:
            continue
    return rows


def control_text(window) -> str:
    values = [window.window_text()]
    try:
        for child in window.children():
            value = child.window_text()
            if value:
                values.append(value)
    except Exception:
        pass
    return "\n".join(value for value in values if value)


def capture(output: Path, name: str) -> Path:
    path = output / "screenshots" / f"{name}.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    ImageGrab.grab().save(path)
    return path


def click_message_button(dialog, label: str) -> None:
    button = dialog.child_window(title=label, class_name="Button")
    button.wait("exists enabled", timeout=8)
    button.click_input()


def click_tax_button(main) -> str:
    main.set_focus()
    try:
        uia_main = Desktop(backend="uia").window(handle=main.handle)
        button = uia_main.child_window(title=BUTTON_TITLE, control_type="Button")
        if button.exists(timeout=2):
            button.click_input()
            return "uia-button"
    except Exception:
        pass

    # Tk's Windows accessibility tree can omit child labels on hosted runners.
    # The main window uses the same fixed left-column button order as the
    # committed UI; this point is the tax-review button shown in the GUI proof.
    rect = main.rectangle()
    point = (rect.left + 125, rect.top + 496)
    mouse.click(button="left", coords=point)
    return f"win32-screen-coordinate:{point[0]},{point[1]}"


def enter_tk_prompt(title: str, value: str) -> None:
    dialog = wait_window(title, timeout=12)
    dialog.set_focus()
    send_keys(value, with_spaces=True)
    send_keys("{ENTER}")
    wait_window_closed(dialog, timeout=10)


def create_jp_sentinel(appdata: Path) -> tuple[Path, bytes]:
    jp_dir = appdata / "JPFreelanceLedger"
    jp_dir.mkdir(parents=True, exist_ok=True)
    db_path = jp_dir / "books.sqlite3"
    connection = sqlite3.connect(db_path)
    try:
        connection.execute("CREATE TABLE sentinel (value TEXT NOT NULL)")
        connection.execute("INSERT INTO sentinel VALUES ('JP-KEEP')")
        connection.commit()
    finally:
        connection.close()
    return db_path, db_path.read_bytes()


def transaction_count(db_path: Path) -> int:
    connection = sqlite3.connect(db_path)
    try:
        return int(connection.execute("SELECT COUNT(*) FROM transactions").fetchone()[0])
    finally:
        connection.close()


def launch_app(appdata: Path, log_path: Path):
    env = os.environ.copy()
    env["APPDATA"] = str(appdata)
    env["PYTHONIOENCODING"] = "utf-8"
    log = log_path.open("w", encoding="utf-8")
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    process = subprocess.Popen(
        [sys.executable, str(MAIN)],
        cwd=str(PRODUCT),
        env=env,
        stdout=log,
        stderr=subprocess.STDOUT,
        creationflags=creationflags,
    )
    return process, log


def close_app(main, process, log) -> None:
    try:
        main.close()
    except Exception:
        pass
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
    log.close()


def run_approved(output: Path) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="us-ledger-gui-approve-") as tmp:
        appdata = Path(tmp)
        jp_db, jp_before_bytes = create_jp_sentinel(appdata)
        jp_before = sha256_bytes(jp_before_bytes)
        log_path = output / "approve-app.log"
        process, log = launch_app(appdata, log_path)
        main = None
        try:
            main = wait_window("Freelance Ledger US", timeout=30)
            capture(output, "approve-main-window")
            db_path = appdata / "USFreelanceLedger" / "books.sqlite3"
            ledger_before = sha256_file(db_path)

            click_method = click_tax_button(main)
            review = wait_window(REVIEW_TITLE, timeout=12)
            review_text = control_text(review)
            for phrase in (
                "United States (USD) only",
                "NOT a tax return or filing",
                "tax year",
                "IRS publication",
                "No tax amounts are posted automatically",
            ):
                if phrase not in review_text:
                    raise AssertionError(f"review dialog omitted novice warning: {phrase!r}")
            capture(output, "approve-review-required-prompt")
            click_message_button(review, "Yes")
            wait_window_closed(review, timeout=8)

            enter_tk_prompt(CALC_TITLE, REQUEST["calculation"])
            enter_tk_prompt("Sales tax", REQUEST["amount_usd"])
            enter_tk_prompt("Sales tax", REQUEST["jurisdiction_rate_percent"])
            enter_tk_prompt("Sales tax", REQUEST["jurisdiction"])

            result = wait_window(RESULT_TITLE, timeout=12)
            result_text = control_text(result)
            for phrase in (
                "Fixture jurisdiction",
                "Tax USD 8.00",
                "Gross USD 108.00",
                "Arithmetic only",
                "nexus/taxability is not determined",
                "No posting",
            ):
                if phrase not in result_text:
                    raise AssertionError(f"sales-tax result omitted expected text: {phrase!r}")
            capture(output, "approve-sales-tax-result")
            click_message_button(result, "OK")
            wait_window_closed(result, timeout=8)

            ledger_after = sha256_file(db_path)
            count = transaction_count(db_path)
            jp_after_bytes = jp_db.read_bytes()
            if ledger_after != ledger_before:
                raise AssertionError("approved review changed the US ledger database bytes")
            if count != 0:
                raise AssertionError(f"approved review unexpectedly wrote {count} ledger rows")
            if jp_after_bytes != jp_before_bytes:
                raise AssertionError("approved review changed the JP sentinel database")
            return {
                "status": "PASS",
                "click_method": click_method,
                "review_dialog_title": REVIEW_TITLE,
                "result_dialog_title": RESULT_TITLE,
                "result_text": result_text,
                "tax_usd": "8.00",
                "gross_usd": "108.00",
                "ledger_sha256_before": ledger_before,
                "ledger_sha256_after": ledger_after,
                "transaction_count": count,
                "jp_sentinel_sha256_before": jp_before,
                "jp_sentinel_sha256_after": sha256_bytes(jp_after_bytes),
            }
        except Exception:
            capture(output, "approve-failure-screen")
            raise
        finally:
            if main is not None:
                close_app(main, process, log)
            else:
                if process.poll() is None:
                    process.terminate()
                log.close()


def run_declined(output: Path) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="us-ledger-gui-decline-") as tmp:
        appdata = Path(tmp)
        jp_db, jp_before_bytes = create_jp_sentinel(appdata)
        jp_before = sha256_bytes(jp_before_bytes)
        log_path = output / "decline-app.log"
        process, log = launch_app(appdata, log_path)
        main = None
        try:
            main = wait_window("Freelance Ledger US", timeout=30)
            capture(output, "decline-main-window")
            db_path = appdata / "USFreelanceLedger" / "books.sqlite3"
            ledger_before = sha256_file(db_path)

            click_method = click_tax_button(main)
            review = wait_window(REVIEW_TITLE, timeout=12)
            review_text = control_text(review)
            if "No tax amounts are posted automatically" not in review_text:
                raise AssertionError("decline prompt did not show the no-posting warning")
            capture(output, "decline-review-required-prompt")
            click_message_button(review, "No")
            wait_window_closed(review, timeout=8)

            if not wait_title_absent(CALC_TITLE, timeout=3):
                raise AssertionError("declining review still opened the calculator")
            capture(output, "decline-returned-to-main")

            ledger_after = sha256_file(db_path)
            count = transaction_count(db_path)
            jp_after_bytes = jp_db.read_bytes()
            if ledger_after != ledger_before:
                raise AssertionError("declining review changed the US ledger database bytes")
            if count != 0:
                raise AssertionError(f"declining review unexpectedly wrote {count} ledger rows")
            if jp_after_bytes != jp_before_bytes:
                raise AssertionError("declining review changed the JP sentinel database")
            return {
                "status": "PASS",
                "click_method": click_method,
                "review_dialog_title": REVIEW_TITLE,
                "calculator_opened": False,
                "ledger_sha256_before": ledger_before,
                "ledger_sha256_after": ledger_after,
                "transaction_count": count,
                "jp_sentinel_sha256_before": jp_before,
                "jp_sentinel_sha256_after": sha256_bytes(jp_after_bytes),
            }
        except Exception:
            capture(output, "decline-failure-screen")
            raise
        finally:
            if main is not None:
                close_app(main, process, log)
            else:
                if process.poll() is None:
                    process.terminate()
                log.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if sys.platform != "win32":
        raise SystemExit("Windows desktop session required")
    if not MAIN.is_file():
        raise SystemExit(f"US ledger source missing: {MAIN}")
    if args.output.exists():
        raise SystemExit(f"refusing to overwrite evidence directory: {args.output}")
    args.output.mkdir(parents=True)

    source_sha = os.environ.get("SOURCE_SHA") or os.environ.get("GITHUB_SHA", "")
    source_ref = os.environ.get("SOURCE_REF") or os.environ.get("GITHUB_REF", "")
    if len(source_sha) != 40 or not source_ref.startswith("refs/heads/codex/"):
        raise SystemExit("exact codex source SHA/ref required")

    request_bytes = json.dumps(REQUEST, sort_keys=True, separators=(",", ":")).encode("utf-8")
    receipt = {
        "schema_version": 1,
        "status": "RUNNING",
        "source_repository": "shihuiarenjinba-png/AI-App-Factory",
        "source_ref": source_ref,
        "source_sha": source_sha,
        "source_mode": "python-source-windows-gui",
        "native_exe_built": False,
        "executable_sha256": None,
        "source_file_sha256": {
            "main.py": sha256_file(MAIN),
            "core.py": sha256_file(PRODUCT / "core.py"),
            "tax_assets.py": sha256_file(PRODUCT / "tax_assets.py"),
        },
        "request_id": f"us-ledger-review-gui:{source_sha}",
        "request_sha256": sha256_bytes(request_bytes),
        "request": REQUEST,
    }
    try:
        receipt["approve_path"] = run_approved(args.output)
        receipt["decline_path"] = run_declined(args.output)
        receipt["status"] = "PASS"
    except Exception as exc:
        receipt["status"] = "FAIL"
        receipt["error"] = f"{type(exc).__name__}: {str(exc)[:500]}"
        receipt["visible_windows_on_failure"] = visible_windows()
        (args.output / "gui-receipt.json").write_text(
            json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        raise
    receipt["screenshots"] = {
        path.name: sha256_file(path)
        for path in sorted((args.output / "screenshots").glob("*.png"))
    }
    (args.output / "gui-receipt.json").write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    receipt_path = args.output / "gui-receipt.json"
    print(json.dumps({
        "status": receipt["status"],
        "source_sha": source_sha,
        "request_sha256": receipt["request_sha256"],
        "receipt_sha256": sha256_file(receipt_path),
        "approve": receipt["approve_path"]["status"],
        "decline": receipt["decline_path"]["status"],
        "screenshots": list(receipt["screenshots"]),
    }, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
