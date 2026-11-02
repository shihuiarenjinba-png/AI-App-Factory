"""US-only first-run layout regression; no tax decisions or external data."""
import ast
import importlib.util
import sys
import tempfile
import tkinter as tk
from tkinter import ttk
import unittest
from pathlib import Path
from unittest.mock import patch

PRODUCT = Path(__file__).resolve().parents[1] / "products" / "us-freelance-ledger"
sys.path.insert(0, str(PRODUCT))
spec = importlib.util.spec_from_file_location("us_ledger_layout", PRODUCT / "main.py")
ui = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ui)


class FirstRunLayoutTests(unittest.TestCase):
    def test_taskbar_work_area_1024x720_never_starts_offscreen(self):
        geometry, minimum_width, minimum_height = ui._window_bounds((0, 0, 1024, 720))
        self.assertEqual(geometry, "1000x696+12+12")
        self.assertEqual((minimum_width, minimum_height), (900, 620))
        self.assertLessEqual(12 + 1000, 1024)
        self.assertLessEqual(12 + 696, 720)
        self.assertNotIn("1100x720", geometry)

    def test_offset_work_area_restart_and_invalid_dimensions(self):
        for _ in range(2):
            self.assertEqual(ui._window_bounds((0, 48, 1024, 720))[0],
                             "1000x696+12+60")
        for area in ((0, 0, 1024, 0), (0, 0, -1, 720)):
            with self.subTest(area=area), self.assertRaises(ValueError):
                ui._window_bounds(area)

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
