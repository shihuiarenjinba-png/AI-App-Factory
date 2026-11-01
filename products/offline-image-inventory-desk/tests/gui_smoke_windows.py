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
            invoke_with_dialog(desk.snapshot_buttons["snap_new"], "askdirectory", baseline)
            # Save dialog is a separate interaction; patch both for the same button.
        finally:
            root.destroy()
        # Reopen to ensure the full UI sequence is driven with both dialogs.
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
            errors = []
            with patch.object(app, "inspect_image", side_effect=PermissionError("simulated read denied")), \
                 patch.object(app.messagebox, "showerror", side_effect=lambda *a, **kw: errors.append(str(a))):
                invoke_with_dialog(desk.snapshot_buttons["snap_compare"], "askdirectory", delivery)
            assert errors and desk.comparison is None, "Read error did not invalidate old evidence"
            assert desk.status.get() == desk.t("snap_failed"), "Error not visible to user"
            screenshots["06_read_error"] = screenshot(root, out / "06_read_error.png")
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


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--exe", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--source-sha", required=True)
    args = parser.parse_args()
    if os.name != "nt":
        raise SystemExit("Windows GUI runner required")
    run(args.out.resolve(), args.exe.resolve(), args.source_sha)
