"""Discover US bank CSV preview tests in Windows and Ubuntu Factory CI."""
import importlib.util
import sys
import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from tkinter import ttk
from unittest.mock import patch

PRODUCT = Path(__file__).resolve().parents[1] / "products" / "us-freelance-ledger"
sys.path.insert(0, str(PRODUCT))
SPEC = importlib.util.spec_from_file_location(
    "us_bank_csv_preview_cases", PRODUCT / "tests" / "test_bank_csv_preview.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
BankCSVPreviewTests = MODULE.BankCSVPreviewTests

UI_SPEC = importlib.util.spec_from_file_location("us_bank_csv_preview_ui", PRODUCT / "main.py")
UI = importlib.util.module_from_spec(UI_SPEC)
UI_SPEC.loader.exec_module(UI)
from core import Store


class BankCSVPreviewGuiTests(unittest.TestCase):
    def test_three_step_entry_visible_on_hosted_1024x720(self):
        try:
            probe = tk.Tk()
            probe.withdraw()
            probe.destroy()
        except tk.TclError:
            self.skipTest("No desktop; Windows hosted Tk verifies mapped controls")
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(UI, "_work_area", return_value=(0, 0, 1024, 720)), \
                 patch.object(UI, "Store", side_effect=lambda: Store(Path(directory) / "ledger.sqlite3")):
                app = UI.App()
                try:
                    app.update()
                    buttons = []
                    def visit(widget):
                        for child in widget.winfo_children():
                            if isinstance(child, ttk.Button) and child.cget("text") == "Preview bank CSV (no posting)":
                                buttons.append(child)
                            visit(child)
                    visit(app)
                    self.assertEqual(len(buttons), 1)
                    self.assertTrue(buttons[0].winfo_ismapped())
                    self.assertLessEqual(buttons[0].winfo_rootx()+buttons[0].winfo_width(), 1024)
                    self.assertLessEqual(buttons[0].winfo_rooty()+buttons[0].winfo_height(), 720)
                    buttons[0].invoke()
                    app.update()
                    dialogs = [child for child in app.winfo_children() if isinstance(child, tk.Toplevel)]
                    self.assertEqual(len(dialogs), 1)
                    self.assertIn("NOT posted", dialogs[0].title())
                    dialogs[0].destroy()
                finally:
                    app.close()


if __name__ == "__main__":
    unittest.main()
