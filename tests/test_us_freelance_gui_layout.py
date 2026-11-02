"""US-only first-run layout regression; no tax decisions or external data."""
import ast
import importlib.util
import sys
import tempfile
import tkinter as tk
from tkinter import ttk
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from types import SimpleNamespace

PRODUCT = Path(__file__).resolve().parents[1] / "products" / "us-freelance-ledger"
sys.path.insert(0, str(PRODUCT))
spec = importlib.util.spec_from_file_location("us_ledger_layout", PRODUCT / "main.py")
ui = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ui)


class FirstRunLayoutTests(unittest.TestCase):
    def test_taskbar_work_area_1024x720_never_starts_offscreen(self):
        with patch.object(ui.sys, "platform", "win32"):
            geometry, minimum_width, minimum_height = ui._window_bounds((0, 0, 1024, 720))
        self.assertEqual(geometry, "960x624+32+48")
        self.assertEqual((minimum_width, minimum_height), (900, 620))
        self.assertLessEqual(32 + 960 + 16, 1024)
        self.assertLessEqual(48 + 624 + 39, 720)
        self.assertNotIn("1100x720", geometry)

    def test_offset_work_area_restart_and_invalid_dimensions(self):
        with patch.object(ui.sys, "platform", "win32"):
            for _ in range(2):
                self.assertEqual(ui._window_bounds((0, 48, 1024, 720))[0],
                                 "960x624+32+96")
        for area in ((0, 0, 1024, 0), (0, 0, -1, 720)):
            with self.subTest(area=area), self.assertRaises(ValueError):
                ui._window_bounds(area)

    def test_windows_work_area_api_failure_reserves_taskbar_margins(self):
        root = SimpleNamespace(winfo_screenwidth=lambda: 1024,
                               winfo_screenheight=lambda: 768)
        with patch.object(ui.sys, "platform", "win32"), \
             patch.object(ui.ctypes, "windll", None, create=True):
            self.assertEqual(ui._work_area(root), (64, 64, 896, 640))
            geometry, minimum_width, minimum_height = ui._window_bounds(
                ui._work_area(root))
            self.assertEqual(geometry, "832x544+96+112")
            self.assertEqual((minimum_width, minimum_height), (832, 544))

    def test_bank_actions_two_rows_with_primary_flow_visible(self):
        tree = ast.parse((PRODUCT / "main.py").read_text(encoding="utf-8"))
        buttons = {}
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "grid"
                    and isinstance(node.func.value, ast.Call)):
                continue
            constructor = node.func.value
            if not (isinstance(constructor.func, ast.Attribute)
                    and constructor.func.attr == "Button"):
                continue
            opts = {kw.arg: kw.value for kw in constructor.keywords}
            if "text" not in opts:
                continue
            label = ast.literal_eval(opts["text"])
            placement = {kw.arg: ast.literal_eval(kw.value)
                         for kw in node.keywords if kw.arg in ("row", "column")}
            buttons[label] = placement
        self.assertEqual(buttons["Match selected"], {"row": 0, "column": 0})
        self.assertEqual(buttons["Check statement"], {"row": 0, "column": 1})
        self.assertEqual(buttons["Undo match"], {"row": 1, "column": 0})
        self.assertEqual(buttons["Undo checked"], {"row": 1, "column": 1})

    def test_gui_check_statement_only_finalizes_zero_difference(self):
        fake = SimpleNamespace(store=SimpleNamespace(conn=object()), refresh=Mock())
        prompts = ["Checking", "2026-10-31", "0.00", "10.00"]
        with patch.object(ui.simpledialog, "askstring", side_effect=prompts), \
             patch.object(ui, "statement_preview",
                          return_value={"difference_cents": 0, "transaction_ids": [1]}), \
             patch.object(ui.messagebox, "askyesno", return_value=True), \
             patch.object(ui.messagebox, "showinfo"), \
             patch.object(ui, "finalize_statement") as finalize:
            ui.App.check_bank(fake)
            finalize.assert_called_once_with(fake.store.conn, *prompts)
            fake.refresh.assert_called_once()

        fake.refresh.reset_mock()
        with patch.object(ui.simpledialog, "askstring", side_effect=prompts), \
             patch.object(ui, "statement_preview",
                          return_value={"difference_cents": 1, "transaction_ids": [1]}), \
             patch.object(ui.messagebox, "showwarning") as warning, \
             patch.object(ui, "finalize_statement") as finalize:
            ui.App.check_bank(fake)
            warning.assert_called_once()
            finalize.assert_not_called()
            fake.refresh.assert_not_called()

    def test_gui_undo_error_never_claims_success(self):
        fake = SimpleNamespace(store=SimpleNamespace(conn=object()), refresh=Mock())
        with patch.object(ui.simpledialog, "askstring",
                          side_effect=["Checking", "2026-10-31"]), \
             patch.object(ui.messagebox, "askyesno", return_value=True), \
             patch.object(ui, "cancel_statement",
                          side_effect=ui.BankReviewError("Evidence changed")) as cancel, \
             patch.object(ui.messagebox, "showerror") as error, \
             patch.object(ui.messagebox, "showinfo") as success:
            ui.App.cancel_bank(fake)
            cancel.assert_called_once()
            error.assert_called_once()
            success.assert_not_called()
            fake.refresh.assert_not_called()

    def test_real_tk_buttons_fit_1024x720_if_display_available(self):
        try:
            probe = tk.Tk()
            probe.withdraw()
            probe.destroy()
        except tk.TclError:
            self.skipTest("No graphical desktop; static bounds tests still apply")
        with tempfile.TemporaryDirectory() as directory:
            from core import Store
            with patch.object(ui, "_work_area", return_value=(0, 0, 1024, 720)), \
                 patch.object(ui, "Store",
                              side_effect=lambda: Store(Path(directory) / "ledger.sqlite3", "cash")):
                app = ui.App()
                try:
                    app.update_idletasks()
                    app.update()  # Process the actual Tk window-map events.
                    if not app.winfo_ismapped():
                        self.skipTest("Windows runner has no mapped GUI desktop; physical GUI remains unverified")
                    self.assertLessEqual(app.winfo_width(), 1024)
                    self.assertLessEqual(app.winfo_height(), 720)
                    buttons = {}
                    def visit(widget):
                        for child in widget.winfo_children():
                            if isinstance(child, ttk.Button):
                                buttons[child.cget("text")] = child
                            visit(child)
                    visit(app)
                    for name in ("Match selected", "Check statement", "Undo checked"):
                        with self.subTest(name=name):
                            button = buttons[name]
                            self.assertTrue(button.winfo_ismapped())
                            self.assertGreater(button.winfo_width(), 60)
                            self.assertGreaterEqual(button.winfo_rootx(), 0)
                            self.assertLessEqual(button.winfo_rootx() + button.winfo_width(), 1024)
                            self.assertLessEqual(button.winfo_rooty() + button.winfo_height(), 720)
                finally:
                    app.close()


if __name__ == "__main__":
    unittest.main()
