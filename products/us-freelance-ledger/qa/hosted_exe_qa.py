"""Hosted Windows QA for an exact, unmodified US Freelance Ledger source SHA.

Two distinct evidence levels: packaged PE window launch/restart, and actual Tk
button invocation against the same pinned source. NOT human or physical-DPI QA.
"""
import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import zipfile
import zlib

PINNED = "97beffedec6f5657a4c3a66439e90ce68637ba53"
SOURCE_BRANCH = "codex/us-freelance-taskbar-bounds-20261103"
SLUG = "us-freelance-ledger"


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def package(source, output):
    source, output = Path(source).resolve(), Path(output).resolve()
    exe = output / (SLUG + ".exe")
    manifest = source / "products" / SLUG / "manifest.json"
    if not exe.is_file() or not manifest.is_file() or exe.open("rb").read(2) != b"MZ":
        raise RuntimeError("No valid exact-source Windows PE or manifest")
    git_sha = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip()
    if git_sha != PINNED:
        raise RuntimeError("Source checkout does not match pinned PR82 HEAD")
    dirty = subprocess.check_output(["git", "-C", str(source), "status", "--porcelain",
                                     "--", "products/" + SLUG], text=True).strip()
    if dirty:
        raise RuntimeError("Source product is not clean")
    info = json.loads(manifest.read_text(encoding="utf-8"))
    if info.get("slug") != SLUG or info.get("market") != "US" or info.get("entry") != "main.py":
        raise RuntimeError("Unexpected US product manifest")
    receipt = {
        "schema_version": 1, "status": "UNSIGNED_EXE_QA_ONLY",
        "source_repository": "shihuiarenjinba-png/AI-App-Factory",
        "source_branch": SOURCE_BRANCH, "source_sha": PINNED,
        "request_id": None, "request_status": "NOT_VERIFIED_NO_BINDING",
        "identity_status": "NOT_USED", "msix_status": "NOT_BUILT",
        "slug": SLUG, "executable": exe.name,
        "executable_sha256": sha256(exe), "executable_bytes": exe.stat().st_size,
        "source_manifest_sha256": sha256(manifest),
    }
    (output / "exe-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    archive = output / "us-freelance-ledger-unsigned-qa.zip"
    members = [(exe, exe.name), (manifest, "manifest.json"),
               (output / "exe-receipt.json", "exe-receipt.json")]
    with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_DEFLATED,
                         compresslevel=6, allowZip64=True) as bundle:
        for path, name in members:
            bundle.write(path, arcname=name)
    with zipfile.ZipFile(archive) as bundle:
        if bundle.testzip() is not None:
            raise RuntimeError("ZIP CRC verification failed")
        verified = []
        for path, name in members:
            data = bundle.read(name)
            if hashlib.sha256(data).hexdigest() != sha256(path):
                raise RuntimeError("ZIP member changed: " + name)
            entry = bundle.getinfo(name)
            if entry.CRC != (zlib.crc32(data) & 0xffffffff):
                raise RuntimeError("ZIP CRC mismatch: " + name)
            verified.append({"name": name, "size": len(data),
                             "crc32": f"{entry.CRC:08x}", "sha256": sha256(path)})
    (output / "zip-validation.json").write_text(json.dumps({
        "zip_sha256": sha256(archive), "zip_bytes": archive.stat().st_size,
        "members": verified, "crc_status": "PASS", "source_sha": PINNED
    }, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt, sort_keys=True))


def windows():
    if sys.platform != "win32":
        raise RuntimeError("Real Windows host required")
    return ctypes.windll.user32


def get_work_area():
    from ctypes import wintypes
    rect = wintypes.RECT()
    if not windows().SystemParametersInfoW(48, 0, ctypes.byref(rect), 0):
        raise RuntimeError("Windows work area could not be measured")
    return [rect.left, rect.top, rect.right, rect.bottom]


def find_window(pid):
    from ctypes import wintypes
    found = []
    import psutil
    try:
        accepted = {pid} | {child.pid for child in psutil.Process(pid).children(recursive=True)}
    except psutil.Error:
        accepted = {pid}
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def callback(hwnd, unused):
        owner = wintypes.DWORD()
        windows().GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value in accepted and windows().IsWindowVisible(hwnd):
            title = ctypes.create_unicode_buffer(256)
            windows().GetWindowTextW(hwnd, title, len(title))
            if "Freelance Ledger US" in title.value:
                rect = wintypes.RECT()
                if windows().GetWindowRect(hwnd, ctypes.byref(rect)):
                    found.append((hwnd, [rect.left, rect.top, rect.right, rect.bottom]))
        return True
    cb = callback_type(callback)
    windows().EnumWindows(cb, 0)
    return found[0] if found else None


