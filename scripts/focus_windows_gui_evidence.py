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
    return image


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
                **{f"preset_{minutes}": button for minutes, button in desk.preset_buttons.items()},
            })
            screenshot(output / "01-first-run.png")
            desk.entry_var.set("QA task 日本語")
            desk.add()
            assert len(desk.data["tasks"]) == 1
            ident = desk.data["tasks"][0]["id"]
            desk.tree.selection_set(ident)
            desk.toggle()
            assert desk.data["tasks"][0]["done"] is True
            assert desk.start_preset(50)
            assert desk.timer.minutes == 50
            assert desk.timer.state == "running"
            assert all("disabled" in button.state() for button in desk.preset_buttons.values())
            desk.pause_resume()
            assert desk.timer.state == "paused"
            desk.pause_resume()
            assert desk.timer.state == "running"
            desk.reset()
            assert desk.timer.state == "idle"
            assert desk.start_preset(25)
            assert desk.timer.minutes == 25 and desk.timer.state == "running"
            desk.reset()
            desk.minutes_var.set("50")
            desk.apply_minutes()
            assert desk.timer.minutes == 50 and desk.timer.state == "idle"
            desk.switch_language()
            assert desk.lang == "en"
            visible(root, {"start": desk.start_button, "language": desk.language_button,
                           "task_list": desk.tree, "task_input": desk.entry})
            screenshot(output / "02-actions-en.png")
            desk.close()
        finally:
            # Desk.close() may already have destroyed the Tcl interpreter.
            try:
                root.destroy()
            except tk.TclError:
                pass
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
            # Desk.close() may already have destroyed the Tcl interpreter.
            try:
                root.destroy()
            except tk.TclError:
                pass


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
                    # PyInstaller onefile may host Tk in a child process.
                    # The isolated runner plus a live launched EXE and exact
                    # window title are required; PID equality is not reliable.
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
            # A launched window is not consumer-ready if its controls sit
            # beneath the Windows taskbar. Use the actual desktop work area.
            class Rect(ctypes.Structure):
                _fields_ = [("left", wintypes.LONG), ("top", wintypes.LONG),
                            ("right", wintypes.LONG), ("bottom", wintypes.LONG)]
            window_rect, work_rect = Rect(), Rect()
            if not user32.GetWindowRect(hwnd, ctypes.byref(window_rect)):
                raise RuntimeError("Cannot inspect EXE window bounds")
            if not user32.SystemParametersInfoW(48, 0, ctypes.byref(work_rect), 0):
                raise RuntimeError("Cannot inspect Windows desktop work area")
            if (window_rect.left < work_rect.left or window_rect.top < work_rect.top
                    or window_rect.right > work_rect.right
                    or window_rect.bottom > work_rect.bottom):
                raise RuntimeError(
                    f"EXE window overlaps taskbar or desktop edge: "
                    f"window=({window_rect.left},{window_rect.top},"
                    f"{window_rect.right},{window_rect.bottom}), "
                    f"workarea=({work_rect.left},{work_rect.top},"
                    f"{work_rect.right},{work_rect.bottom})")
            # The GitHub runner may put its console above the application.
            # Capture the real HWND via Windows PrintWindow (Pillow 11.3+)
            # rather than mislabeling a console screenshot as the EXE UI.
            window_image = ImageGrab.grab(window=hwnd)
            if (window_image.width < 790 or window_image.height < 550
                    or min(ImageStat.Stat(window_image.convert("RGB")).mean) < 125):
                raise RuntimeError("Actual EXE HWND capture is blank or too small")
            window_image.save(output / "04-real-exe-window.png")
            # Keep the unmodified desktop capture separately for context.
            screenshot(output / "05-desktop-context.png")
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
