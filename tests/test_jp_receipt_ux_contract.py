"""Headless UX contract checks; actual Windows rendering remains unverified."""
import ast
import unittest
from pathlib import Path

MAIN = Path(__file__).resolve().parents[1] / "products" / "jp-bookkeeping-desk" / "main.py"

class BeginnerReceiptUXContract(unittest.TestCase):
    def test_three_step_workflow_and_review_action(self):
        source = MAIN.read_text(encoding="utf-8")
        module = ast.parse(source)
        app = next(n for n in module.body if isinstance(n, ast.ClassDef) and n.name == "App")
        methods = {n.name for n in app.body if isinstance(n, ast.FunctionDef)}
        self.assertTrue({"import_receipts", "view_receipts", "post", "lookup_help"}.issubset(methods))
        self.assertIn("import_receipts_verified(self.s.conn,paths)", source)
        self.assertIn("list_receipts_verified(self.s.conn)", source)
        self.assertIn("証憑を追加 → 科目と金額を確認 → 記帳", source)
        self.assertIn("自動読取や自動記帳は行いません", source)
        self.assertIn('self.geometry("1024x768")', source)
        self.assertIn("wraplength=940", source)

if __name__ == "__main__":
    unittest.main()
