"""Regression checks for automatic MSIX export on the active Factory work branch."""
import unittest
from fnmatch import fnmatchcase
from pathlib import Path

from tools.msix_export_ref_guard import validate_export_context

ROOT=Path(__file__).resolve().parents[1]
WORKFLOW=(ROOT/".github/workflows/msix-export.yml").read_text(encoding="utf-8")

class MsixExportTriggerTests(unittest.TestCase):
    def test_identity_return_on_any_codex_work_branch_triggers_export(self):
        # Identity routing writes to per-product work branches, not only the
        # original Factory bootstrap branch. Push filters must include them.
        self.assertIn('      - "codex/**"',WORKFLOW)
        self.assertIn('  push:',WORKFLOW)
        self.assertIn('      - "products/**"',WORKFLOW)
        for branch in ("codex/factory-autoloop-20261026",
                       "codex/app-package-handoff-20261026",
                       "codex/app-msix-container-gate-20261027",
                       "codex/products/demo/identity-return"):
            with self.subTest(branch=branch):
                self.assertTrue(fnmatchcase(branch, "codex/**"))
        for branch in ("main", "release", "release/v1"):
            with self.subTest(branch=branch):
                self.assertFalse(fnmatchcase(branch, "codex/**"))
    def test_manual_dispatch_cannot_export_main_release_or_tags(self):
        rejected = (
            ("workflow_dispatch", "refs/heads/main", "branch"),
            ("workflow_dispatch", "refs/heads/release", "branch"),
            ("workflow_dispatch", "refs/heads/release/v1", "branch"),
            ("workflow_dispatch", "refs/tags/v1.0", "tag"),
            ("push", "refs/heads/main", "branch"),
            ("pull_request", "refs/heads/codex/example", "branch"),
            ("workflow_dispatch", "refs/heads/codex/../main", "branch"),
            ("workflow_dispatch", "refs/heads/codex//test", "branch"),
            ("workflow_dispatch", "refs/heads/codex/evil\\nref", "branch"),
            ("workflow_dispatch", "", ""),
        )
        for event, ref, ref_type in rejected:
            with self.subTest(event=event, ref=ref):
                with self.assertRaises(ValueError):
                    validate_export_context(event, ref, ref_type)

    def test_work_branch_export_is_allowed_for_push_and_dispatch(self):
        for event in ("push", "workflow_dispatch"):
            for branch in ("codex/factory-autoloop-20261026",
                           "codex/app-msix-export-work-branches-20261027",
                           "codex/products/demo/identity-return"):
                with self.subTest(event=event, branch=branch):
                    self.assertEqual(
                        validate_export_context(event, "refs/heads/" + branch, "branch"),
                        branch,
                    )

    def test_runtime_guard_precedes_any_build_or_product_selection(self):
        self.assertIn("run: python tools/msix_export_ref_guard.py", WORKFLOW)
        self.assertLess(
            WORKFLOW.index("run: python tools/msix_export_ref_guard.py"),
            WORKFLOW.index("Select exactly one changed product"),
        )
        self.assertLess(
            WORKFLOW.index("run: python tools/msix_export_ref_guard.py"),
            WORKFLOW.index("Build MSIX on Windows"),
        )

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
