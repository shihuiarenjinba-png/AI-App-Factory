"""Include product-local bank receipt fixtures in Factory Windows/Ubuntu discovery."""
import importlib.util
import sys
from pathlib import Path

PRODUCT = Path(__file__).resolve().parents[1] / "products" / "us-freelance-ledger"
sys.path.insert(0, str(PRODUCT))
SPEC = importlib.util.spec_from_file_location(
    "us_freelance_bank_receipt_cases", PRODUCT / "tests" / "test_bank_report.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
BankReceiptTests = MODULE.BankReceiptTests

import tempfile
import tkinter as tk
import unittest
from tkinter import ttk
from types import SimpleNamespace
from unittest.mock import patch
from core import Store
import main as ui


class BankReportGuiTests(unittest.TestCase):
    def test_export_button_fits_hosted_1024x720_when_display_available(self):
        try:
            probe = tk.Tk()
            probe.withdraw()
            probe.destroy()
        except tk.TclError:
            self.skipTest("No GUI display; Windows hosted Tk job verifies actual mapping")
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(ui, "_work_area", return_value=(0, 0, 1024, 720)), \
                 patch.object(ui, "Store", side_effect=lambda: Store(Path(directory) / "db.sqlite3")):
                app = ui.App()
                try:
                    app.update_idletasks()
                    app.update()
                    if not app.winfo_ismapped():
                        self.skipTest("Tk desktop not mapped")
                    found = []
                    def visit(widget):
                        for child in widget.winfo_children():
                            if isinstance(child, ttk.Button) and child.cget("text") == "Export bank check report":
                                found.append(child)
                            visit(child)
                    visit(app)
                    self.assertEqual(len(found), 1)
                    button = found[0]
                    self.assertTrue(button.winfo_ismapped())
                    self.assertGreater(button.winfo_width(), 100)
                    self.assertGreaterEqual(button.winfo_rootx(), 0)
                    self.assertLessEqual(button.winfo_rootx() + button.winfo_width(), 1024)
                    self.assertLessEqual(button.winfo_rooty() + button.winfo_height(), 720)
                finally:
                    app.close()

    def test_gui_export_failure_never_shows_success(self):
        fake = SimpleNamespace(store=SimpleNamespace(conn=object()))
        with patch.object(ui.simpledialog, "askstring", side_effect=["Checking", "2026-10-31"]), \
             patch.object(ui.filedialog, "asksaveasfilename", return_value="check.csv"), \
             patch.object(ui, "export_bank_report", side_effect=ui.BankReviewError("Already exists")), \
             patch.object(ui.messagebox, "showerror") as error, \
             patch.object(ui.messagebox, "showinfo") as success:
            ui.App.export_bank_check(fake)
            error.assert_called_once()
            success.assert_not_called()

    def test_gui_export_success_names_both_paths(self):
        fake = SimpleNamespace(store=SimpleNamespace(conn=object()))
        receipt = {
            "status": "CHECKED", "transaction_ids": [1], "difference_cents": 0,
            "csv_path": "C:/reports/check.csv", "text_path": "C:/reports/check.txt"
        }
        with patch.object(ui.simpledialog, "askstring", side_effect=["Checking", "2026-10-31"]), \
             patch.object(ui.filedialog, "asksaveasfilename", return_value="check.csv"), \
             patch.object(ui, "export_bank_report", return_value=receipt), \
             patch.object(ui.messagebox, "showinfo") as success:
            ui.App.export_bank_check(fake)
            text = success.call_args.args[1]
            self.assertIn(receipt["csv_path"], text)
            self.assertIn(receipt["text_path"], text)
            self.assertIn("REVIEW REQUIRED", success.call_args.args[0])
