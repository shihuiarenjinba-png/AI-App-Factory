"""Fail-closed APP5 market-fit precondition for MSIX packaging.

A market research document is evidence, not permission by itself. A PASS must
match the unchanged reviewed product source and the full owner-defined rubric.
This gate never promotes a candidate, binds Identity or submits to the Store.
"""
from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import urlsplit

SLUG = re.compile(r"[a-z][a-z0-9-]{3,39}\Z")
SHA40 = re.compile(r"[0-9a-f]{40}\Z")
WEIGHTS = {
    "problem_severity": 20,
    "differentiation": 20,
    "willingness_to_pay": 20,
    "usability": 15,
    "trust_privacy": 10,
    "discoverability": 10,
    "implementation_risk": 5,
}
GO_FLAGS = (
    "one_sentence_why_pay",
    "two_distinctions_from_free_alternatives",
    "addresses_review_complaint",
    "feasible_windows_local",
    "no_saas_dependency",
    "minimum_score_70",
)


def _valid_date(value: object) -> bool:
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return False
    try:
        return date.fromisoformat(value).isoformat() == value
    except ValueError:
        return False


def _valid_evidence_url(value: object) -> bool:
    if not isinstance(value, str) or not 12 <= len(value) <= 2048:
        return False
    try:
        parsed = urlsplit(value)
    except ValueError:
        return False
    return (parsed.scheme == "https" and bool(parsed.hostname)
            and parsed.username is None and parsed.password is None
            and parsed.hostname not in {"localhost", "example.com", "example.invalid"})


class MarketFitHold(ValueError):
    """A product is not authorized for commercial MSIX packaging."""


