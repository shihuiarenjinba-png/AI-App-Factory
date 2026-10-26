import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
WF=(ROOT/".github/workflows/factory-autoloop.yml").read_text(encoding="utf-8")

class ExternalOrchestratorContract(unittest.TestCase):
    def test_requires_no_paid_ai_api(self):
        self.assertNotIn("OPENAI_API_KEY",WF)
        self.assertNotIn("openai/codex-action",WF)
        self.assertNotIn("FACTORY_ENABLED",WF)
    def test_no_faux_github_cron_agent(self):
        self.assertNotIn("schedule:",WF)
        self.assertIn("workflow_dispatch:",WF)
    def test_source_checks_still_run(self):
        self.assertIn("python -m unittest discover -s tests",WF)
        self.assertIn("python -m compileall",WF)
    def test_no_repository_write_permission(self):
        self.assertIn("contents: read",WF)
        self.assertNotIn("contents: write",WF)
    def test_explains_chatgpt_orchestration(self):
        self.assertIn("ChatGPT scheduled tasks",WF)

if __name__=="__main__":
    unittest.main()
