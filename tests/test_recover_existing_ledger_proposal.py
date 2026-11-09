"""Regression tests for non-destructive, evidence-bound proposal restoration."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / "tools" / "recover_existing_ledger_proposal.py"
spec = importlib.util.spec_from_file_location("ledger_recovery", SOURCE)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

URLS = [
    "https://github.com/example-one/project-a/issues/12",
    "https://github.com/example-two/project-b/issues/34",
]
PROPOSAL = {
    "slug": "us-freelance-ledger",
    "title": "Offline ledger bank reconciliation",
    "customer_problem": "Review bank entries without silently changing ledger data.",
    "audience": "Freelancers who review imported bank transactions locally.",
    "differentiation": "Human review and explicit file preservation by default.",
    "scope": ["Read-only bank CSV preview", "Manual matching and review report"],
    "evidence_urls": URLS,
}
SUMMARY = "US Freelance Ledger customer demand for local bank matching and competitor pricing"
MARKET = {"schema": 1, "kind": "app", "signals": [{"url": u, "summary": SUMMARY} for u in URLS]}

def fake_github(url):
    if "/collaborators/" in url and url.endswith("/permission"):
        return {"permission": "write"}
    issue_url = url.replace("https://api.github.com/repos/", "https://github.com/").replace("/issues/", "/issues/").split("/comments?")[0]
    if "/comments?" in url:
        return [{"user": {"login": "trusted-reviewer"}, "body": "APPROVED MARKET EVIDENCE: us-freelance-ledger", "created_at": "2026-11-01T00:00:00Z"}]
    return {"html_url": issue_url, "body": "US Freelance Ledger customer demand and market competitor analysis. " + SUMMARY}

class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        product = self.root / "products/us-freelance-ledger"
        product.mkdir(parents=True)
        (product / "manifest.json").write_text(json.dumps({
            "slug": "us-freelance-ledger", "kind": "app",
            "market": "US", "currency": "USD"}), encoding="utf-8")
        factory = self.root / "factory"
        factory.mkdir()
        (factory / "state.json").write_bytes(b'{"slug":"offline-image-inventory-desk"}\n')
        self.proposal = self.root / "candidate.json"
        self.market = self.root / "market.json"
        self.write_inputs()
        self.state_before = (factory / "state.json").read_bytes()

    def write_inputs(self, proposal=None, market=None):
        self.proposal.write_text(json.dumps(PROPOSAL if proposal is None else proposal), encoding="utf-8")
        self.market.write_text(json.dumps(MARKET if market is None else market), encoding="utf-8")

    def restore(self, dry_run=False, fetch=fake_github, approved_by="trusted-reviewer"):
        return mod.restore(self.root, self.proposal, self.market, dry_run, approved_by, fetch)

    def test_rejects_unauthorized_approver(self):
        def read_only(url):
            if "/collaborators/" in url:
                return {"permission": "read"}
            return fake_github(url)
        with self.assertRaisesRegex(ValueError, "permission"):
            self.restore(fetch=read_only)
        self.assertFalse((self.root / "proposals/us-freelance-ledger.json").exists())

    def test_rejects_missing_permission_response(self):
        def missing_permission(url):
            if "/collaborators/" in url:
                raise OSError("403")
            return fake_github(url)
        with self.assertRaisesRegex(ValueError, "unavailable"):
            self.restore(fetch=missing_permission)

    def test_rejects_empty_market_summary(self):
        bad = {"schema": 1, "kind": "app", "signals": [
            {"url": u, "summary": ""} for u in URLS]}
        self.write_inputs(market=bad)
        with self.assertRaisesRegex(ValueError, "summary missing"):
            self.restore()

    def test_rejects_fabricated_market_summary(self):
        bad = {"schema": 1, "kind": "app", "signals": [
            {"url": u, "summary": "Fabricated competitor pricing claims without any issue support"} for u in URLS]}
        self.write_inputs(market=bad)
        with self.assertRaisesRegex(ValueError, "not found"):
            self.restore()

    def test_rejects_invalid_market_url(self):
        bad = {"schema": 1, "kind": "app", "signals": [
            {"url": "https://example.invalid/fake", "summary": SUMMARY},
            {"url": URLS[1], "summary": SUMMARY}]}
        self.write_inputs(market=bad)
        with self.assertRaisesRegex(ValueError, "invalid GitHub"):
            self.restore()

    def test_rejects_nonexistent_issue(self):
        def missing(url):
            raise OSError("404")
        with self.assertRaisesRegex(ValueError, "unavailable"):
            self.restore(fetch=missing)

    def test_rejects_unapproved_issue(self):
        def no_approval(url):
            if "/comments?" in url:
                return []
            return fake_github(url)
        with self.assertRaisesRegex(ValueError, "approval"):
            self.restore(fetch=no_approval)

    def test_rejects_irrelevant_issue(self):
        def irrelevant(url):
            result = fake_github(url)
            if isinstance(result, dict):
                result["body"] = "Unrelated technical bug"
            return result
        with self.assertRaisesRegex(ValueError, "product"):
            self.restore(fetch=irrelevant)

    def test_rejects_missing_trusted_actor(self):
        with self.assertRaisesRegex(ValueError, "actor"):
            self.restore(approved_by=None)

    def test_restore_preserves_factory_state_and_product(self):
        manifest = (self.root / "products/us-freelance-ledger/manifest.json").read_bytes()
        target = self.restore()
        self.assertEqual(Path(target).name, "us-freelance-ledger.json")
        self.assertEqual((self.root / "factory/state.json").read_bytes(), self.state_before)
        self.assertEqual((self.root / "products/us-freelance-ledger/manifest.json").read_bytes(), manifest)

    def test_rejects_symlinked_output_directory(self):
        external = self.root / "external"
        external.mkdir()
        (self.root / "proposals").symlink_to(external, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "symlink proposal directory"):
            self.restore()
        self.assertFalse((external / "us-freelance-ledger.json").exists())

    def test_dry_run_never_writes(self):
        self.assertEqual(self.restore(True), "VALIDATED_ONLY")
        self.assertFalse((self.root / "proposals/us-freelance-ledger.json").exists())

    def test_refuses_overwrite(self):
        target = self.root / "proposals/us-freelance-ledger.json"
        target.parent.mkdir()
        target.write_bytes(b"ORIGINAL")
        with self.assertRaisesRegex(ValueError, "overwritten"):
            self.restore()
        self.assertEqual(target.read_bytes(), b"ORIGINAL")

    def test_rejects_unverified_market_evidence(self):
        bad = dict(PROPOSAL, evidence_urls=[URLS[0], "https://github.com/fake/repo/issues/1"])
        self.write_inputs(proposal=bad)
        with self.assertRaisesRegex(ValueError, "absent"):
            self.restore()

    def test_rejects_wrong_slug(self):
        self.write_inputs(proposal=dict(PROPOSAL, slug="offline-image-inventory-desk"))
        with self.assertRaisesRegex(ValueError, "slug"):
            self.restore()

    def test_rejects_single_repository(self):
        other = "https://github.com/example-one/project-a/issues/13"
        self.write_inputs(
            proposal=dict(PROPOSAL, evidence_urls=[URLS[0], other]),
            market={"schema": 1, "kind": "app", "signals": [{"url": URLS[0]}, {"url": other}]},
        )
        with self.assertRaisesRegex(ValueError, "repositories"):
            self.restore()

    def test_rejects_missing_market_data(self):
        self.write_inputs(market={"schema": 1, "kind": "app", "signals": []})
        with self.assertRaisesRegex(ValueError, "signals"):
            self.restore()

if __name__ == "__main__":
    unittest.main()