def _git(root: Path, *args: str) -> bool:
    try:
        result = subprocess.run(
            ["git", *args], cwd=root, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, timeout=15, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise MarketFitHold("cannot verify reviewed source history") from exc
    return result.returncode == 0


def assert_market_fit(root: Path, slug: str) -> dict:
    """Validate a reviewed, source-bound market decision; otherwise HOLD."""
    if not isinstance(slug, str) or not SLUG.fullmatch(slug):
        raise MarketFitHold("invalid product slug")
    root = Path(root)
    docs = root / "docs"
    market_dir = docs / "market"
    path = market_dir / (slug + ".market-fit.json")
    if any(p.is_symlink() for p in (docs, market_dir, path)):
        raise MarketFitHold("linked market evidence prohibited")
    if not path.is_file() or path.stat().st_size > 65536:
        raise MarketFitHold("market-fit evidence missing or oversized")
    # A local builder must not accept a self-promoted, uncommitted PASS.
    # Require the reviewed market decision to be present in HEAD and clean
    # in both the index and worktree, just like the product source.
    evidence_path = "docs/market/" + slug + ".market-fit.json"
    if not _git(root, "ls-files", "--error-unmatch", "--", evidence_path):
        raise MarketFitHold("market-fit evidence is not tracked")
    if not _git(root, "diff", "--quiet", "HEAD", "--", evidence_path):
        raise MarketFitHold("market-fit evidence has uncommitted or staged edits")
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise MarketFitHold("invalid market-fit JSON") from exc
    if not isinstance(doc, dict) or doc.get("schema_version") != "app5-market-fit-v1":
        raise MarketFitHold("unrecognized market-fit schema")
    if doc.get("slug") != slug or doc.get("decision") != "MARKET_FIT_PASS":
        raise MarketFitHold("product has no matching MARKET_FIT_PASS")
    if doc.get("commercial_msix_allowed") is not True:
        raise MarketFitHold("commercial MSIX is not explicitly allowed")
    if doc.get("feature_expansion_allowed") is not True:
        raise MarketFitHold("product expansion has not been approved")
    if not _valid_date(doc.get("researched_on")):
        raise MarketFitHold("research date missing or invalid")
    competitors = doc.get("direct_competitors")
    alternatives = doc.get("free_alternatives")
    if (not isinstance(competitors, list) or len(competitors) < 3
            or not isinstance(alternatives, list) or len(alternatives) < 3):
        raise MarketFitHold("competitor evidence incomplete")
    # Strings such as 'competitor A' are not independently checkable evidence.
    # A PASS needs three distinct named competitors with dated HTTPS sources.
    if any(not isinstance(item, dict)
           or not isinstance(item.get("name"), str)
           or not item["name"].strip()
           or not _valid_evidence_url(item.get("source"))
           or not _valid_date(item.get("checked")) for item in competitors):
        raise MarketFitHold("competitor source URL/date missing or invalid")
    if len({item["name"].strip().casefold() for item in competitors}) < 3:
        raise MarketFitHold("fewer than three distinct competitors")
    if (any(not isinstance(item, str) or not item.strip() for item in alternatives)
            or len({item.strip().casefold() for item in alternatives}) < 3):
        raise MarketFitHold("fewer than three distinct free alternatives")
    for field in ("paid_price_range", "buyer_persona", "why_pay_statement"):
        if not isinstance(doc.get(field), str) or len(doc[field].strip()) < 10:
            raise MarketFitHold("missing market rationale: " + field)
    if "NOT PROVEN" in doc["why_pay_statement"].upper():
        raise MarketFitHold("unproven willingness to pay")
    complaints = doc.get("common_review_complaints")
    if not isinstance(complaints, list) or not complaints:
        raise MarketFitHold("review complaints not documented")
    if not any(isinstance(item, dict)
               and isinstance(item.get("complaint"), str)
               and len(item["complaint"].strip()) >= 10
               and _valid_evidence_url(item.get("source"))
               and _valid_date(item.get("post_date")) for item in complaints):
        raise MarketFitHold("no dated, source-linked review complaint")
    if not isinstance(doc.get("store_search_keywords"), list) or not doc["store_search_keywords"]:
        raise MarketFitHold("Store discoverability not documented")
    if not isinstance(doc.get("price_hypothesis"), dict):
        raise MarketFitHold("price hypothesis absent")
    criteria = doc.get("go_criteria")
    if not isinstance(criteria, dict) or any(criteria.get(flag) is not True for flag in GO_FLAGS):
        raise MarketFitHold("GO conditions are not all satisfied")
    scoring = doc.get("scoring")
    if not isinstance(scoring, dict):
        raise MarketFitHold("market scoring absent")
    total = 0
    for name, maximum in WEIGHTS.items():
        component = scoring.get(name)
        if not isinstance(component, dict):
            raise MarketFitHold("scoring component absent: " + name)
        score = component.get("score")
        if type(score) is not int or not 0 <= score <= maximum or component.get("max") != maximum:
            raise MarketFitHold("invalid scoring component: " + name)
        total += score
    if type(scoring.get("total")) is not int or scoring["total"] != total or total < 80:
        raise MarketFitHold("score below 80 or inconsistent")
    if scoring.get("max") != 100:
        raise MarketFitHold("market scoring maximum invalid")
    baseline = doc.get("baseline_sha")
    if not isinstance(baseline, str) or not SHA40.fullmatch(baseline):
        raise MarketFitHold("reviewed source SHA absent")
    if not _git(root, "merge-base", "--is-ancestor", baseline, "HEAD"):
        raise MarketFitHold("market review baseline is not an ancestor")
    # Store Identity return may change, but product source must remain identical.
    source = "products/" + slug
    excluded_store = ":(exclude)" + source + "/store"
    if not _git(root, "diff", "--quiet", baseline, "HEAD", "--",
                source, excluded_store):
        raise MarketFitHold("product source changed after market review")
    # A direct local builder may read modified/staged files not present in HEAD.
    # The reviewed source must match the actual bytes that would be packaged.
    if not _git(root, "diff", "--quiet", "--", source, excluded_store):
        raise MarketFitHold("uncommitted product source changes")
    if not _git(root, "diff", "--cached", "--quiet", "--", source, excluded_store):
        raise MarketFitHold("staged product source changes")
    try:
        pending = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard", "--", source,
             excluded_store], cwd=root, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, timeout=15, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise MarketFitHold("cannot inspect untracked product source") from exc
    if pending.returncode != 0 or pending.stdout.strip():
        raise MarketFitHold("untracked product source files")
    return doc


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--slug", required=True)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args(argv)
    try:
        doc = assert_market_fit(args.root, args.slug)
    except (MarketFitHold, OSError) as exc:
        print("MARKET_FIT_HOLD: " + str(exc)[:220], file=sys.stderr)
        return 2
    print("MARKET_FIT_PASS: " + doc["slug"] + " (score "
          + str(doc["scoring"]["total"]) + "/100; reviewed source unchanged)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