def launch_exe(exe, appdata, output, label):
    from PIL import ImageGrab
    env = dict(os.environ, APPDATA=str(appdata))
    proc = subprocess.Popen([str(exe)], cwd=str(output), env=env)
    try:
        match = None
        for _ in range(40):
            if proc.poll() is not None:
                raise RuntimeError("Packaged EXE exited before GUI was visible")
            match = find_window(proc.pid)
            if match:
                break
            time.sleep(0.5)
        if not match:
            return {"status": "HOLD_NO_VISIBLE_PACKAGED_WINDOW",
                    "process_alive": proc.poll() is None,
                    "reason": "Hosted runner desktop or packaged child window not observable"}
        hwnd, bounds = match
        if bounds[2] <= bounds[0] or bounds[3] <= bounds[1]:
            raise RuntimeError("Invalid EXE window geometry")
        shot = ImageGrab.grab(bbox=tuple(bounds), all_screens=True)
        if shot.width < 300 or shot.height < 250:
            raise RuntimeError("Packaged GUI screenshot too small")
        shot.save(output / (label + "-packaged.png"))
        area = get_work_area()
        if (bounds[0] < area[0] or bounds[1] < area[1] or
                bounds[2] > area[2] or bounds[3] > area[3]):
            raise RuntimeError("Packaged window clipped by Windows work area: "
                               + str(bounds) + " vs " + str(area))
        dpi = None
        try:
            dpi = windows().GetDpiForWindow(hwnd)
        except (AttributeError, OSError):
            pass
        return {"visible": True, "window_bounds": bounds, "window_dpi": dpi,
                "screenshot": label + "-packaged.png"}
    finally:
        match = find_window(proc.pid)
        if match:
            windows().PostMessageW(match[0], 0x0010, 0, 0)
        try:
            proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            proc.terminate()
            proc.wait(timeout=8)


def tk_buttons(app):
    from tkinter import ttk
    found = {}
    def visit(parent):
        for widget in parent.winfo_children():
            if isinstance(widget, ttk.Button):
                found[widget.cget("text")] = widget
            visit(widget)
    visit(app)
    return found


