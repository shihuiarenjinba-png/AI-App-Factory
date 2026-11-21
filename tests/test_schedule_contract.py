import unittest
from pathlib import Path
from scripts.simulate_clock import inspect_schedule

ROOT=Path(__file__).resolve().parents[1]

class ScheduleContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source=(ROOT/".github/workflows/factory-autoloop.yml").read_text(encoding="utf-8")
    def test_four_15_minute_slots_are_theoretical_only(self):
        r=inspect_schedule(self.source)
        self.assertEqual(r["simulated_timestamps_per_24h"],96)
        self.assertFalse(r["actual_github_schedule_executed"])
        self.assertFalse(r["external_schedule_verified"])
    def test_chatgpt_owns_scheduled_development(self):
        r=inspect_schedule(self.source)
        self.assertIn("ChatGPT scheduled tasks",r["orchestrator"])
    def test_no_paid_ai_action(self):
        self.assertNotIn("OPENAI_API_KEY",self.source)
        self.assertNotIn("openai/codex-action",self.source)
    def test_no_github_ai_cron(self):
        self.assertNotIn("schedule:",self.source)
        self.assertIn("workflow_dispatch:",self.source)
    def test_github_verification_remains_read_only(self):
        self.assertIn("contents: read",self.source)
        self.assertNotIn("contents: write",self.source)
    def test_missing_dispatch_must_fail(self):
        with self.assertRaises(ValueError):inspect_schedule("name: invalid")
    def test_paid_action_must_fail(self):
        with self.assertRaises(ValueError):
            inspect_schedule(self.source+"\nopenai/codex-action@v1")
    def test_added_github_cron_must_fail(self):
        with self.assertRaises(ValueError):
            inspect_schedule(self.source+"\n  schedule:\n")
if __name__=="__main__":
    unittest.main()
