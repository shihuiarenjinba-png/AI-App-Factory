"""Native Windows error-recovery QA for the pinned Focus Session Desk EXE.

This script does not rebuild or modify the product. It runs only against two
fresh APPDATA directories beneath RUNNER_TEMP and records native dialog,
state-file and process-exit evidence.
"""
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from pywinauto import Desktop
from pywinauto.keyboard import send_keys
from pywinauto.mouse import click

SOURCE_SHA = "fb6293839bc7b0bbff0a6d1d3c04e2f8f5942e79"
REQUEST_ID = "app-focus-session-desk-fb6293839bc7"
EXE_SHA256 = "d1ef4b389b1344e4886eb7728173508ea7754b795d476340dffd46f9024ddcda"
EXE_SIZE = 11477122
ARTIFACT_ID = "15083856249"
ARTIFACT_RUN_ID = "45746737287"
ARTIFACT_ZIP_SHA256 = "d3c36255a282d1912c6fe5e00efdbaad217433033226744fb61cf6e493c9f19d"
ARTIFACT_NAME = "focus-native-gui-exe-custody-45746737287"


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha256_file(path):
    return sha256_bytes(Path(path).read_bytes())


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def fixture_document():
    return {
        "schema": 1,
        "language": "en",
        "minutes": 25,
        "tasks": [
            {
                "id": "a" * 32,
                "title": "Recovery fixture task",
                "done": False,
            }
        ],
        "session": "idle",
    }


def verify_custody(exe):
    exe = Path(exe).resolve()
    if not exe.is_file():
        raise AssertionError(f"Missing artifact EXE: {exe}")
    if exe.name != "FocusSessionDesk.exe":
        raise AssertionError(f"Unexpected EXE name: {exe.name}")
    if exe.stat().st_size != EXE_SIZE or sha256_file(exe) != EXE_SHA256:
        raise AssertionError("Downloaded EXE bytes do not match the verified custody receipt")

    folder = exe.parent
    provenance = json.loads((folder / "provenance.json").read_text(encoding="utf-8-sig"))
    gui_receipt_path = folder / "receipt.json"
    gui_receipt = json.loads(gui_receipt_path.read_text(encoding="utf-8-sig"))
    if provenance.get("product_source_sha") != SOURCE_SHA:
        raise AssertionError("Artifact provenance product source SHA mismatch")
    if provenance.get("request_id") != REQUEST_ID:
        raise AssertionError("Artifact provenance request ID mismatch")
    if provenance.get("executable", {}).get("sha256") != EXE_SHA256:
        raise AssertionError("Artifact provenance EXE SHA mismatch")
    if provenance.get("executable", {}).get("size_bytes") != EXE_SIZE:
        raise AssertionError("Artifact provenance EXE size mismatch")
    if provenance.get("executable", {}).get("included_in_artifact") is not True:
        raise AssertionError("Artifact does not attest included EXE bytes")
    if sha256_file(gui_receipt_path) != provenance.get("gui_receipt_sha256"):
        raise AssertionError("Original GUI receipt SHA mismatch")
    if gui_receipt.get("source_sha") != SOURCE_SHA or gui_receipt.get("request_id") != REQUEST_ID:
        raise AssertionError("Original GUI receipt source/request mismatch")
    if gui_receipt.get("exe_sha256") != EXE_SHA256 or gui_receipt.get("exe_size_bytes") != EXE_SIZE:
        raise AssertionError("Original GUI receipt EXE mismatch")
    for name, expected in (
        ("exe-sha256.txt", EXE_SHA256),
        ("source-sha.txt", SOURCE_SHA),
        ("request-id.txt", REQUEST_ID),
    ):
        if (folder / name).read_text(encoding="utf-8-sig").strip() != expected:
            raise AssertionError(f"Artifact custody sidecar mismatch: {name}")
    return {
        "artifact_id": ARTIFACT_ID,
        "artifact_run_id": ARTIFACT_RUN_ID,
        "artifact_name": ARTIFACT_NAME,
        "artifact_zip_sha256": ARTIFACT_ZIP_SHA256,
        "product_source_sha": SOURCE_SHA,
        "request_id": REQUEST_ID,
        "exe_sha256": EXE_SHA256,
        "exe_size_bytes": EXE_SIZE,
        "original_gui_receipt_sha256": provenance["gui_receipt_sha256"],
    }