def tk_workflow(source, appdata, output):
    from unittest.mock import patch
    from PIL import ImageGrab
    product = Path(source) / "products" / SLUG
    sys.path.insert(0, str(product))
    import main as ledger_ui
    from bank_reconcile import match_statuses, statement_preview
    os.environ["APPDATA"] = str(appdata)
    messages, errors = [], []
    prompts = []
    destinations = []
    def askstring(*args, **kwargs):
        if not prompts:
            raise RuntimeError("Unexpected GUI prompt: " + str(args))
        return prompts.pop(0)
    def askfile(*args, **kwargs):
        if not destinations:
            raise RuntimeError("Unexpected file chooser")
        return str(destinations.pop(0))
    def info(title, message, *args, **kwargs):
        messages.append({"title": title, "text": message})
    def error(title, message, *args, **kwargs):
        errors.append({"title": title, "text": message})
    with patch.object(ledger_ui.simpledialog, "askstring", side_effect=askstring), \
         patch.object(ledger_ui.filedialog, "asksaveasfilename", side_effect=askfile), \
         patch.object(ledger_ui.messagebox, "askyesno", return_value=True), \
         patch.object(ledger_ui.messagebox, "showinfo", side_effect=info), \
         patch.object(ledger_ui.messagebox, "showerror", side_effect=error), \
         patch.object(ledger_ui.messagebox, "showwarning", side_effect=error):
        app = ledger_ui.App()
        try:
            app.geometry("1000x696+12+12")
            app.update()
            required = ["Match selected", "Check statement", "Undo checked",
                        "Export bank check report", "Add transaction"]
            buttons = tk_buttons(app)
            if any(label not in buttons for label in required):
                raise RuntimeError("Missing key Tk controls")
            visible = {}
            for label in required:
                widget = buttons[label]
                if not widget.winfo_ismapped():
                    raise RuntimeError("Tk control not mapped: " + label)
                x, y = widget.winfo_rootx(), widget.winfo_rooty()
                w, h = widget.winfo_width(), widget.winfo_height()
                if x < 0 or y < 0 or x + w > 1024 or y + h > 720 or w < 50 or h < 15:
                    raise RuntimeError("Tk control clipped in 1024x720: " + label)
                visible[label] = [x, y, w, h]
            ImageGrab.grab(bbox=(0, 0, 1024, 720)).save(output / "tk-1024x720.png")
            app.v["date"].set("2026-10-12")
            app.v["kind"].set("income")
            app.v["amount"].set("50.25")
            app.v["category"].set("Business income")
            buttons["Add transaction"].invoke()
            rows = app.store.rows()
            if len(rows) != 1:
                raise RuntimeError("GUI transaction entry failed")
            tid = rows[0]["id"]
            app.tree.selection_set(str(tid))
            prompts.extend(["Business Checking", "2026-10-31"])
            buttons["Match selected"].invoke()
            if match_statuses(app.store.conn).get(tid) != "CLEARED":
                raise RuntimeError("GUI bank match failed")
            prompts.extend(["Business Checking", "2026-10-31", "100.00", "150.25"])
            buttons["Check statement"].invoke()
            if match_statuses(app.store.conn).get(tid) != "RECONCILED":
                raise RuntimeError("GUI zero-difference check failed")
            checked = output / "checked.csv"
            prompts.extend(["Business Checking", "2026-10-31"])
            destinations.append(checked)
            buttons["Export bank check report"].invoke()
            if not checked.is_file() or not checked.with_suffix(".txt").is_file():
                raise RuntimeError("GUI checked report not created")
            if not any(str(checked) in m["text"] and str(checked.with_suffix(".txt")) in m["text"]
                       for m in messages):
                raise RuntimeError("GUI did not disclose both report paths")
        finally:
            app.close()
        app = ledger_ui.App()
        try:
            app.geometry("1000x696+12+12")
            app.update()
            buttons = tk_buttons(app)
            if match_statuses(app.store.conn).get(tid) != "RECONCILED":
                raise RuntimeError("Restart did not preserve checked state")
            prompts.extend(["Business Checking", "2026-10-31"])
            buttons["Undo checked"].invoke()
            if match_statuses(app.store.conn).get(tid) != "CLEARED":
                raise RuntimeError("GUI undo failed")
            undone = output / "undone.csv"
            prompts.extend(["Business Checking", "2026-10-31"])
            destinations.append(undone)
            buttons["Export bank check report"].invoke()
            text = undone.with_suffix(".txt").read_text(encoding="utf-8")
            if "BANK_RECONCILE_CANCEL" not in text or "UNDONE" not in text:
                raise RuntimeError("Undo audit missing from readable report")
            if app.store.conn.execute("SELECT amount_cents FROM transactions WHERE id=?", (tid,)).fetchone()[0] != 5025:
                raise RuntimeError("Undo changed ledger amount")
            original = checked.read_bytes()
            info_count = len(messages)
            prompts.extend(["Business Checking", "2026-10-31"])
            destinations.append(checked)
            buttons["Export bank check report"].invoke()
            if checked.read_bytes() != original or len(messages) != info_count or not errors:
                raise RuntimeError("Existing output was overwritten or false success reported")
            if statement_preview(app.store.conn, "Business Checking", "2026-10-31",
                                 "100.00", "150.26")["difference_cents"] == 0:
                raise RuntimeError("Nonzero difference accepted")
            if prompts or destinations:
                raise RuntimeError("GUI test left unused dialog inputs")
            return {"status": "PASS_PROGRAMMATIC_TK_BUTTONS_NOT_HUMAN",
                    "visible_controls": visible, "checked_csv_sha256": sha256(checked),
                    "undone_csv_sha256": sha256(undone),
                    "reports": [str(checked), str(undone)],
                    "success_dialogs": len(messages), "expected_failure_dialogs": len(errors),
                    "ledger_amount_unchanged_cents": 5025}
        finally:
            app.close()


def gui(source, output):
    source, output = Path(source).resolve(), Path(output).resolve()
    exe = output / (SLUG + ".exe")
    receipt = json.loads((output / "exe-receipt.json").read_text(encoding="utf-8"))
    if receipt["source_sha"] != PINNED or sha256(exe) != receipt["executable_sha256"]:
        raise RuntimeError("GUI EXE differs from immutable build receipt")
    work = output / "gui-data"
    work.mkdir(exist_ok=False)
    appdata = work / "AppData"
    appdata.mkdir()
    evidence = {"schema_version": 1, "source_sha": PINNED,
                "exe_sha256": sha256(exe), "human_qa": "NOT_PERFORMED",
                "physical_dpi_125_150": "NOT_PERFORMED",
                "host_work_area": get_work_area(), "steps": {}}
    try:
        evidence["steps"]["packaged_initial"] = launch_exe(exe, appdata, output, "initial")
        evidence["steps"]["tk_workflow"] = tk_workflow(source, appdata, output)
        evidence["steps"]["packaged_restart"] = launch_exe(exe, appdata, output, "restart")
        if (evidence["steps"]["packaged_initial"].get("status") or
                evidence["steps"]["packaged_restart"].get("status")):
            evidence["status"] = "HOLD_PACKAGED_WINDOW_UNVERIFIED_TK_WORKFLOW_TESTED"
        else:
            evidence["status"] = "PASS_HOSTED_PACKAGED_LAUNCH_AND_TK_WORKFLOW"
    except Exception as exc:
        evidence["status"] = "GUI_HOLD"
        evidence["error"] = type(exc).__name__ + ": " + str(exc)[:300]
        raise
    finally:
        (output / "hosted-gui-receipt.json").write_text(
            json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(evidence, sort_keys=True))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["package", "gui"])
    parser.add_argument("--source", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    if args.action == "package":
        package(args.source, args.output)
    else:
        gui(args.source, args.output)
