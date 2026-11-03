"""Exact PR86 US Freelance Ledger unsigned Windows EXE + hosted CSV GUI evidence.

QA-only, no proposal/request/Identity fabrication and no Store/MSIX promotion.
The product is checked out at an immutable source commit separately from this harness.
Packaged EXE launch/restart and source-Tk button actions are distinct evidence levels.
"""
from __future__ import annotations

import argparse
import csv
import ctypes
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import zipfile
import zlib

PIN = "f9405fa12c2418f0ade943d0f41d02ccdc267d63"
SOURCE_BRANCH = "codex/us-freelance-csv-human-review-20261103"
SLUG = "us-freelance-ledger"
REPO = "shihuiarenjinba-png/AI-App-Factory"
MAPPING = ("Posted", "USD amount", "Flow", "CCY")


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def require(condition, reason):
    if not condition:
        raise RuntimeError(reason)


def git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args],
                                   text=True, encoding="utf-8").strip()


def source_contract(source):
    source = Path(source).resolve(strict=True)
    require(git(source, "rev-parse", "HEAD") == PIN,
            "STALE_OR_CHANGED_SOURCE: only exact PR86 product HEAD may be packaged")
    require(not git(source, "status", "--porcelain", "--untracked-files=all", "--",
                    "products/" + SLUG, "factory/config.json"),
            "CHANGED_SOURCE: product or factory config is dirty")
    product = source / "products" / SLUG
    manifest = product / "manifest.json"
    require(manifest.is_file() and not manifest.is_symlink(), "MISSING_MANIFEST")
    for name in ("main.py", "bank_csv_preview.py", "tests/test_smoke.py"):
        path = product / name
        require(path.is_file() and not path.is_symlink(), "MISSING_PRODUCT_SOURCE: " + name)
        git(source, "cat-file", "-e", "HEAD:products/" + SLUG + "/" + name)
    info = json.loads(manifest.read_text(encoding="utf-8"))
    require(info.get("slug") == SLUG and info.get("kind") == "app" and
            info.get("entry") == "main.py" and info.get("market") == "US" and
            info.get("currency") == "USD" and info.get("language") == "en-US",
            "WRONG_COUNTRY_OR_PRODUCT_MANIFEST")
    config = json.loads((source / "factory/config.json").read_text(encoding="utf-8"))
    require(config.get("kind") == "app", "WRONG_FACTORY_LANE")
    proposal = source / "proposals" / (SLUG + ".json")
    require(not proposal.exists(),
            "PROPOSAL_CHANGED: source contract changed; manual review required")
    return product, manifest


def package(source, output):
    require(sys.platform == "win32", "WINDOWS_HOST_REQUIRED")
    product, manifest = source_contract(source)
    output = Path(output).resolve(strict=True)
    exe = output / (SLUG + ".exe")
    require(exe.is_file() and not exe.is_symlink(), "MISSING_NEW_EXE")
    require(exe.stat().st_size > 1024 and exe.read_bytes()[:2] == b"MZ",
            "INVALID_WINDOWS_PE")
    receipt = {
        "schema_version": 1, "stage": "EXACT_SOURCE_UNSIGNED_EXE_QA",
        "status": "QA_ONLY_NOT_SALE_READY", "source_repository": REPO,
        "source_branch": SOURCE_BRANCH, "source_sha": PIN,
        "product_slug": SLUG, "country": "US", "currency": "USD",
        "manifest_sha256": digest(manifest),
        "bank_csv_preview_sha256": digest(product / "bank_csv_preview.py"),
        "executable": exe.name, "executable_sha256": digest(exe),
        "executable_bytes": exe.stat().st_size,
        "proposal_status": "ABSENT_NOT_INVENTED_QA_ONLY",
        "request_id": None, "request_status": "UNVERIFIED_NOT_USED",
        "identity_status": "NOT_USED", "store_status": "NOT_SUBMITTED",
        "msix_status": "NOT_BUILT",
        "previous_pr83_exe_sha256_forbidden":
            "20e625d9f6bed782bf68c1df83496fadf81812dea075baabe93ee1a73c7bdba2",
    }
    require(receipt["executable_sha256"] != receipt["previous_pr83_exe_sha256_forbidden"],
            "STALE_PR83_EXE_FORBIDDEN")
    receipt_file = output / "exe-receipt.json"
    require(not receipt_file.exists(), "EXISTING_RECEIPT_OVERWRITE_REFUSED")
    receipt_file.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    archive = output / "us-freelance-pr86-unsigned-exe-qa.zip"
    require(not archive.exists(), "EXISTING_ARCHIVE_OVERWRITE_REFUSED")
    members = [(exe, exe.name), (manifest, "manifest.json"),
               (receipt_file, "exe-receipt.json")]
    with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_DEFLATED) as bundle:
        for file, name in members:
            bundle.write(file, arcname=name)
    with zipfile.ZipFile(archive) as bundle:
        require(bundle.testzip() is None, "ZIP_CRC_FAILED")
        checked = []
        for file, name in members:
            raw = bundle.read(name)
            entry = bundle.getinfo(name)
            require(hashlib.sha256(raw).hexdigest() == digest(file), "ZIP_MEMBER_HASH_MISMATCH")
            require(entry.CRC == zlib.crc32(raw) & 0xffffffff, "ZIP_MEMBER_CRC_MISMATCH")
            checked.append({"name": name, "sha256": digest(file),
                            "bytes": len(raw), "crc32": f"{entry.CRC:08x}"})
    zip_receipt = {"source_sha": PIN, "zip_sha256": digest(archive),
                   "zip_bytes": archive.stat().st_size, "zip_crc": "PASS",
                   "members": checked}
    (output / "zip-receipt.json").write_text(
        json.dumps(zip_receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"exe": receipt["executable_sha256"],
                      "zip": zip_receipt["zip_sha256"], "source": PIN}))


