import unittest
from pathlib import Path

WORKFLOW=(Path(__file__).resolve().parents[1]/".github/workflows/factory-autoloop.yml").read_text()

class AutoLoopContract(unittest.TestCase):
    def test_four_ticks_hourly(self):
        self.assertIn("4,19,34,49 * * * *",WORKFLOW) if (Path(__file__).resolve().parents[1]/"factory/config.json").read_text().find('"app"')>0 else self.assertIn("11,26,41,56 * * * *",WORKFLOW)
    def test_audit_is_separate_job(self):
        self.assertIn("  generate:",WORKFLOW)
        self.assertIn("  audit:",WORKFLOW)
        self.assertIn("  checkpoint:",WORKFLOW)
        self.assertIn("needs.audit.result == 'success'",WORKFLOW)
    def test_persistent_work_branch(self):
        self.assertIn("HEAD:refs/heads/codex/factory-autoloop-20261026",WORKFLOW)
        self.assertNotIn("git push origin main",WORKFLOW)
        self.assertNotIn("gh pr create",WORKFLOW)
    def test_same_sha_reviewed(self):
        self.assertIn("HOLD: concurrent or unexpected code change",WORKFLOW)
        self.assertIn("ref: "+"$"+"{{ needs.generate.outputs.source_sha }}",WORKFLOW)
    def test_bounded_cost_and_failures(self):
        self.assertIn("MAX_AUTONOMOUS_STAGES_PER_DAY",WORKFLOW)
        self.assertIn("3 failing runs in 24 hours",WORKFLOW)
        self.assertIn("FACTORY_ENABLED",WORKFLOW)
    def test_offline_sandbox(self):
        for text in ("--network none","--read-only","--cap-drop ALL","--memory 512m"):
            self.assertIn(text,WORKFLOW)
    def test_only_verified_package_can_be_dispatched(self):
        self.assertIn("approved-identity.json",WORKFLOW)
        self.assertIn("gh workflow run msix-export.yml",WORKFLOW)
    def test_not_launch_store_submissions(self):
        self.assertNotIn("Partner Center submit",WORKFLOW)
        self.assertNotIn("gh pr merge",WORKFLOW)

if __name__=="__main__":
    unittest.main()
