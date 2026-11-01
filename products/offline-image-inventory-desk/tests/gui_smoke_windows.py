"""CLOUD_WINDOWS_GUI_SMOKE: real Tk window and unsigned EXE launch on hosted Windows.
Not LOCAL_GUI_PASS; never mutates source image folders after fixture setup.
"""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import time
from unittest.mock import patch
import zlib

PRODUCT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PRODUCT))
import main as app
import tkinter as tk
from PIL import ImageGrab
from pywinauto import Desktop


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def png(path, rgb):
    width, height = 24, 18
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)
    raw = b"".join(b"\x00" + bytes(rgb) * width for _ in range(height))
    Path(path).write_bytes(b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def hashes(folder):
    return {p.relative_to(folder).as_posix(): sha(p)
            for p in sorted(folder.rglob("*.png"))}


def screenshot(root, destination):
    root.update_idletasks()
    root.update()
    time.sleep(0.35)
    root.update()
    if not root.winfo_viewable():
        raise AssertionError("GUI window not viewable on Windows runner")
    x, y = root.winfo_rootx(), root.winfo_rooty()
    w, h = root.winfo_width(), root.winfo_height()
    if w < 850 or h < 600:
        raise AssertionError("Window clipped: %sx%s" % (w, h))
    image = ImageGrab.grab(bbox=(x, y, x + w, y + h))
    if image.size != (w, h) or len(image.getcolors(maxcolors=1000000) or []) < 3:
        raise AssertionError("No useful screenshot content")
    image.save(destination)
    return {"width": w, "height": h, "sha256": sha(destination)}


def invoke_with_dialog(button, name, value):
    with patch.object(app.filedialog, name, return_value=str(value)):
        button.invoke()


def run(out, exe, source_sha):
    out.mkdir(parents=True, exist_ok=True)
    logs = []
    screenshots = {}
    with tempfile.TemporaryDirectory(prefix="image-gui-smoke-") as temp:
        rootdir = Path(temp)
        baseline = rootdir / "baseline"
        delivery = rootdir / "delivery"
        baseline.mkdir()
        delivery.mkdir()
        for name, rgb in (("same.png", (5, 10, 15)),
                          ("modified.png", (20, 40, 60)),
                          ("removed.png", (80, 100, 120))):
            png(baseline / name, rgb)
        for file in baseline.iterdir():
            shutil.copyfile(file, delivery / file.name)
        png(delivery / "modified.png", (200, 10, 20))
        (delivery / "removed.png").unlink()
        png(delivery / "added.png", (10, 210, 30))
        initial = {"baseline": hashes(baseline), "delivery": hashes(delivery)}
        saved = rootdir / "baseline.json"
        csv_path, json_path, txt_path = (out / "changes.csv", out / "changes.json",
                                         out / "delivery-summary-ja.txt")
        root = tk.Tk()
        try:
            desk = app.Desk(root)
            screenshots["01_initial_en"] = screenshot(root, out / "01_initial_en.png")
            record_ui_layout(root, desk, out)
        finally:
            root.destroy()
        # Drive baseline/compare/export in a fresh real Tk session.
        root = tk.Tk()
        try:
            desk = app.Desk(root)
            with patch.object(app.filedialog, "askdirectory", return_value=str(baseline)), \
                 patch.object(app.filedialog, "asksaveasfilename", return_value=str(saved)):
                desk.snapshot_buttons["snap_new"].invoke()
            assert saved.is_file() and desk.baseline is not None, "Baseline not saved"
            logs.append("baseline saved via real Tk button")
            screenshots["02_baseline_en"] = screenshot(root, out / "02_baseline_en.png")
            invoke_with_dialog(desk.snapshot_buttons["snap_compare"], "askdirectory", delivery)
            assert desk.comparison is not None, "Comparison missing"
            assert desk.comparison["summary"] == {"ADDED": 1, "REMOVED": 1, "MODIFIED": 1, "UNCHANGED": 1}
            logs.append("two folders: added=1 removed=1 modified=1 unchanged=1")
            screenshots["03_comparison_en"] = screenshot(root, out / "03_comparison_en.png")
            with patch.object(app.filedialog, "asksaveasfilename", return_value=str(csv_path)):
                desk.snapshot_buttons["snap_export"].invoke()
            with patch.object(app.filedialog, "asksaveasfilename", return_value=str(json_path)):
                desk.snapshot_buttons["snap_export"].invoke()
            desk.lang.invoke()
            assert desk.language == "ja" and "納品" in desk.summary_button.cget("text")
            screenshots["04_japanese"] = screenshot(root, out / "04_japanese.png")
            with patch.object(app.filedialog, "asksaveasfilename", return_value=str(txt_path)):
                desk.summary_button.invoke()
            assert "日時の限界" in txt_path.read_text(encoding="utf-8")
            assert json.loads(json_path.read_text(encoding="utf-8"))["summary"]["MODIFIED"] == 1
            with csv_path.open(encoding="utf-8", newline="") as stream:
                assert len(list(csv.DictReader(stream))) == 4
            logs.append("CSV, JSON and Japanese TXT exported via GUI")
        finally:
            for child in root.winfo_children():
                if isinstance(child, tk.Toplevel):
                    child.destroy()
            root.destroy()

        root = tk.Tk()
        try:
            desk = app.Desk(root)
            with patch.object(app.filedialog, "askopenfilename", return_value=str(saved)):
                desk.snapshot_buttons["snap_open"].invoke()
            assert desk.baseline is not None
            invoke_with_dialog(desk.snapshot_buttons["snap_compare"], "askdirectory", delivery)
            assert desk.comparison is not None
            screenshots["05_restarted"] = screenshot(root, out / "05_restarted.png")
            logs.append("restart, open baseline and recompare PASS")
            # Close the comparison overlay before capturing the main-window error state.
            for child in root.winfo_children():
                if isinstance(child, tk.Toplevel):
                    child.destroy()
            root.lift()
            root.focus_force()
            errors = []
            with patch.object(app, "inspect_image", side_effect=PermissionError("simulated read denied")), \
                 patch.object(app.messagebox, "showerror", side_effect=lambda *a, **kw: errors.append(str(a))):
                invoke_with_dialog(desk.snapshot_buttons["snap_compare"], "askdirectory", delivery)
            assert errors and desk.comparison is None, "Read error did not invalidate old evidence"
            assert desk.status.get() == desk.t("snap_failed"), "Error not visible to user"
            screenshots["06_read_error"] = screenshot(root, out / "06_read_error.png")
            if screenshots["06_read_error"]["sha256"] == screenshots["05_restarted"]["sha256"]:
                raise AssertionError("Read-error screenshot indistinguishable from prior state")
            with patch.object(app.filedialog, "asksaveasfilename",
                              side_effect=AssertionError("stale evidence dialog opened")):
                desk.summary_button.invoke()
            assert desk.comparison is None, "Stale summary export re-enabled"
            logs.append("read error visible; stale comparison invalidated; no false export")
        finally:
            for child in root.winfo_children():
                if isinstance(child, tk.Toplevel):
                    child.destroy()
            root.destroy()
        assert initial == {"baseline": hashes(baseline), "delivery": hashes(delivery)}, "SOURCE_IMAGES_MODIFIED"
        logs.append("source image SHA-256 before/after identical")

        # Launch the actual packaged PE as a separate GUI process, not just source Tk.
        process = subprocess.Popen([str(exe)], cwd=str(exe.parent))
        try:
            window = Desktop(backend="win32").window(title="Offline Image Inventory Desk")
            window.wait("visible", timeout=40)
            shot = out / "07_packaged_exe.png"
            window.capture_as_image().save(str(shot))
            if shot.stat().st_size < 1000:
                raise AssertionError("Packaged EXE screenshot empty")
            screenshots["07_packaged_exe"] = {"sha256": sha(shot), "bytes": shot.stat().st_size}
            logs.append("actual unsigned packaged EXE launched and window captured")
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()

        receipt = {
            "classification": "CLOUD_WINDOWS_GUI_SMOKE",
            "not_local_gui_pass": True,
            "source_sha": source_sha,
            "exe_sha256": sha(exe),
            "exe_bytes": exe.stat().st_size,
            "source_images_untouched": True,
            "fixture_input_sha256": initial,
            "evidence_sha256": {p.name: sha(p) for p in (saved, csv_path, json_path, txt_path)},
            "screenshots": screenshots,
            "checks": logs,
            "market_fit": "MARKET_FIT_HOLD",
            "market_score": 64,
            "why_pay_verified": False,
        }
        (out / "gui-smoke-receipt.json").write_text(
            json.dumps(receipt, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        (out / "gui-smoke.log").write_text("\n".join(logs) + "\n", encoding="utf-8")
        print(json.dumps(receipt, ensure_ascii=False, indent=2))



def record_ui_layout(root, desk, out):
    """Calibrate real Tk button centres for separate black-box packaged-EXE clicks."""
    root.update_idletasks()
    root.update()
    widgets = dict(desk.snapshot_buttons)
    widgets.update({"summary": desk.summary_button, "lang": desk.lang})
    coords = {}
    for name, widget in widgets.items():
        if not widget.winfo_viewable():
            raise AssertionError("Unmapped button: " + name)
        coords[name] = [
            widget.winfo_rootx() - root.winfo_rootx() + widget.winfo_width() // 2,
            widget.winfo_rooty() - root.winfo_rooty() + widget.winfo_height() // 2,
        ]
    (out / "ui-layout.json").write_text(json.dumps(coords, indent=2), encoding="utf-8")
    return coords


def run_packaged(out, exe, source_sha, calibration):
    """Black-box automation: all user operations go through the built PE process.

    No import or monkeypatch of the application in this path. Native Windows file
    dialogs and screen clicks are controlled from a separate Python process.
    """
    import pyautogui
    import win32gui
    import psutil
    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.2
    out.mkdir(parents=True, exist_ok=True)
    controls = json.loads(calibration.read_text(encoding="utf-8"))
    expected = {"ADDED": 1, "REMOVED": 1, "MODIFIED": 1, "UNCHANGED": 1}
    log = []
    shots = {}
    with tempfile.TemporaryDirectory(prefix="packaged-image-e2e-") as tmp:
        folder = Path(tmp)
        baseline, delivery = folder / "baseline", folder / "delivery"
        baseline.mkdir()
        delivery.mkdir()
        for name, rgb in (("same.png", (5, 10, 15)),
                          ("modified.png", (20, 40, 60)),
                          ("removed.png", (80, 100, 120))):
            png(baseline / name, rgb)
            shutil.copyfile(baseline / name, delivery / name)
        png(delivery / "modified.png", (200, 10, 20))
        (delivery / "removed.png").unlink()
        png(delivery / "added.png", (10, 210, 30))
        originals = {"baseline": hashes(baseline), "delivery": hashes(delivery)}
        snapshot = folder / "baseline.json"
        csv_path = out / "packaged-changes.csv"
        json_path = out / "packaged-changes.json"
        txt_path = out / "packaged-summary-ja.txt"
        process = None
        window = None

        def start():
            nonlocal process, window
            process = subprocess.Popen([str(exe)], cwd=str(folder))
            # PyInstaller onefile uses a parent bootloader and child GUI PID.
            deadline = time.monotonic() + 45
            match = None
            while time.monotonic() < deadline:
                try:
                    allowed = {process.pid} | {child.pid for child in psutil.Process(process.pid).children(recursive=True)}
                except psutil.Error:
                    allowed = {process.pid}
                candidates = Desktop(backend="win32").windows(
                    title="Offline Image Inventory Desk", visible_only=True)
                match = next((candidate for candidate in candidates
                              if candidate.process_id() in allowed), None)
                if match:
                    break
                time.sleep(0.35)
            if match is None:
                raise AssertionError("Packaged GUI window not found in EXE process tree")
            window = Desktop(backend="win32").window(handle=match.handle)
            window.wait("visible", timeout=5)
            time.sleep(1.2)
            window.set_focus()
            rect = window.rectangle()
            if rect.width() < 1000 or rect.height() < 700:
                raise AssertionError("Packaged EXE window too small: " + str(rect))
            log.append("packaged EXE process started PID=" + str(process.pid))

        def stop():
            nonlocal process, window
            if process is not None:
                subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                               capture_output=True, text=True, check=False, timeout=15)
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
            process, window = None, None

        def click(name):
            window.set_focus()
            x0, y0 = win32gui.ClientToScreen(window.handle, (0, 0))
            dx, dy = controls[name]
            pyautogui.click(x0 + dx, y0 + dy)
            time.sleep(0.65)

        def wait_dialog():
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                dialogs = Desktop(backend="win32").windows(
                    class_name="#32770", process=window.process_id(), visible_only=True)
                if dialogs:
                    return dialogs[-1]
                time.sleep(0.25)
            raise AssertionError("Native Windows file/folder dialog did not appear")

        def choose_path(path):
            dialog = wait_dialog()
            uia = Desktop(backend="uia").window(handle=dialog.handle)
            edits = uia.descendants(control_type="Edit")
            if not edits:
                raise AssertionError("Native dialog has no editable folder/file path field")
            field = edits[-1]
            field.set_edit_text(str(path))
            time.sleep(0.35)
            dialog.set_focus()
            pyautogui.press("enter")
            time.sleep(1.0)
            # Some native dialogs first navigate into the typed folder.
            if win32gui.IsWindow(dialog.handle) and win32gui.IsWindowVisible(dialog.handle):
                buttons = [b for b in uia.descendants(control_type="Button")
                           if b.window_text().lower() in ("ok", "select folder", "open", "save", "フォルダーの選択", "保存")]
                if buttons:
                    buttons[-1].click_input()
                    time.sleep(0.8)
            if win32gui.IsWindow(dialog.handle) and win32gui.IsWindowVisible(dialog.handle):
                raise AssertionError("Native dialog remained open after selecting " + str(path))

        def action(button, *paths):
            click(button)
            for path in paths:
                choose_path(path)
            log.append("packaged UI " + button + ": " + ", ".join(str(p) for p in paths))

        def capture(label, focus=True):
            if focus:
                window.set_focus()
            time.sleep(0.3)
            rect = window.rectangle()
            image = ImageGrab.grab(bbox=(rect.left, rect.top, rect.right, rect.bottom))
            if image.width < 1000 or image.height < 700:
                raise AssertionError("Packaged GUI capture clipped")
            path = out / (label + ".png")
            image.save(path)
            shots[label] = {"sha256": sha(path), "width": image.width, "height": image.height}

        def close_comparison():
            # The comparison table is a distinct Tk Toplevel, not a file dialog.
            for w in Desktop(backend="win32").windows(process=window.process_id(), visible_only=True):
                if w.handle != window.handle and "delivery changes" in w.window_text().lower():
                    w.close()
                    time.sleep(0.5)

        try:
            start()
            capture("01_exe_initial_en")
            action("snap_new", baseline, snapshot)
            if not snapshot.is_file():
                raise AssertionError("Packaged EXE did not save baseline")
            capture("02_exe_baseline")
            action("snap_compare", delivery)
            close_comparison()
            capture("03_exe_comparison")
            action("snap_export", csv_path)
            action("snap_export", json_path)
            click("lang")
            if "オフライン" not in win32gui.GetWindowText(window.handle):
                raise AssertionError("Packaged EXE did not switch to Japanese")
            capture("04_exe_japanese")
            action("summary", txt_path)
            if not all(p.is_file() for p in (csv_path, json_path, txt_path)):
                raise AssertionError("Packaged EXE exports missing")
            report = json.loads(json_path.read_text(encoding="utf-8"))
            if report["summary"] != expected:
                raise AssertionError("Wrong packaged comparison counts: " + str(report["summary"]))
            with csv_path.open(encoding="utf-8", newline="") as stream:
                if len(list(csv.DictReader(stream))) != 4:
                    raise AssertionError("Packaged CSV has incorrect rows")
            if "日時の限界" not in txt_path.read_text(encoding="utf-8"):
                raise AssertionError("Packaged Japanese TXT disclaimer missing")
            log.append("packaged CSV/JSON/TXT contents validated")
            stop()
            start()
            action("snap_open", snapshot)
            action("snap_compare", delivery)
            close_comparison()
            capture("05_exe_restarted")
            # Malformed image forces a real parser read error without admin symlink rights.
            (delivery / "unreadable.png").write_bytes(b"malformed image fixture")
            expected_files = {"baseline": hashes(baseline), "delivery": hashes(delivery)}
            click("snap_compare")
            choose_path(delivery)
            dialog = wait_dialog()  # real error messagebox
            error_text = dialog.window_text()
            capture("06_exe_read_error", focus=False)
            dialog.set_focus()
            pyautogui.press("enter")
            time.sleep(0.5)
            # A stale successful comparison must not open an export Save dialog.
            click("summary")
            if Desktop(backend="win32").windows(class_name="#32770",
                                                process=window.process_id(), visible_only=True):
                raise AssertionError("Packaged EXE allowed stale summary export")
            log.append("packaged read error blocked stale summary export: " + error_text)
            if expected_files != {"baseline": hashes(baseline), "delivery": hashes(delivery)}:
                raise AssertionError("SOURCE_IMAGES_MODIFIED")
            if originals["baseline"] != hashes(baseline):
                raise AssertionError("BASELINE_IMAGES_MODIFIED")
            log.append("all source images untouched")
        finally:
            stop()
        receipt = {
            "classification": "CLOUD_WINDOWS_PACKAGED_EXE_E2E",
            "not_source_tk_smoke": True,
            "not_local_gui_pass": True,
            "source_sha": source_sha,
            "exe_sha256": sha(exe),
            "exe_bytes": exe.stat().st_size,
            "source_images_untouched": True,
            "fixture_sha256_before": originals,
            "fixture_sha256_after": {"baseline": hashes(baseline), "delivery": hashes(delivery)},
            "screenshots": shots,
            "checks": log,
            "market_fit": "MARKET_FIT_HOLD",
            "market_score": 64,
            "why_pay_verified": False,
        }
        (out / "packaged-exe-e2e-receipt.json").write_text(
            json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (out / "packaged-exe-e2e.log").write_text("\n".join(log) + "\n", encoding="utf-8")
        print(json.dumps(receipt, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--exe", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--mode", choices=("source", "packaged"), default="source")
    parser.add_argument("--calibration", type=Path)
    args = parser.parse_args()
    if os.name != "nt":
        raise SystemExit("Windows GUI runner required")
    if args.mode == "packaged":
        if args.calibration is None:
            parser.error("--calibration required for packaged mode")
        run_packaged(args.out.resolve(), args.exe.resolve(), args.source_sha, args.calibration.resolve())
    else:
        run(args.out.resolve(), args.exe.resolve(), args.source_sha)
