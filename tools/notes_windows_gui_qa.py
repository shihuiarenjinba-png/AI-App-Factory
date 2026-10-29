#!/usr/bin/env python3
"""Cloud Windows GUI QA for the exact promoted Offline Notes source.

Never marks Store/Identity/E2E ready. Produces a screenshot and JSON evidence
only if a real Tk window, interactions, persistence and restart all succeed.
"""
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import tkinter as tk
from unittest.mock import patch

from PIL import ImageGrab

ROOT = Path(__file__).resolve().parents[1]
PRODUCT = ROOT / "products/offline-notes-canary"
sys.path.insert(0, str(PRODUCT))
from main import App, read_notes

OUT = Path(os.environ.get("GUI_QA_OUTPUT", "dist/notes-gui-qa"))
OUT.mkdir(parents=True, exist_ok=True)
EXPECTED_SOURCE = os.environ.get("EXPECTED_SOURCE_SHA", "06a076fcbc5b06760fc489aace43725eb62d9c47")


def assert_fits(root, app):
    root.update_idletasks()
    left = root.winfo_rootx()
    right = left + root.winfo_width()
    top = root.winfo_rooty()
    bottom = top + root.winfo_height()
    elements = list(app.buttons) + [app.favorite_button, app.save_as_button, app.favorites_check, app.search_entry,
                                   app.listbox, app.title_entry, app.tag_entry, app.body]
    for widget in elements:
        x, y = widget.winfo_rootx(), widget.winfo_rooty()
        w, h = widget.winfo_width(), widget.winfo_height()
        if w < 5 or h < 5 or x < left or y < top or x + w > right or y + h > bottom:
            raise AssertionError(f"Widget outside client area: {widget} {x},{y},{w},{h}")
    return [{"widget":str(w), "x":w.winfo_rootx()-left,
             "y":w.winfo_rooty()-top, "width":w.winfo_width(),
             "height":w.winfo_height()} for w in elements]


def run():
    import subprocess
    subprocess.run(["git", "diff", "--quiet", EXPECTED_SOURCE, "HEAD", "--",
                    "products/offline-notes-canary"], check=True)
    sha = EXPECTED_SOURCE
    report = {"source_sha": sha, "resolution_budget": "1024x768",
              "gui_pass": False, "identity_cas_allowed": False,
              "msix_status": "NOT_BUILT", "commercial_quality_status": "HOLD"}
    with tempfile.TemporaryDirectory() as tmp:
        data = Path(tmp) / "notes.json"
        root = tk.Tk()
        try:
            root.geometry("980x700+10+10")
            app = App(root)
            root.update()
            app.new()
            app.title.set("Sample Note")
            app.tag_text.set("Work, 研究")
            app.body.delete("1.0", "end")
            app.body.insert("1.0", "Sample body. Sample search.")
            root.update()  # Process real Tk modified events before the Save click.
            # Live tag filtering must work before Save without modifying the model.
            app.query.set("研究")
            root.update()
            assert app.visible == [app.current], "Draft tag missing from search"
            assert "tags" not in app.notes[0], "Search must not commit draft tags"
            app.query.set("")
            root.update()
            app.commit_editor()
            app.toggle_favorite()
            with patch("main.filedialog.asksaveasfilename", return_value=str(data)):
                assert app.save() is True
            assert data.is_file()
            # Exercise real bilingual Save As with a new filename, without overwriting.
            copy_path = Path(tmp) / "notes-safe-copy.json"
            with patch("main.filedialog.asksaveasfilename", return_value=str(copy_path)):
                assert app.save_as() is True
            assert copy_path.is_file() and app.path == copy_path
            assert read_notes(copy_path) == read_notes(data)
            report["save_as_new_file"] = True
            app.query.set("Sample")
            root.update()
            assert len(app.body.tag_ranges("search_match")) == 4
            assert app.favorites_check.cget("text") == "お気に入りのみ"
            assert app.save_as_button.cget("text") == "名前を付けて保存"
            app.favorites_check.invoke()
            root.update()
            assert app.favorites_only.get() and app.visible == [app.current]
            app.favorites_check.invoke()
            root.update()
            assert not app.favorites_only.get() and app.visible == [app.current]
            app.language()
            root.update()
            assert app.favorites_check.cget("text") == "Favorites only"
            assert app.save_as_button.cget("text") == "Save As"
            assert app.lang == "en" and root.title() == "Offline Notes"
            assert not app.dirty and app.status.get() == "Saved", "False unsaved state after Save"
            positions = assert_fits(root, app)
            screenshot = OUT / "offline-notes-1024x768.png"
            ImageGrab.grab(bbox=(0, 0, 1024, 768)).save(screenshot)
            report["screenshot_sha256"] = hashlib.sha256(screenshot.read_bytes()).hexdigest()
            report["widget_bounds"] = positions
            report["en_ja_toggle"] = True
            report["favorites_filter_toggled"] = True
            report["favorites_filter_ja_en"] = True
            report["search_highlight_ranges"] = 2
            report["saved_file_sha256"] = hashlib.sha256(data.read_bytes()).hexdigest()
        finally:
            root.destroy()
        root2 = tk.Tk()
        try:
            root2.geometry("980x700+10+10")
            app2 = App(root2)
            with patch("main.filedialog.askopenfilename", return_value=str(data)):
                app2.open_file()
            root2.update()
            notes, fallback = read_notes(data)
            assert not fallback and len(notes) == 1
            assert notes[0]["tags"] == ["Work", "研究"]
            assert notes[0]["favorite"] is True
            assert notes[0]["title"] == "Sample Note"
            assert app2.notes == notes
            app2.favorites_check.invoke()
            root2.update()
            assert app2.visible == [notes[0]["id"]]
            assert_fits(root2, app2)
            report["restart_reopen"] = True
            report["persisted_tags_and_favorite"] = True
        finally:
            root2.destroy()
    report["gui_pass"] = True
    (OUT / "gui-qa-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k:v for k,v in report.items() if k!="widget_bounds"}, ensure_ascii=False))


if __name__ == "__main__":
    run()
