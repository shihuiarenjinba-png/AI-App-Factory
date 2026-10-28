"""Exercise Focus Session Desk through the real Factory controller in isolation.

This does not promote the checked-out branch or claim Windows GUI validation.
The production candidate is kept untouched while the test executes in a
temporary Factory root. The source under test is the checked-in candidate.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import factory

ROOT = Path(__file__).resolve().parents[1]
SLUG = "focus-session-desk"


class FocusCohortLifecycleTests(unittest.TestCase):
    def test_real_controller_research_build_and_candidate_tests(self):
        proposal_path = ROOT / ".candidate" / "proposal.json"
        if not proposal_path.is_file():
            proposal_path = ROOT / "proposals" / (SLUG + ".json")
        product_path = ROOT / ".candidate" / "product"
        if not product_path.is_dir():
            product_path = ROOT / "products" / SLUG
        if not proposal_path.is_file() or not product_path.is_dir():
            self.fail("Focus research proposal and real product candidate are required")
        proposal = json.loads(proposal_path.read_text(encoding="utf-8"))
        self.assertEqual(proposal["slug"], SLUG)
        self.assertGreaterEqual(len(proposal["evidence_urls"]), 2)

        with tempfile.TemporaryDirectory(prefix="focus-factory-lifecycle-") as temp:
            root = Path(temp)
            for name in ("AGENTS.md",):
                shutil.copyfile(ROOT / name, root / name)
            (root / "factory").mkdir()
            (root / ".runtime").mkdir()
            (root / ".candidate").mkdir()
            shutil.copyfile(ROOT / "factory" / "config.json", root / "factory" / "config.json")
            (root / "factory" / "state.json").write_text(json.dumps({
                "schema": 1, "kind": "app", "stage": "research",
                "cycle": 1, "revision": 0, "slug": None
            }), encoding="utf-8")
            (root / ".runtime" / "market.json").write_text(json.dumps({
                "schema": 1, "kind": "app",
                "signals": [{"url": u, "title": "reviewed issue evidence", "excerpt": ""}
                            for u in proposal["evidence_urls"]]
            }), encoding="utf-8")
            shutil.copyfile(proposal_path, root / ".candidate" / "proposal.json")

            # Actual controller calls, not a fabricated stage transition.
            self.assertEqual(factory.plan(root)["stage"], "research")
            self.assertEqual(factory.validate(root), {"stage": "research", "slug": SLUG})
            self.assertEqual(factory.promote(root), {"stage": "research", "slug": SLUG})
            self.assertFalse((root / ".candidate" / "proposal.json").exists())
            self.assertTrue((root / "proposals" / (SLUG + ".json")).is_file())

            shutil.copytree(product_path, root / ".candidate" / "product")
            self.assertEqual(factory.plan(root)["stage"], "build")
            self.assertEqual(factory.validate(root), {"stage": "build", "slug": SLUG})

            # Run the candidate's own tests, not merely syntax/AST checks.
            env = dict(os.environ)
            env["PYTHONDONTWRITEBYTECODE"] = "1"
            result = subprocess.run(
                [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
                cwd=root / ".candidate" / "product",
                env=env, capture_output=True, text=True, timeout=90, check=False
            )
            self.assertEqual(result.returncode, 0, result.stdout + "\n" + result.stderr)
            import re
            count = re.search(r"Ran (\\d+) tests in", result.stderr)
            self.assertIsNotNone(count, result.stderr)
            self.assertGreaterEqual(int(count.group(1)), 18)
            print("FOCUS_CANDIDATE_TESTS=" + count.group(1)
                  + " PASS (headless; not Windows GUI QA)")
            self.assertNotIn("skipped=", result.stderr)
            self.assertNotIn("expected failures=", result.stderr)

            self.assertEqual(factory.promote(root), {"stage": "build", "slug": SLUG})
            promoted = root / "products" / SLUG
            self.assertTrue((promoted / "main.py").is_file())
            self.assertTrue((promoted / "tests" / "test_smoke.py").is_file())
            self.assertEqual(json.loads((promoted / "manifest.json").read_text(encoding="utf-8")),
                             {"slug": SLUG, "kind": "app", "entry": "main.py"})
            self.assertEqual((promoted / "main.py").read_bytes(),
                             (product_path / "main.py").read_bytes())
            state = json.loads((root / "factory" / "state.json").read_text(encoding="utf-8"))
            self.assertEqual((state["stage"], state["revision"], state["slug"]),
                             ("improve", 1, SLUG))


if __name__ == "__main__":
    unittest.main()
