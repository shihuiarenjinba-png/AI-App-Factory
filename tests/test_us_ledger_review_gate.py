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

if __name__ == "__main__":
    unittest.main()