def work_area():
    from ctypes import wintypes
    area = wintypes.RECT()
    require(ctypes.windll.user32.SystemParametersInfoW(
        48, 0, ctypes.byref(area), 0), "WINDOWS_WORK_AREA_UNAVAILABLE")
    return [area.left, area.top, area.right, area.bottom]


def find_window(pid):
    import psutil
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    try:
        pids = {pid} | {p.pid for p in psutil.Process(pid).children(recursive=True)}
    except psutil.Error:
        pids = {pid}
    matches = []
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def visit(hwnd, unused):
        owner = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value in pids and user32.IsWindowVisible(hwnd):
            title = ctypes.create_unicode_buffer(256)
            user32.GetWindowTextW(hwnd, title, len(title))
            if title.value == "Freelance Ledger US":
                bounds = wintypes.RECT()
                if user32.GetWindowRect(hwnd, ctypes.byref(bounds)):
                    matches.append((hwnd, [bounds.left, bounds.top,
                                           bounds.right, bounds.bottom]))
        return True

    user32.EnumWindows(callback_type(visit), 0)
    return matches[0] if matches else None


def packaged_launch(exe, appdata, output, label):
    from PIL import ImageGrab
    proc = subprocess.Popen([str(exe)], env={**os.environ, "APPDATA": str(appdata)},
                            cwd=str(output))
    found = None
    try:
        for _ in range(60):
            if proc.poll() is not None:
                raise RuntimeError("PACKAGED_EXE_EXITED_BEFORE_WINDOW")
            found = find_window(proc.pid)
            if found:
                break
            time.sleep(0.5)
        require(found is not None, "PACKAGED_EXE_VISIBLE_WINDOW_NOT_FOUND")
        hwnd, bounds = found
        area = work_area()
        require(bounds[0] >= area[0] and bounds[1] >= area[1] and
                bounds[2] <= area[2] and bounds[3] <= area[3],
                "PACKAGED_GUI_CLIPPED: " + str(bounds) + " vs " + str(area))
        image = ImageGrab.grab(bbox=tuple(bounds), all_screens=True)
        require(image.width > 300 and image.height > 250, "PACKAGED_SCREENSHOT_TOO_SMALL")
        filename = label + "-packaged.png"
        image.save(output / filename)
        dpi = ctypes.windll.user32.GetDpiForWindow(hwnd)
        return {"status": "PASS_PACKAGED_EXE_LAUNCH", "window": bounds,
                "work_area": area, "dpi_observed": dpi, "screenshot": filename}
    finally:
        found = find_window(proc.pid)
        if found:
            ctypes.windll.user32.PostMessageW(found[0], 0x0010, 0, 0)
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.terminate()
            proc.wait(timeout=10)


def buttons(parent):
    from tkinter import ttk
    result = {}
    def walk(widget):
        for child in widget.winfo_children():
            if isinstance(child, ttk.Button):
                result[child.cget("text")] = child
            walk(child)
    walk(parent)
    return result


