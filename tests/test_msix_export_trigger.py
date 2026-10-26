"""Regression checks for automatic MSIX export on the active Factory work branch."""
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
WORKFLOW=(ROOT/".github/workflows/msix-export.yml").read_text(encoding="utf-8")

class MsixExportTriggerTests(unittest.TestCase):
    def test_active_factory_work_branch_is_triggered(self):
        self.assertIn('      - "codex/factory-autoloop-20261026"',WORKFLOW)
        self.assertIn('  push:',WORKFLOW)
        self.assertIn('      - "products/**"',WORKFLOW)
    def test_only_one_product_per_build(self):
        self.assertIn('expected exactly one changed product',WORKFLOW)
    def test_build_never_fabricates_store_identity(self):
        self.assertIn('approved-identity.json',WORKFLOW)
        self.assertIn('do not invent Store IDs',WORKFLOW)
    def test_windows_runner_and_binary_provenance(self):
        self.assertIn('runs-on: windows-latest',WORKFLOW)
        self.assertIn('tools/build_windows_msix.py',WORKFLOW)
        self.assertIn('tools/msix_handoff.py',WORKFLOW)
        self.assertIn('actions/upload-artifact@v4',WORKFLOW)
        self.assertIn('factory-msix-handoff-',WORKFLOW)
    def test_never_submits_to_store(self):
        self.assertNotIn('msstore publish',WORKFLOW)
        self.assertNotIn('Partner Center submit',WORKFLOW)

if __name__=="__main__":unittest.main()
