"""US-only review gate and JP/US separation regression, no display required."""
import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
US = ROOT / "products" / "us-freelance-ledger"
MAIN = US / "main.py"

class USReviewGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = MAIN.read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.source)
        cls.app = next(n for n in cls.tree.body if isinstance(n, ast.ClassDef) and n.name == "App")
        cls.tax_method = next(n for n in cls.app.body if isinstance(n, ast.FunctionDef) and n.name == "tax_assets")
        cls.confirm = next(n for n in cls.tree.body if isinstance(n, ast.FunctionDef) and n.name == "confirm_us_tax_review")

    def test_tax_calculator_requires_review_before_mode_dialog(self):
        first = self.tax_method.body[0]
        self.assertIsInstance(first, ast.If)
        self.assertIsInstance(first.test, ast.UnaryOp)
        self.assertIsInstance(first.test.operand, ast.Call)
        self.assertEqual(first.test.operand.func.id, "confirm_us_tax_review")
        self.assertIsInstance(first.body[0], ast.Return)

    def test_review_gate_decline_and_non_boolean_fail_closed(self):
        # Compile only the pure gate function, without importing tkinter or creating a window.
        fn = ast.FunctionDef(name=self.confirm.name, args=self.confirm.args,
                             body=self.confirm.body, decorator_list=[], returns=None,
                             type_comment=None)
        # Remove the default tkinter dependency and inject a fake dialog.
        fn.args.defaults = []
        module = ast.fix_missing_locations(ast.Module(body=[fn], type_ignores=[]))
        scope = {"TAX_REVIEW_TITLE": "REVIEW REQUIRED", "TAX_REVIEW_TEXT": "US only"}
        exec(compile(module, str(MAIN), "exec"), scope)
        gate = scope["confirm_us_tax_review"]
        self.assertFalse(gate(None, lambda *a, **k: False))
        self.assertFalse(gate(None, lambda *a, **k: None))
        self.assertFalse(gate(None, lambda *a, **k: "yes"))
        self.assertTrue(gate(None, lambda *a, **k: True))

    def test_us_label_and_review_result_are_visible(self):
        self.assertIn("US tax / fixed assets — REVIEW REQUIRED", self.source)
        for title in ("REVIEW REQUIRED — Sales tax", "REVIEW REQUIRED — Tax depreciation",
                      "REVIEW REQUIRED — Book depreciation"):
            self.assertIn(title, self.source)

    def test_us_does_not_import_japan_tax_rules(self):
        imports = [n for n in ast.walk(self.tree) if isinstance(n, (ast.Import, ast.ImportFrom))]
        imported = " ".join(ast.unparse(n) for n in imports).lower()
        for forbidden in ("nta", "japan_tax", "jp_ledger", "jp_accounting"):
            self.assertNotIn(forbidden, imported)
        self.assertIn("United States only", self.source)
        self.assertIn("USD", self.source)


    def test_runtime_decline_never_opens_calculator(self):
        # Execute the actual App callback without a display or real ledger.
        import copy
        from unittest.mock import Mock
        method = copy.deepcopy(self.tax_method)
        method.decorator_list = []
        method.args.defaults = []
        module = ast.fix_missing_locations(ast.Module(body=[method], type_ignores=[]))
        dialogs = Mock()
        scope = {"confirm_us_tax_review": lambda parent: False,
                 "simpledialog": dialogs, "messagebox": Mock()}
        exec(compile(module, str(MAIN), "exec"), scope)
        scope["tax_assets"](object())
        dialogs.assert_not_called()
        scope["messagebox"].showinfo.assert_not_called()

    def test_runtime_approved_sales_tax_stays_usd_and_requires_review(self):
        import copy
        from unittest.mock import Mock
        method = copy.deepcopy(self.tax_method)
        module = ast.fix_missing_locations(ast.Module(body=[method], type_ignores=[]))
        dialogs = Mock()
        dialogs.askstring.side_effect = ["sales tax", "California"]
        dialogs.askfloat.side_effect = [100.0, 7.5]
        messages = Mock()
        scope = {"confirm_us_tax_review": lambda parent: True,
                 "simpledialog": dialogs, "messagebox": messages,
                 "manual_sales_tax": lambda amount, rate: {"tax": "7.50", "gross": "107.50"}}
        exec(compile(module, str(MAIN), "exec"), scope)
        scope["tax_assets"](object())
        messages.showinfo.assert_called_once()
        title, body = messages.showinfo.call_args.args
        self.assertIn("REVIEW REQUIRED", title)
        self.assertIn("USD", body)
        self.assertIn("No posting", body)
        self.assertNotIn("JPY", body)
        self.assertNotIn("消費税", body)

    def test_unknown_calculation_mode_fails_closed_without_book_depreciation(self):
        import copy
        from unittest.mock import Mock
        method = copy.deepcopy(self.tax_method)
        module = ast.fix_missing_locations(ast.Module(body=[method], type_ignores=[]))
        dialogs = Mock()
        dialogs.askstring.return_value = "unrecognized tax calculation"
        messages = Mock()
        scope = {"confirm_us_tax_review": lambda parent: True,
                 "simpledialog": dialogs, "messagebox": messages}
        exec(compile(module, str(MAIN), "exec"), scope)
        scope["tax_assets"](object())
        dialogs.askfloat.assert_not_called()
        dialogs.askinteger.assert_not_called()
        messages.showinfo.assert_not_called()
        messages.showwarning.assert_called_once()
        self.assertIn("REVIEW REQUIRED", messages.showwarning.call_args.args[0])

    def test_us_tax_ui_never_posts_to_ledger(self):
        # All calculator branches must remain read-only; do not silently write JP/US ledger.
        prohibited = {"add", "execute", "executemany", "commit", "set_accounting_method"}
        for node in ast.walk(self.tax_method):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                self.assertNotIn(node.func.attr, prohibited)
        self.assertNotIn("JPY", ast.get_source_segment(self.source, self.tax_method))

    def test_us_runtime_dependency_imports_are_local_and_not_jp(self):
        # Inspect all US product Python modules, not only the UI entrypoint.
        for path in US.glob("*.py"):
            with self.subTest(module=path.name):
                tree = ast.parse(path.read_text(encoding="utf-8"))
                imports = [n for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))]
                names = " ".join(ast.unparse(n) for n in imports).lower()
                for forbidden in ("japan_tax", "jp_ledger", "jp_accounting", "nta"):
                    self.assertNotIn(forbidden, names)

if __name__ == "__main__":
    unittest.main()