def csv_flow(source, appdata, output):
    import tkinter as tk
    from tkinter import ttk
    from unittest.mock import patch
    from PIL import ImageGrab
    sys.path.insert(0, str(Path(source) / "products" / SLUG))
    import main as ui
    os.environ["APPDATA"] = str(appdata)
    csv_path = output / "statement-usd.csv"
    with csv_path.open("x", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(MAPPING)
        writer.writerow(["2026-10-12", "50.25", "credit", "USD"])
    bad_path = output / "statement-eur.csv"
    with bad_path.open("x", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(MAPPING)
        writer.writerow(["2026-10-12", "50.25", "credit", "EUR"])
    dup_path = output / "statement-duplicate.csv"
    with dup_path.open("x", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(MAPPING)
        writer.writerow(["2026-10-12", "50.25", "credit", "USD"])
        writer.writerow(["2026-10-12", "50.25", "credit", "USD"])
    target = output / "bank-csv-review.txt"
    restart_target = output / "bank-csv-review-after-restart.txt"
    chooser, save_targets, messages, errors = [], [], [], []

    def choose_file(*args, **kwargs):
        require(bool(chooser), "UNEXPECTED_OPEN_DIALOG")
        return str(chooser.pop(0))

    def save_file(*args, **kwargs):
        require(bool(save_targets), "UNEXPECTED_SAVE_DIALOG")
        return str(save_targets.pop(0))

    def show_info(title, message, *args, **kwargs):
        messages.append({"title": title, "text": message})

    def show_error(title, message, *args, **kwargs):
        errors.append({"title": title, "text": message})

    def fingerprint(app):
        return (tuple(app.store.conn.execute(
            "SELECT id,txn_date,kind,amount_cents FROM transactions ORDER BY id"
        ).fetchall()), app.store.conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0])

    def find_dialog(app):
        matches = [w for w in app.winfo_children()
                   if isinstance(w, tk.Toplevel) and "Bank CSV review" in w.title()]
        require(len(matches) == 1, "CSV_REVIEW_DIALOG_NOT_VISIBLE")
        return matches[0]

    def choose_and_review(app, dialog, file, expected):
        chooser.append(file)
        actions = buttons(dialog)
        actions["1. Choose CSV"].invoke()
        app.update()
        combos = []
        def visit(w):
            for child in w.winfo_children():
                if isinstance(child, ttk.Combobox):
                    combos.append(child)
                visit(child)
        visit(dialog)
        require(len(combos) == 4, "FOUR_EXPLICIT_MAPPING_FIELDS_MISSING")
        for combo, column in zip(combos, MAPPING):
            combo.set(column)
        actions["3. Preview candidates"].invoke()
        app.update()
        current_state = str(actions["4. Save review copy (.txt)"].cget("state"))
        require(current_state == ("normal" if expected else "disabled"),
                "INCORRECT_SAVE_STATE actual=" + repr(current_state) +
                " expected=" + repr(expected) + " dialogs=" + repr(errors[-3:]))
        return actions

    with patch.object(ui, "_work_area", return_value=(0, 0, 1024, 720)), \
         patch.object(ui.filedialog, "askopenfilename", side_effect=choose_file), \
         patch.object(ui.filedialog, "asksaveasfilename", side_effect=save_file), \
         patch.object(ui.messagebox, "showinfo", side_effect=show_info), \
         patch.object(ui.messagebox, "showwarning", side_effect=show_error), \
         patch.object(ui.messagebox, "showerror", side_effect=show_error):
        app = ui.App()
        try:
            app.update()
            primary = buttons(app)
            require("Preview bank CSV (no posting)" in primary, "CSV_PREVIEW_BUTTON_MISSING")
            for name in ("Preview bank CSV (no posting)", "Match selected",
                         "Check statement", "Undo checked", "Export bank check report"):
                control = primary[name]
                require(control.winfo_ismapped(), "HIDDEN_CONTROL: " + name)
                require(control.winfo_rootx() >= 0 and control.winfo_rooty() >= 0 and
                        control.winfo_rootx() + control.winfo_width() <= 1024 and
                        control.winfo_rooty() + control.winfo_height() <= 720,
                        "1024x720_CONTROL_CLIPPED: " + name)
            ImageGrab.grab(bbox=(0, 0, 1024, 720)).save(output / "tk-work-area-1024x720.png")
            app.v["date"].set("2026-10-12")
            app.v["kind"].set("income")
            app.v["amount"].set("50.25")
            app.v["category"].set("Business income")
            primary["Add transaction"].invoke()
            require(len(app.store.rows()) == 1, "FIXTURE_LEDGER_ENTRY_FAILED")
            before = fingerprint(app)
            primary["Preview bank CSV (no posting)"].invoke()
            app.update()
            dialog = find_dialog(app)
            actions = choose_and_review(app, dialog, csv_path, True)
            listing = [w for w in dialog.winfo_children() if isinstance(w, ttk.Treeview)]
            require(len(listing) == 1 and len(listing[0].get_children()) == 1,
                    "GUI_CANDIDATE_ROW_MISSING")
            values = listing[0].item(listing[0].get_children()[0], "values")
            require("CANDIDATE ONLY" in str(values) and "5025" in str(values),
                    "GUI_CANDIDATE_NOT_EXPLAINED")
            save_targets.append(target)
            actions["4. Save review copy (.txt)"].invoke()
            require(target.is_file() and "NOT POSTED" in target.read_text(encoding="utf-8"),
                    "REVIEW_COPY_NOT_SAVED")
            require(any(str(target) in m["text"] for m in messages),
                    "GUI_SAVED_PATH_NOT_SHOWN")
            require(fingerprint(app) == before, "LEDGER_CHANGED_DURING_CSV_PREVIEW")
            first_bytes = target.read_bytes()
            info_before = len(messages)
            save_targets.append(target)
            actions["4. Save review copy (.txt)"].invoke()
            require(target.read_bytes() == first_bytes and len(messages) == info_before and errors,
                    "OVERWRITE_OR_FALSE_SUCCESS")
            actions = choose_and_review(app, dialog, bad_path, False)
            require(len(messages) == info_before, "WRONG_CURRENCY_FALSE_SUCCESS")
            actions = choose_and_review(app, dialog, dup_path, True)
            duplicate_values = listing[0].item(listing[0].get_children()[-1], "values")
            require("DUPLICATE" in str(duplicate_values), "DUPLICATE_NOT_FLAGGED")
            first_duplicate = listing[0].item(listing[0].get_children()[0], "values")
            require("DUPLICATE" in str(first_duplicate), "FIRST_DUPLICATE_ROW_NOT_FLAGGED")
            require(fingerprint(app) == before, "LEDGER_CHANGED_BY_NEGATIVE_CASES")
            dialog.destroy()
        finally:
            app.close()

        app = ui.App()
        try:
            app.update()
            require(len(app.store.rows()) == 1, "RESTART_LOST_LEDGER")
            before = fingerprint(app)
            buttons(app)["Preview bank CSV (no posting)"].invoke()
            app.update()
            dialog = find_dialog(app)
            actions = choose_and_review(app, dialog, csv_path, True)
            save_targets.append(restart_target)
            actions["4. Save review copy (.txt)"].invoke()
            require(restart_target.is_file() and
                    "NOT POSTED" in restart_target.read_text(encoding="utf-8"),
                    "RESTART_REVIEW_COPY_MISSING")
            require(fingerprint(app) == before, "RESTART_LEDGER_CHANGED")
            dialog.destroy()
        finally:
            app.close()

    require(not chooser and not save_targets, "UNCONSUMED_FILE_DIALOG_INPUTS")
    return {"status": "PASS_SOURCE_TK_BUTTONS_NOT_PACKAGED_GUI_AUTOMATION",
            "source_sha": PIN, "initial_report_sha256": digest(target),
            "restart_report_sha256": digest(restart_target),
            "ledger_transactions": 1, "ledger_amount_cents": 5025,
            "wrong_currency_rejected": True, "duplicate_review_required": True,
            "overwrite_refused": True, "saved_path_disclosed": True,
            "human_qa": False, "physical_dpi_125_150": False,
            "warning_dialog_count": len(errors), "success_dialog_count": len(messages)}


def gui(source, output):
    source_contract(source)
    output = Path(output).resolve(strict=True)
    receipt = json.loads((output / "exe-receipt.json").read_text(encoding="utf-8"))
    exe = output / receipt["executable"]
    require(receipt["source_sha"] == PIN and digest(exe) == receipt["executable_sha256"],
            "EXE_SOURCE_RECEIPT_MISMATCH")
    require(receipt["executable_sha256"] != receipt["previous_pr83_exe_sha256_forbidden"],
            "STALE_PR83_EXE")
    require(receipt["executable_sha256"] != "756ff1437602bb40dcdf92c1f1e3daa57b0812d82b6ded3a24131425b6a45048",
            "STALE_PR85_EXE")
    appdata = output / "isolated-appdata"
    appdata.mkdir(exist_ok=False)
    evidence = {"source_sha": PIN, "exe_sha256": digest(exe),
                "human_qa": "NOT_PERFORMED", "physical_dpi_125_150": "NOT_PERFORMED",
                "steps": {}}
    try:
        evidence["steps"]["packaged_initial"] = packaged_launch(exe, appdata, output, "initial")
        evidence["steps"]["csv_tk_workflow"] = csv_flow(source, appdata, output)
        evidence["steps"]["packaged_restart"] = packaged_launch(exe, appdata, output, "restart")
        evidence["status"] = "PASS_HOSTED_EXE_LAUNCH_RESTART_AND_SOURCE_TK_CSV_FLOW"
    except Exception as exc:
        evidence["status"] = "GUI_HOLD"
        evidence["error"] = type(exc).__name__ + ": " + str(exc)[:400]
        raise
    finally:
        (output / "hosted-csv-gui-receipt.json").write_text(
            json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(evidence, sort_keys=True))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("package", "gui"))
    parser.add_argument("--source", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    if args.mode == "package":
        package(args.source, args.output)
    else:
        gui(args.source, args.output)
