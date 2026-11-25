"""Windows-only US accounting GUI smoke; never touches JP storage or Store packaging."""
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
PRODUCT = ROOT / "products" / "us-freelance-ledger"
sys.path.insert(0, str(PRODUCT))
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog, font as tkfont
from PIL import ImageGrab


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    out = Path(os.environ.get("APP_SMOKE_OUTPUT", "app-smoke-evidence")).resolve()
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["APPDATA"] = tmp
        import main as us_main
        app = us_main.App()
        try:
            app.update()
            buttons = []

            def walk(widget):
                for child in widget.winfo_children():
                    if isinstance(child, ttk.Button) and child.cget("text") == "US tax — REVIEW REQUIRED":
                        buttons.append(child)
                    walk(child)

            walk(app)
            assert len(buttons) == 1, f"Expected one real GUI button, got {len(buttons)}"
            button_font = tkfont.Font(root=app, font=buttons[0].cget("font") or "TkDefaultFont")
            button_text_width = button_font.measure(buttons[0].cget("text"))
            button_width = buttons[0].winfo_width()
            assert button_text_width + 24 <= button_width, (
                f"Review button label is clipped: text={button_text_width}px, widget={button_width}px"
            )

            receipt = {"source_sha": os.environ.get("APP_SOURCE_SHA", "LOCAL"), "scenarios": []}

            def shot(label):
                app.update()
                path = out / (label + ".png")
                ImageGrab.grab().save(path)
                return {"file": path.name, "sha256": sha(path)}

            receipt["window"] = shot("us_main_window")
            receipt["review_button"] = {
                "label": buttons[0].cget("text"),
                "text_width_px": button_text_width,
                "widget_width_px": button_width,
                "fully_visible": button_text_width + 24 <= button_width,
            }
            with patch.object(us_main, "confirm_us_tax_review", return_value=False) as confirm, patch.object(simpledialog, "askstring") as ask:
                buttons[0].invoke()
                assert confirm.call_count == 1 and ask.call_count == 0
                receipt["scenarios"].append({"case": "decline", "result": "no_calculator_opened"})
            with patch.object(us_main, "confirm_us_tax_review", return_value=True) as confirm, patch.object(simpledialog, "askstring", side_effect=["sales tax", "California"]), patch.object(simpledialog, "askfloat", side_effect=[100.0, 7.5]), patch.object(messagebox, "showinfo") as info:
                buttons[0].invoke()
                assert confirm.call_count == 1 and info.call_count == 1
                title, body = info.call_args.args[:2]
                assert "REVIEW REQUIRED" in title and "USD" in body and "No posting" in body
                receipt["scenarios"].append({"case": "approve", "title": title, "body": body, "result": "USD_review_only"})

            assert not (Path(tmp) / "JPFreelanceLedger").exists()
            receipt["jp_storage_untouched"] = True
            receipt["dialog_method"] = "patched deterministic Tk dialog callbacks; NOT native modal click evidence"
            receipt["request_sha256"] = sha(__file__)
            (out / "receipt.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
        finally:
            # The Windows runner locks SQLite files until the connection is
            # explicitly closed. Always close even when a locator/assertion fails.
            try:
                app.store.close()
            finally:
                try:
                    app.destroy()
                except tk.TclError:
                    pass


if __name__ == "__main__":
    main()