def make_appdata(runner_temp, label):
    root = Path(tempfile.mkdtemp(prefix=f"focus-{label}-", dir=runner_temp)).resolve()
    (root / "FocusSessionDesk").mkdir()
    return root


def wait_main_window(timeout=35):
    window = Desktop(backend="uia").window(title_re=r".*Focus Session Desk.*")
    window.wait("visible", timeout=timeout)
    window.set_focus()
    return window


def wait_native_dialog(title, expected_text, timeout=25):
    dialog = Desktop(backend="win32").window(title=title, class_name="#32770")
    dialog.wait("visible", timeout=timeout)
    texts = [control.window_text() for control in dialog.descendants()]
    combined = "\n".join(text for text in texts if text)
    if expected_text not in combined:
        raise AssertionError(
            f"Native dialog text mismatch. Expected {expected_text!r}; observed {combined!r}"
        )
    return dialog, combined


def dismiss_ok(dialog):
    button = dialog.child_window(title="OK", class_name="Button")
    button.wait("visible", timeout=8)
    button.click_input()


def wait_json(path, expected, timeout=12):
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        try:
            last = json.loads(Path(path).read_text(encoding="utf-8"))
            if last == expected:
                return last
        except (OSError, ValueError, UnicodeError):
            pass
        time.sleep(0.15)
    raise AssertionError(f"State did not reach expected value: {last!r}")


def file_inventory(root):
    return sorted(
        str(path.relative_to(root)).replace("\\", "/")
        for path in Path(root).rglob("*")
        if path.is_file()
    )


def close_process(window, proc):
    if proc.poll() is None:
        try:
            window.close()
        except Exception:
            pass
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            subprocess.run(
                ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                capture_output=True,
                text=True,
                check=False,
            )
            proc.wait(timeout=10)
    if proc.returncode != 0:
        raise AssertionError(f"Focus Session Desk exited with {proc.returncode}")


def run_recovery_case(exe, runner_temp, out):
    appdata = make_appdata(runner_temp, "valid-backup")
    state_dir = appdata / "FocusSessionDesk"
    state_path = state_dir / "state.json"
    backup_path = state_dir / "state.json.bak"
    backup_document = fixture_document()
    backup_bytes = json_bytes(backup_document)
    corrupted_bytes = b"{ this is deliberately corrupted primary JSON\n"
    backup_path.write_bytes(backup_bytes)
    state_path.write_bytes(corrupted_bytes)
    backup_sha_before = sha256_file(backup_path)
    primary_sha_before = sha256_file(state_path)

    env = os.environ.copy()
    env["APPDATA"] = str(appdata)
    proc = subprocess.Popen([str(exe)], cwd=str(exe.parent), env=env)
    window = None
    try:
        dialog, dialog_text = wait_native_dialog(
            "Focus Session Desk", "Recovered from backup. Review the restored data."
        )
        dialog.capture_as_image().save(out / "01-recovery-notice.png")
        dismiss_ok(dialog)

        window = wait_main_window()
        wait_json(state_path, backup_document)
        restored_bytes = state_path.read_bytes()
        if restored_bytes != backup_bytes:
            raise AssertionError("Restored primary bytes differ from the valid backup")
        if sha256_file(backup_path) != backup_sha_before:
            raise AssertionError("Recovery modified the retained valid backup")
        window.capture_as_image().save(out / "02-recovered-main-window.png")

        close_process(window, proc)
        window = None
        inventory = file_inventory(appdata)
        expected_inventory = [
            "FocusSessionDesk/state.json",
            "FocusSessionDesk/state.json.bak",
        ]
        if inventory != expected_inventory:
            raise AssertionError(f"Unexpected disposable APPDATA files: {inventory!r}")
        return {
            "case": "corrupt_primary_valid_backup",
            "result": "PASS",
            "appdata_scope": "fresh RUNNER_TEMP directory only",
            "primary_sha256_before_launch": primary_sha_before,
            "backup_sha256_before_launch": backup_sha_before,
            "backup_sha256_after_exit": sha256_file(backup_path),
            "restored_primary_sha256": sha256_file(state_path),
            "restored_state_equals_backup_bytes": restored_bytes == backup_bytes,
            "restored_document": json.loads(state_path.read_text(encoding="utf-8")),
            "native_dialog_title": "Focus Session Desk",
            "native_dialog_text": dialog_text,
            "recovery_notice_visible": True,
            "screenshots": [
                "01-recovery-notice.png",
                "02-recovered-main-window.png",
            ],
            "appdata_file_inventory": inventory,
            "process_exit_code": proc.returncode,
        }
    finally:
        if proc.poll() is None:
            close_process(window, proc)


