"""Market-fit MSIX gate regression tests: missing, false and stale evidence HOLD."""
import json
from datetime import date, timedelta
from pathlib import Path
import subprocess
import tempfile
import unittest

from tools.market_fit_gate import MarketFitHold, assert_market_fit


class MarketFitGateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.slug = "sample-desk"
        self.product = self.root / "products" / self.slug
        self.product.mkdir(parents=True)
        (self.product / "main.py").write_text("print('original')\n", encoding="utf-8")
        self.git("init", "-q")
        self.git("config", "user.email", "ci@example.invalid")
        self.git("config", "user.name", "CI")
        self.git("add", ".")
        self.git("commit", "-qm", "baseline source")
        baseline = self.git("rev-parse", "HEAD")
        self.as_date = date.today()
        self.today = self.as_date.isoformat()
        self.recent = (self.as_date - timedelta(days=5)).isoformat()
        self.document = {
            "schema_version": "app5-market-fit-v1",
            "researched_on": self.today,
            "slug": self.slug,
            "decision": "MARKET_FIT_PASS",
            "commercial_msix_allowed": True,
            "feature_expansion_allowed": True,
            "direct_competitors": [
                {"name": "competitor A", "source": "https://vendor-a.test/pricing", "checked": self.today},
                {"name": "competitor B", "source": "https://vendor-b.test/pricing", "checked": self.today},
                {"name": "competitor C", "source": "https://vendor-c.test/pricing", "checked": self.today},
            ],
            "free_alternatives": [
                {"name": "free A", "source": "https://free-a.test/", "checked": self.today},
                {"name": "free B", "source": "https://free-b.test/", "checked": self.today},
                {"name": "free C", "source": "https://free-c.test/", "checked": self.today},
            ],
            "paid_price_range": "USD 10-50 one time",
            "buyer_persona": "Windows local-only professional operator",
            "why_pay_statement": "A complete local handoff report avoids manual reconciliation.",
            "common_review_complaints": [{
                "complaint": "Difficult export workflow",
                "source": "https://forum.test/review/123",
                "post_date": self.recent,
            }],
            "store_search_keywords": ["offline report", "Windows local"],
            "price_hypothesis": {"one_time_jpy": 900},
            "go_criteria": {
                "one_sentence_why_pay": True,
                "two_distinctions_from_free_alternatives": True,
                "addresses_review_complaint": True,
                "feasible_windows_local": True,
                "no_saas_dependency": True,
                "minimum_score_70": True,
            },
            "scoring": {
                "problem_severity": {"score": 16, "max": 20},
                "differentiation": {"score": 16, "max": 20},
                "willingness_to_pay": {"score": 16, "max": 20},
                "usability": {"score": 12, "max": 15},
                "trust_privacy": {"score": 8, "max": 10},
                "discoverability": {"score": 8, "max": 10},
                "implementation_risk": {"score": 4, "max": 5},
                "total": 80,
                "max": 100,
            },
            "baseline_sha": baseline,
        }
        self.path = self.root / "docs" / "market" / (self.slug + ".market-fit.json")
        self.path.parent.mkdir(parents=True)
        self.write_doc()
        self.commit("reviewed market fit")

    def git(self, *args):
        p = subprocess.run(["git", *args], cwd=self.root, check=True,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           text=True)
        return p.stdout.strip()

    def commit(self, message):
        self.git("add", ".")
        self.git("commit", "-qm", message)

    def write_doc(self):
        self.path.write_text(json.dumps(self.document, indent=2) + "\n", encoding="utf-8")

    def test_valid_pass_with_unchanged_source(self):
        self.assertEqual(assert_market_fit(self.root, self.slug)["scoring"]["total"], 80)

    def test_uncommitted_market_pass_edit_holds(self):
        # A local PASS claim must not be accepted before the reviewed JSON
        # is committed; otherwise a direct builder could bypass review.
        self.document["why_pay_statement"] = "Unreviewed new commercial claim"
        self.write_doc()
        with self.assertRaisesRegex(MarketFitHold, "uncommitted or staged"):
            assert_market_fit(self.root, self.slug)

    def test_staged_market_pass_edit_holds(self):
        self.document["why_pay_statement"] = "Staged unreviewed claim"
        self.write_doc()
        self.git("add", "docs/market")
        with self.assertRaisesRegex(MarketFitHold, "uncommitted or staged"):
            assert_market_fit(self.root, self.slug)

    def test_untracked_market_pass_doc_holds(self):
        self.git("rm", "--cached", "docs/market/" + self.slug + ".market-fit.json")
        with self.assertRaisesRegex(MarketFitHold, "not tracked"):
            assert_market_fit(self.root, self.slug)

    def test_missing_market_doc_holds(self):
        self.path.unlink()
        with self.assertRaisesRegex(MarketFitHold, "missing"):
            assert_market_fit(self.root, self.slug)

    def test_existing_market_hold_cannot_be_overridden_by_identity(self):
        self.document["decision"] = "MARKET_FIT_HOLD"
        self.write_doc()
        self.commit("review altered market decision")
        with self.assertRaisesRegex(MarketFitHold, "MARKET_FIT_PASS"):
            assert_market_fit(self.root, self.slug)

    def test_score_79_holds(self):
        self.document["scoring"]["discoverability"]["score"] = 7
        self.document["scoring"]["total"] = 79
        self.write_doc()
        self.commit("review altered market decision")
        with self.assertRaisesRegex(MarketFitHold, "below 80"):
            assert_market_fit(self.root, self.slug)

    def test_forged_total_holds(self):
        self.document["scoring"]["willingness_to_pay"]["score"] = 1
        self.write_doc()
        self.commit("review altered market decision")
        with self.assertRaisesRegex(MarketFitHold, "inconsistent"):
            assert_market_fit(self.root, self.slug)

    def test_go_condition_false_holds(self):
        self.document["go_criteria"]["two_distinctions_from_free_alternatives"] = False
        self.write_doc()
        self.commit("review altered market decision")
        with self.assertRaisesRegex(MarketFitHold, "GO conditions"):
            assert_market_fit(self.root, self.slug)

    def test_false_commercial_permission_holds(self):
        self.document["commercial_msix_allowed"] = False
        self.write_doc()
        self.commit("review altered market decision")
        with self.assertRaisesRegex(MarketFitHold, "not explicitly allowed"):
            assert_market_fit(self.root, self.slug)

    def test_source_change_after_review_holds(self):
        (self.product / "main.py").write_text("print('changed')\n", encoding="utf-8")
        self.commit("product changed")
        with self.assertRaisesRegex(MarketFitHold, "source changed"):
            assert_market_fit(self.root, self.slug)

    def test_uncommitted_source_change_holds(self):
        (self.product / "main.py").write_text("print('dirty')\\n", encoding="utf-8")
        with self.assertRaisesRegex(MarketFitHold, "uncommitted product"):
            assert_market_fit(self.root, self.slug)

    def test_staged_source_change_holds(self):
        (self.product / "main.py").write_text("print('staged')\\n", encoding="utf-8")
        self.git("add", "products")
        with self.assertRaisesRegex(MarketFitHold, "staged product"):
            assert_market_fit(self.root, self.slug)

    def test_untracked_product_code_holds(self):
        (self.product / "unexpected.py").write_text("print('new')\\n", encoding="utf-8")
        with self.assertRaisesRegex(MarketFitHold, "untracked product"):
            assert_market_fit(self.root, self.slug)

    def test_uncommitted_identity_return_is_excluded(self):
        store = self.product / "store"
        store.mkdir()
        (store / "approved-identity.json").write_text('{"test": true}\\n', encoding="utf-8")
        self.assertEqual(assert_market_fit(self.root, self.slug)["slug"], self.slug)

    def test_identity_return_does_not_invalidate_product_source(self):
        store = self.product / "store"
        store.mkdir()
        (store / "approved-identity.json").write_text('{"test": true}\n', encoding="utf-8")
        self.commit("Identity return only")
        self.assertEqual(assert_market_fit(self.root, self.slug)["slug"], self.slug)

    def test_wrong_baseline_holds(self):
        self.document["baseline_sha"] = "0" * 40
        self.write_doc()
        self.commit("review altered market decision")
        with self.assertRaisesRegex(MarketFitHold, "not an ancestor"):
            assert_market_fit(self.root, self.slug)

    def test_invalid_score_type_holds(self):
        self.document["scoring"]["problem_severity"]["score"] = True
        self.write_doc()
        self.commit("review altered market decision")
        with self.assertRaisesRegex(MarketFitHold, "invalid scoring"):
            assert_market_fit(self.root, self.slug)

    def test_bad_slug_and_missing_evidence_holds(self):
        with self.assertRaises(MarketFitHold):
            assert_market_fit(self.root, "../unsafe")
        self.document["slug"] = "other-product"
        self.write_doc()
        with self.assertRaises(MarketFitHold):
            assert_market_fit(self.root, self.slug)

    def test_symlink_market_document_holds_when_supported(self):
        self.path.unlink()
        try:
            self.path.symlink_to(self.root / "other.json")
        except (OSError, NotImplementedError):
            self.skipTest("symlink creation restricted")
        with self.assertRaisesRegex(MarketFitHold, "linked"):
            assert_market_fit(self.root, self.slug)


    def test_competitor_names_without_sources_hold(self):
        self.document["direct_competitors"] = ["A", "B", "C"]
        self.write_doc()
        self.commit("invalid string-only competitor claims")
        with self.assertRaisesRegex(MarketFitHold, "competitor source"):
            assert_market_fit(self.root, self.slug)

    def test_competitor_missing_url_holds(self):
        self.document["direct_competitors"][0].pop("source")
        self.write_doc()
        self.commit("competitor without source")
        with self.assertRaisesRegex(MarketFitHold, "competitor source"):
            assert_market_fit(self.root, self.slug)

    def test_competitor_invalid_date_holds(self):
        self.document["direct_competitors"][0]["checked"] = "2026-02-31"
        self.write_doc()
        self.commit("invalid competitor date")
        with self.assertRaisesRegex(MarketFitHold, "competitor source"):
            assert_market_fit(self.root, self.slug)

    def test_duplicate_competitor_names_hold(self):
        self.document["direct_competitors"][1]["name"] = "competitor A"
        self.write_doc()
        self.commit("duplicate competitor")
        with self.assertRaisesRegex(MarketFitHold, "distinct competitors"):
            assert_market_fit(self.root, self.slug)

    def test_duplicate_free_alternatives_hold(self):
        self.document["free_alternatives"][1]["name"] = "free A"
        self.write_doc()
        self.commit("duplicate free alternatives")
        with self.assertRaisesRegex(MarketFitHold, "distinct free alternatives"):
            assert_market_fit(self.root, self.slug)

    def test_review_complaint_without_date_holds(self):
        self.document["common_review_complaints"][0].pop("post_date")
        self.write_doc()
        self.commit("undated complaint")
        with self.assertRaisesRegex(MarketFitHold, "dated, source-linked"):
            assert_market_fit(self.root, self.slug)

    def test_review_complaint_without_source_holds(self):
        self.document["common_review_complaints"][0]["source"] = "not-a-url"
        self.write_doc()
        self.commit("unsourced complaint")
        with self.assertRaisesRegex(MarketFitHold, "dated, source-linked"):
            assert_market_fit(self.root, self.slug)

    def test_missing_research_date_holds(self):
        self.document.pop("researched_on")
        self.write_doc()
        self.commit("missing research date")
        with self.assertRaisesRegex(MarketFitHold, "research date"):
            assert_market_fit(self.root, self.slug)

    def test_string_only_free_alternatives_hold(self):
        self.document["free_alternatives"] = ["free A", "free B", "free C"]
        self.write_doc()
        self.commit("unsourced free alternatives")
        with self.assertRaisesRegex(MarketFitHold, "free alternative source"):
            assert_market_fit(self.root, self.slug)

    def test_free_alternative_missing_source_holds(self):
        self.document["free_alternatives"][0].pop("source")
        self.write_doc()
        self.commit("missing free alternative source")
        with self.assertRaisesRegex(MarketFitHold, "free alternative source"):
            assert_market_fit(self.root, self.slug)

    def test_stale_free_alternative_check_holds(self):
        self.document["free_alternatives"][0]["checked"] = (
            self.as_date - timedelta(days=181)).isoformat()
        self.write_doc()
        self.commit("stale free alternative")
        with self.assertRaisesRegex(MarketFitHold, "free alternative source"):
            assert_market_fit(self.root, self.slug)

    def test_future_competitor_check_holds(self):
        self.document["direct_competitors"][0]["checked"] = (
            self.as_date + timedelta(days=3)).isoformat()
        self.write_doc()
        self.commit("future competitor date")
        with self.assertRaisesRegex(MarketFitHold, "competitor source"):
            assert_market_fit(self.root, self.slug)

    def test_stale_competitor_check_holds(self):
        self.document["direct_competitors"][0]["checked"] = (
            self.as_date - timedelta(days=181)).isoformat()
        self.write_doc()
        self.commit("stale competitor check")
        with self.assertRaisesRegex(MarketFitHold, "competitor source"):
            assert_market_fit(self.root, self.slug)

    def test_stale_research_date_holds(self):
        self.document["researched_on"] = (
            self.as_date - timedelta(days=181)).isoformat()
        self.write_doc()
        self.commit("stale research")
        with self.assertRaisesRegex(MarketFitHold, "research date"):
            assert_market_fit(self.root, self.slug)

    def test_future_research_date_holds(self):
        self.document["researched_on"] = (
            self.as_date + timedelta(days=3)).isoformat()
        self.write_doc()
        self.commit("future research")
        with self.assertRaisesRegex(MarketFitHold, "research date"):
            assert_market_fit(self.root, self.slug)

    def test_future_review_complaint_date_holds(self):
        self.document["common_review_complaints"][0]["post_date"] = (
            self.as_date + timedelta(days=3)).isoformat()
        self.write_doc()
        self.commit("future complaint date")
        with self.assertRaisesRegex(MarketFitHold, "dated, source-linked"):
            assert_market_fit(self.root, self.slug)

    def test_workflow_and_direct_builder_both_call_gate(self):
        root = Path(__file__).resolve().parents[1]
        selector = (root / "tools/msix_push_product.py").read_text(encoding="utf-8")
        builder = (root / "tools/build_windows_msix.py").read_text(encoding="utf-8")
        self.assertIn('assert_market_fit(Path("."), slug)', selector)
        self.assertIn("MarketFitHold", selector)
        self.assertIn("assert_market_fit(repo_root, slug)", builder)


if __name__ == "__main__":
    unittest.main()
