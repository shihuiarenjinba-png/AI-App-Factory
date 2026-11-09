#!/usr/bin/env python3
"""Fail-closed recovery of an approved existing-product proposal.

This does NOT synthesize market evidence, mutate factory/state.json, or use
the research stage of the currently active product. Supply reviewed inputs.
"""
import argparse
import json
import os
import re
import sys
import urllib.request
from pathlib import Path

SLUG = "us-freelance-ledger"
FIELDS = ("title", "customer_problem", "audience", "differentiation")

def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))

def verify_live_evidence(proposal, market, approved_by, fetch=None):
    """Fail closed unless real GitHub issues contain market context and approval."""
    if not approved_by or not re.fullmatch(r"[A-Za-z0-9-]{1,39}", approved_by):
        raise ValueError("trusted approval actor required")
    if fetch is None:
        def fetch(url):
            req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "ledger-recovery"})
            with urllib.request.urlopen(req, timeout=12) as response:
                return json.load(response)
    # Never accept a bare URL as a substantive market signal.
    signals = {item["url"]: item for item in market["signals"]}
    for url in proposal["evidence_urls"]:
        match = re.fullmatch(r"https://github\.com/([^/]+)/([^/]+)/issues/([0-9]+)", url)
        if not match:
            raise ValueError("invalid issue URL")
        owner, repo, number = match.groups()
        signal = signals[url]
        summary = signal.get("summary")
        if not isinstance(summary, str) or len(summary.strip()) < 40:
            raise ValueError("market evidence summary missing")
        if not any(word in summary.lower() for word in ("customer", "demand", "competitor", "pricing")):
            raise ValueError("market evidence summary lacks substance")
        api = f"https://api.github.com/repos/{owner}/{repo}/issues/{number}"
        try:
            issue, comments = fetch(api), fetch(api + "/comments?per_page=100")
            permission = fetch(f"https://api.github.com/repos/{owner}/{repo}/collaborators/{approved_by}/permission")
        except (OSError, ValueError, TypeError, KeyError) as exc:
            raise ValueError("live evidence unavailable") from exc
        if not isinstance(permission, dict) or permission.get("permission") not in ("admin", "maintain", "write"):
            raise ValueError("approver lacks repository write permission")
        if not isinstance(issue, dict) or issue.get("pull_request") or issue.get("html_url") != url:
            raise ValueError("issue identity mismatch")
        body = issue.get("body")
        if not isinstance(body, str) or not any(x in body.lower() for x in ("us freelance ledger", "us-freelance-ledger")):
            raise ValueError("issue does not identify product")
        if summary.strip().lower() not in body.lower():
            raise ValueError("market evidence summary not found in issue")
        if not any(x in body.lower() for x in ("market", "customer", "demand", "competitor")):
            raise ValueError("issue lacks market evidence")
        # The GitHub comments endpoint is paginated. A full first page is
        # ambiguous: an unseen later page may contain revocations or changes.
        # Reject rather than certify approval from an incomplete history.
        if not isinstance(comments, list) or len(comments) >= 100:
            raise ValueError("approval history incomplete or invalid")
        if not any(
            isinstance(c, dict) and isinstance(c.get("user"), dict)
            and c["user"].get("login", "").lower() == approved_by.lower()
            and c.get("body", "").strip() == "APPROVED MARKET EVIDENCE: us-freelance-ledger"
            and c.get("created_at") for c in comments
        ):
            raise ValueError("trusted approval missing")
    return True

def validate(root, proposal, market):
    product = root / "products" / SLUG / "manifest.json"
    if not product.is_file():
        raise ValueError("existing US Freelance Ledger manifest missing")
    manifest = read_json(product)
    if (manifest.get("slug"), manifest.get("kind"), manifest.get("market"),
        manifest.get("currency")) != (SLUG, "app", "US", "USD"):
        raise ValueError("existing product manifest does not match US ledger")
    if proposal.get("slug") != SLUG:
        raise ValueError("proposal slug mismatch")
    for field in FIELDS:
        if not isinstance(proposal.get(field), str) or len(proposal[field].strip()) < 15:
            raise ValueError("incomplete proposal field: " + field)
    scope = proposal.get("scope")
    if not isinstance(scope, list) or not 2 <= len(scope) <= 6 or any(
        not isinstance(s, str) or not 8 <= len(s) <= 200 for s in scope
    ):
        raise ValueError("invalid scope")
    if market.get("schema") != 1 or market.get("kind") != "app":
        raise ValueError("market evidence schema/kind mismatch")
    signals = market.get("signals")
    if not isinstance(signals, list) or len(signals) < 2:
        raise ValueError("missing independent market signals")
    allowed = set()
    for signal in signals:
        if not isinstance(signal, dict):
            raise ValueError("invalid market signal")
        url = signal.get("url")
        if not isinstance(url, str) or not re.fullmatch(
            r"https://github\.com/[^/\s]+/[^/\s]+/issues/[0-9]+", url
        ):
            raise ValueError("invalid GitHub issue evidence URL")
        allowed.add(url)
    urls = proposal.get("evidence_urls")
    if not isinstance(urls, list) or len(urls) < 2 or len(set(urls)) < 2:
        raise ValueError("two distinct evidence URLs required")
    if any(not isinstance(url, str) or url not in allowed for url in urls):
        raise ValueError("proposal evidence absent from supplied market record")
    repos = {"/".join(url.split("/")[3:5]).lower() for url in urls}
    if len(repos) < 2:
        raise ValueError("two distinct repositories required")
    return True

def restore(root, proposal_path, market_path, dry_run=False, approved_by=None, fetch=None):
    root = Path(root)
    target = root / "proposals" / (SLUG + ".json")
    if target.parent.is_symlink():
        raise ValueError("symlink proposal directory prohibited")
    if target.exists() or target.is_symlink():
        raise ValueError("existing proposal cannot be overwritten")
    if Path(proposal_path).is_symlink() or Path(market_path).is_symlink():
        raise ValueError("symlink input prohibited")
    proposal, market = read_json(proposal_path), read_json(market_path)
    validate(root, proposal, market)
    verify_live_evidence(proposal, market, approved_by, fetch)
    if dry_run:
        return "VALIDATED_ONLY"
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.parent.is_symlink():
        raise ValueError("symlink proposal directory prohibited")
    # Exclusive create: even concurrent recovery cannot overwrite existing bytes.
    payload = json.dumps(proposal, ensure_ascii=False, indent=2) + "\n"
    with target.open("x", encoding="utf-8") as output:
        output.write(payload)
        output.flush()
        os.fsync(output.fileno())
    return str(target)

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    p.add_argument("--proposal", type=Path, required=True)
    p.add_argument("--market", type=Path, required=True)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--approved-by", required=True)
    args = p.parse_args()
    try:
        print(restore(args.root, args.proposal, args.market, args.dry_run, args.approved_by))
    except (ValueError, OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print("HOLD:", exc, file=sys.stderr)
        return 2
    return 0

if __name__ == "__main__":
    sys.exit(main())
