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
from pathlib import Path

SLUG = "us-freelance-ledger"
FIELDS = ("title", "customer_problem", "audience", "differentiation")

def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))

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
            r"https://github\\.com/[^/\\s]+/[^/\\s]+/issues/[0-9]+", url
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

def restore(root, proposal_path, market_path, dry_run=False):
    root = Path(root)
    target = root / "proposals" / (SLUG + ".json")
    if target.exists() or target.is_symlink():
        raise ValueError("existing proposal cannot be overwritten")
    if Path(proposal_path).is_symlink() or Path(market_path).is_symlink():
        raise ValueError("symlink input prohibited")
    proposal, market = read_json(proposal_path), read_json(market_path)
    validate(root, proposal, market)
    if dry_run:
        return "VALIDATED_ONLY"
    target.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive create: even concurrent recovery cannot overwrite existing bytes.
    payload = json.dumps(proposal, ensure_ascii=False, indent=2) + "\\n"
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
    args = p.parse_args()
    try:
        print(restore(args.root, args.proposal, args.market, args.dry_run))
    except (ValueError, OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print("HOLD:", exc, file=sys.stderr)
        return 2
    return 0

if __name__ == "__main__":
    sys.exit(main())
