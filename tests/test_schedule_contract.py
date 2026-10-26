import unittest
from pathlib import Path
from scripts.simulate_clock import inspect_schedule

ROOT=Path(__file__).resolve().parents[1]

class ScheduleContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source=(ROOT/".github/workflows/factory-cycle.yml").read_text(encoding="utf-8")
    def test_96_ticks_every_15_minutes(self):
        report=inspect_schedule(self.source)
        self.assertEqual(report["simulated_timestamps_per_24h"],96)
        self.assertFalse(report["actual_github_schedule_executed"])
    def test_concurrency_no_cancellation(self):
        self.assertIn("cancel-in-progress: false",self.source)
        self.assertIn("concurrency:",self.source)
    def test_draft_pr_only(self):
        self.assertIn("gh pr create --draft",self.source)
        self.assertNotIn("gh pr merge",self.source)
        self.assertNotIn("git push origin main",self.source)
    def test_keys_only_in_dedicated_job(self):
        self.assertIn("permission-profile: \":workspace\"",self.source)
        self.assertIn("OPENAI_API_KEY",self.source)
    def test_product_audit_is_isolated(self):
        for segment in ("--network none","--read-only","--cap-drop ALL","--pids-limit 64"):
            self.assertIn(segment,self.source)
    def test_guard_rejects_staged_changes(self):
        self.assertIn("git diff --cached --exit-code",self.source)
        self.assertIn("git diff --exit-code",self.source)
    def test_tests_cannot_succeed_with_zero_cases(self):
        self.assertIn("Ran [1-9][0-9]* tests? in",self.source)

if __name__=="__main__":unittest.main()
