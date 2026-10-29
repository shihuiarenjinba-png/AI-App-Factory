#!/usr/bin/env python3
"""Real Windows desktop evidence for Focus Session Desk; never claims human QA."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import traceback

from PIL import ImageGrab, ImageStat

ROOT = Path(__file__).resolve().parents[1]
PRODUCT = ROOT / "products" / "focus-session-desk"
sys.path.insert(0, str(PRODUCT))
from main import Desk  # noqa: E402


def screenshot(path):
    image = ImageGrab.grab(bbox=(0, 0, 1024, 768), all_screens=False)
    if image.size != (1024, 768):
        raise AssertionError("Screenshot is not 1024x768")
    image.save(path)
    if max(ImageStat.Stat(image.convert("RGB")).stddev) < 2:
        raise AssertionError("Captured screen is blank/uniform")


def require_screen(root):
    root.update_idletasks()
    if root.winfo_screenwidth() < 1024 or root.winfo_screenheight() < 768:
        raise RuntimeError("Windows runner does not expose a 1024x768 desktop")


def visible(root, widgets):
    root.update()
    for name, widget in widgets.items():
        if not widget.winfo_ismapped():
            raise AssertionError(name + " is not mapped")
        x, y = widget.winfo_rootx(), widget.winfo_rooty()
        w, h = widget.winfo_width(), widget.winfo_height()
        if w < 8 or h < 8 or x < 0 or y < 0 or x + w > 1024 or y + h > 768:
            raise AssertionError(f"{name} clipped at {x},{y} {w}x{h}")


def source_smoke(output):
    import tkinter as tk
    with tempfile.TemporaryDirectory(prefix="focus-gui-") as folder:
        state = Path(folder) / "state.json"
        root = tk.Tk()
        try:
            require_screen(root)
            root.geometry("1000x700+0+0")
            desk = Desk(root, path=state)
            visible(root, {
                "timer": desk.clock_label, "minutes": desk.minutes_entry,
                "start": desk.start_button, "pause": desk.pause_button,
                "reset": desk.reset_button, "task_input": desk.entry,
                "task_list": desk.tree, "language": desk.language_button,
                **{f"task_button_{i}": button for i, (_, button) in enumerate(desk.buttons)},
            })
            screenshot(output / "01-first-run.png")
            desk.entry_var.set("QA task 日本語")
            desk.add()
            assert len(desk.data["tasks"]) == 1
            ident = desk.data["tasks"][0]["id"]
            desk.tree.selection_set(ident)
            desk.toggle()
            assert desk.data["tasks"][0]["done"] is True
            desk.minutes_var.set("50")
            desk.apply_minutes()
            assert desk.timer.minutes == 50
            desk.start()
            assert desk.timer.state == "running"
            desk.pause_resume()
            assert desk.timer.state == "paused"
            desk.pause_resume()
            assert desk.timer.state == "running"
            desk.reset()
            assert desk.timer.state == "idle"
            desk.switch_language()
            assert desk.lang == "en"
            visible(root, {"start": desk.start_button, "language": desk.language_button,
                           "task_list": desk.tree, "task_input": desk.entry})
            screenshot(output / "02-actions-en.png")
            desk.close()
        finally:
            if root.winfo_exists():
                root.destroy()
        root = tk.Tk()
        try:
            require_screen(root)
            root.geometry("1000x700+0+0")
            desk = Desk(root, path=state)
            assert desk.lang == "en"
            assert len(desk.data["tasks"]) == 1 and desk.data["tasks"][0]["done"]
            assert desk.timer.minutes == 50
            visible(root, {"start": desk.start_button, "task_list": desk.tree})
            screenshot(output / "03-restart-persisted.png")
            desk.close()
        finally:
            if root.winfo_exists():
                root.destroy()


def exe_smoke(exe, output):
    # Launch the actual unsigned EXE in an isolated APPDATA folder. Never
    # mistake successful process creation for a visible Windows GUI.
    import ctypes
    from ctypes import wintypes
    with tempfile.TemporaryDirectory(prefix="focus-exe-") as folder:
        env = dict(os.environ, APPDATA=folder)
        process = subprocess.Popen([str(exe)], cwd=str(exe.parent), env=env)
        try:
            hwnd = None
            user32 = ctypes.windll.user32
            user32.EnumWindows.argtypes = [ctypes.c_void_p, wintypes.LPARAM]
            user32.EnumWindows.restype = wintypes.BOOL
            callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
            def collect(window, _):
                nonlocal hwnd
                if user32.IsWindowVisible(window):
                    pid = wintypes.DWORD()
                    user32.GetWindowThreadProcessId(window, ctypes.byref(pid))
                    if pid.value == process.pid:
                        buffer = ctypes.create_unicode_buffer(256)
                        user32.GetWindowTextW(window, buffer, len(buffer))
                        if "Focus Session Desk" in buffer.value or "集中セッション" in buffer.value:
                            hwnd = window
                return True
            cb = callback_type(collect)
            for _ in range(40):
                if process.poll() is not None:
                    raise RuntimeError(f"EXE exited early: {process.returncode}")
                user32.EnumWindows(cb, 0)
                if hwnd:
                    break
                time.sleep(0.5)
            if not hwnd:
                raise RuntimeError("EXE did not expose a visible Focus Session Desk window")
            screenshot(output / "04-real-exe-window.png")
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--exe")
    args = parser.parse_args()
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    evidence = {
        "schema_version": 1,
        "product": "Focus Session Desk",
        "slug": "focus-session-desk",
        "source_branch": os.environ.get("GITHUB_REF_NAME"),
        "source_sha": os.environ.get("GITHUB_SHA"),
        "request_id": os.environ.get("FOCUS_REQUEST_ID"),
        "desktop": "Windows 1024x768",
        "human_review": "NOT_PERFORMED",
        "msix_install": "NOT_PERFORMED",
        "result": "HOLD",
    }
    try:
        source_smoke(out)
        evidence["source_gui"] = "AUTOMATED_WINDOWS_SOURCE_SMOKE_PASS"
        if args.exe:
            exe = Path(args.exe).resolve()
            if not exe.is_file() or exe.read_bytes()[:2] != b"MZ":
                raise RuntimeError("Missing/invalid Windows EXE")
            exe_smoke(exe, out)
            evidence["exe_gui"] = "AUTOMATED_WINDOWS_EXE_WINDOW_PASS"
        evidence["result"] = "AUTOMATED_GUI_EVIDENCE_ONLY"
    except Exception:
        evidence["error"] = traceback.format_exc()
        raise
    finally:
        (out / "evidence.json").write_text(
            json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