def timer_button_rectangles(window):
    win = window.rectangle()
    candidates = []
    for control in window.descendants(control_type="Pane"):
        rect = control.rectangle()
        if (
            60 <= rect.width() <= 100
            and 15 <= rect.height() <= 40
            and win.top + 0.32 * win.height() < rect.top < win.top + 0.40 * win.height()
        ):
            candidates.append(rect)
    return sorted(candidates, key=lambda rect: rect.left)


def run_invalid_duration_case(exe, runner_temp, out):
    appdata = make_appdata(runner_temp, "invalid-duration")
    state_dir = appdata / "FocusSessionDesk"
    state_path = state_dir / "state.json"
    backup_path = state_dir / "state.json.bak"
    expected_document = fixture_document()
    initial_bytes = json_bytes(expected_document)
    state_path.write_bytes(initial_bytes)

    env = os.environ.copy()
    env["APPDATA"] = str(appdata)
    proc = subprocess.Popen([str(exe)], cwd=str(exe.parent), env=env)
    window = None
    try:
        window = wait_main_window()
        wait_json(state_path, expected_document)
        baseline_bytes = state_path.read_bytes()
        baseline_sha = sha256_bytes(baseline_bytes)
        backup_before_action = backup_path.read_bytes()
        backup_sha_before_action = sha256_bytes(backup_before_action)

        # Tk/ttk Entry widgets are exposed as unnamed Pane peers on this
        # hosted runner, not UIA Edit controls. Resolve the small duration
        # Entry by its measured position in the timer row, then click it.
        win = window.rectangle()
        entry_candidates = []
        for control in window.descendants(control_type="Pane"):
            rect = control.rectangle()
            if (
                25 <= rect.width() <= 65
                and 15 <= rect.height() <= 40
                and win.top + 0.28 * win.height() < rect.top < win.top + 0.40 * win.height()
                and rect.left < win.left + 0.48 * win.width()
            ):
                entry_candidates.append(rect)
        if len(entry_candidates) != 1:
            raise AssertionError(
                "Expected one measured duration Entry Pane; observed "
                + repr([[r.left, r.top, r.right, r.bottom] for r in entry_candidates])
            )
        duration_entry = entry_candidates[0]
        duration_entry_xy = (
            (duration_entry.left + duration_entry.right) // 2,
            (duration_entry.top + duration_entry.bottom) // 2,
        )
        click(coords=duration_entry_xy)
        send_keys("^a0", pause=0.08)
        receipt_duration_entry_rect = [
            duration_entry.left, duration_entry.top, duration_entry.right, duration_entry.bottom
        ]
        window.capture_as_image().save(out / "03-invalid-duration-entered.png")

        buttons = timer_button_rectangles(window)
        if len(buttons) != 4:
            raise AssertionError(
                "Expected duration/start/pause/reset native controls; observed "
                + repr([[r.left, r.top, r.right, r.bottom] for r in buttons])
            )
        duration_button = buttons[0]
        click(coords=((duration_button.left + duration_button.right) // 2,
                      (duration_button.top + duration_button.bottom) // 2))

        dialog, dialog_text = wait_native_dialog(
            "Action failed", "Focus duration must be 1-180 minutes"
        )
        dialog.capture_as_image().save(out / "04-invalid-duration-error.png")
        after_error_bytes = state_path.read_bytes()
        if after_error_bytes != baseline_bytes:
            raise AssertionError("Invalid duration changed the persisted state before dialog dismissal")
        if json.loads(after_error_bytes) != expected_document:
            raise AssertionError("Invalid duration changed the prior saved duration or task state")
        if sha256_file(backup_path) != backup_sha_before_action:
            raise AssertionError("Invalid duration changed the backup before dialog dismissal")

        dismiss_ok(dialog)
        window.capture_as_image().save(out / "05-invalid-duration-main-window.png")
        close_process(window, proc)
        window = None

        after_exit_bytes = state_path.read_bytes()
        if after_exit_bytes != baseline_bytes:
            raise AssertionError("Closing after invalid duration changed the prior state bytes")
        if sha256_file(state_path) != baseline_sha:
            raise AssertionError("Prior state SHA changed after invalid duration")
        if json.loads(after_exit_bytes) != expected_document:
            raise AssertionError("Prior duration/task state did not survive invalid input")
        inventory = file_inventory(appdata)
        expected_inventory = [
            "FocusSessionDesk/state.json",
            "FocusSessionDesk/state.json.bak",
        ]
        if inventory != expected_inventory:
            raise AssertionError(f"Unexpected disposable APPDATA files: {inventory!r}")
        return {
            "case": "invalid_duration_zero",
            "result": "PASS",
            "appdata_scope": "fresh RUNNER_TEMP directory only",
            "invalid_input": "0",
            "duration_entry_rectangle": receipt_duration_entry_rect,
            "native_dialog_title": "Action failed",
            "native_dialog_text": dialog_text,
            "controlled_error_visible": True,
            "state_sha256_before_action": baseline_sha,
            "state_sha256_after_error": sha256_bytes(after_error_bytes),
            "state_sha256_after_exit": sha256_file(state_path),
            "state_unchanged_before_dialog_dismissal": after_error_bytes == baseline_bytes,
            "state_unchanged_after_exit": after_exit_bytes == baseline_bytes,
            "prior_minutes_after_error": json.loads(after_exit_bytes)["minutes"],
            "prior_task_count_after_error": len(json.loads(after_exit_bytes)["tasks"]),
            "backup_sha256_before_action": backup_sha_before_action,
            "backup_sha256_after_exit": sha256_file(backup_path),
            "screenshots": [
                "03-invalid-duration-entered.png",
                "04-invalid-duration-error.png",
                "05-invalid-duration-main-window.png",
            ],
            "appdata_file_inventory": inventory,
            "process_exit_code": proc.returncode,
        }
    finally:
        if proc.poll() is None:
            close_process(window, proc)


def main():
    if len(sys.argv) != 3:
        raise SystemExit("usage: windows_exe_error_recovery_smoke.py EXE OUTPUT_DIR")
    exe = Path(sys.argv[1]).resolve()
    out = Path(sys.argv[2]).resolve()
    out.mkdir(parents=True, exist_ok=True)

    expected_qa_head = os.environ["EXPECTED_QA_HEAD_SHA"]
    source_sha = os.environ["EXPECTED_PRODUCT_SOURCE_SHA"]
    request_id = os.environ["EXPECTED_REQUEST_ID"]
    if source_sha != SOURCE_SHA or request_id != REQUEST_ID:
        raise AssertionError("Workflow source/request binding mismatch")
    if os.environ.get("EXPECTED_EXE_SHA256") != EXE_SHA256:
        raise AssertionError("Workflow EXE SHA binding mismatch")
    custody = verify_custody(exe)

    runner_temp = Path(os.environ["RUNNER_TEMP"]).resolve()
    recovery = run_recovery_case(exe, runner_temp, out)
    invalid = run_invalid_duration_case(exe, runner_temp, out)
    receipt = {
        "schema_version": 1,
        "product": "focus-session-desk",
        "result": "PASS",
        "product_source_sha": source_sha,
        "qa_head_sha": expected_qa_head,
        "request_id": request_id,
        "exe_sha256": EXE_SHA256,
        "exe_size_bytes": EXE_SIZE,
        "artifact_custody": custody,
        "user_data_safety": {
            "appdata_overridden_for_each_process": True,
            "both_scenarios_used_fresh_runner_temp_directories": True,
            "no_user_appdata_or_product_source_files_written": True,
        },
        "scenarios": [recovery, invalid],
    }
    (out / "error-recovery-receipt.json").write_bytes(json_bytes(receipt))
    print(json.dumps(receipt, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
