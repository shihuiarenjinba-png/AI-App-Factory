#!/usr/bin/env python3
"""Owner-controlled APP cohort #3 promotion; never writes main or Store."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import factory

ROOT = Path(__file__).resolve().parents[1]
BRANCH = "codex/app-cohort-integrity-ledger-20261028"
SLUG = "file-integrity-ledger"
ISSUES = (("qarmin", "czkawka", 1295), ("agalwood", "Motrix", 2061))


def command(*args, **kwargs):
    return subprocess.run(args, check=True, text=True, **kwargs)


def market():
    signals = []
    for owner, repo, number in ISSUES:
        url = f"https://api.github.com/repos/{owner}/{repo}/issues/{number}"
        headers = {"Accept": "application/vnd.github+json",
                   "User-Agent": "IntegrityLedger-Factory-Cohort/1"}
        token = os.environ.get("GITHUB_TOKEN")
        if token:
            headers["Authorization"] = "Bearer " + token
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers),
                                    timeout=20) as response:
            raw = response.read(100001)
        if len(raw) > 100000:
            raise ValueError("issue evidence too large")
        issue = json.loads(raw)
        exact = f"https://github.com/{owner}/{repo}/issues/{number}"
        if issue.get("html_url") != exact or not issue.get("title"):
            raise ValueError("research evidence mismatch")
        signals.append({"url": exact, "title": str(issue["title"])[:140],
                        "excerpt": str(issue.get("body") or "")[:350]})
    return {"schema": 1, "kind": "app", "signals": signals,
            "note": "Untrusted public issues are weak research signals"}


def run():
    if os.environ.get("GITHUB_REF") != "refs/heads/" + BRANCH:
        raise ValueError("not the dedicated Draft branch")
    sha = command("git", "rev-parse", "HEAD", capture_output=True).stdout.strip()
    if sha != os.environ.get("GITHUB_SHA"):
        raise ValueError("checkout differs from event SHA")
    branch = command("git", "symbolic-ref", "--quiet", "--short", "HEAD",
                     capture_output=True).stdout.strip()
    if branch != BRANCH:
        raise ValueError("checkout branch mismatch")
    if command("git", "status", "--porcelain", capture_output=True).stdout.strip():
        raise ValueError("dirty checkout")
    cfg, state = factory.settings(ROOT)
    if cfg["kind"] != "app" or state != {
        "schema": 1, "kind": "app", "stage": "research",
        "cycle": 1, "revision": 0, "slug": None
    }:
        raise ValueError("unexpected Factory state; do not rerun promotion")
    candidate = ROOT / ".candidate"
    proposal = json.loads((candidate / "proposal.json").read_text(encoding="utf-8"))
    expected_urls = [f"https://github.com/{owner}/{repo}/issues/{number}"
                     for owner, repo, number in ISSUES]
    if proposal.get("slug") != SLUG or proposal.get("evidence_urls") != expected_urls:
        raise ValueError("proposal changed or evidence unreviewed")
    product = candidate / "product"
    if not product.is_dir() or product.is_symlink():
        raise ValueError("candidate code missing")
    (ROOT / ".runtime").mkdir(exist_ok=True)
    factory.save(ROOT / ".runtime/market.json", market())
    with tempfile.TemporaryDirectory(prefix="ledger-candidate-") as temp:
        parked = Path(temp) / "product"
        shutil.move(str(product), str(parked))
        try:
            assert factory.plan(ROOT)["stage"] == "research"
            assert factory.validate(ROOT) == {"stage": "research", "slug": SLUG}
            assert factory.promote(ROOT) == {"stage": "research", "slug": SLUG}
        finally:
            shutil.move(str(parked), str(product))
    if (candidate / "proposal.json").exists():
        raise ValueError("stale proposal after research promotion")
    assert factory.plan(ROOT)["stage"] == "build"
    assert factory.validate(ROOT) == {"stage": "build", "slug": SLUG}
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    result = command(sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v",
                     cwd=product, capture_output=True, env=env, timeout=120)
    if "Ran 18 tests in" not in result.stderr or "skipped=" in result.stderr:
        raise ValueError("18 unskipped product tests not established")
    print(result.stderr, flush=True)
    assert factory.promote(ROOT) == {"stage": "build", "slug": SLUG}
    if factory.settings(ROOT)[1]["stage"] != "improve":
        raise ValueError("build did not promote")
    for path in ("main.py", "manifest.json", "README.md", "tests/test_smoke.py"):
        if not (ROOT / "products" / SLUG / path).is_file():
            raise ValueError("promoted product missing: " + path)
    command(sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v",
            cwd=ROOT, env=env, timeout=180)
    command("git", "add", "-u", "--", ".candidate/proposal.json")
    command("git", "add", "--", "factory/state.json",
            f"proposals/{SLUG}.json", f"products/{SLUG}")
    changed = command("git", "diff", "--cached", "--name-only",
                      capture_output=True).stdout.splitlines()
    allowed = {"factory/state.json", ".candidate/proposal.json", f"proposals/{SLUG}.json"}
    if not changed or any(p not in allowed and not p.startswith(
            f"products/{SLUG}/") for p in changed):
        raise ValueError("unexpected staged files: " + repr(changed))
    command("git", "diff", "--cached", "--check")
    command("git", "-c", "user.name=github-actions[bot]",
            "-c", "user.email=41898282+github-actions[bot]@users.noreply.github.com",
            "commit", "-m", "feat(ledger): promote real file integrity product through Factory")
    current_remote = command("git", "ls-remote", "origin", "refs/heads/" + BRANCH,
                             capture_output=True).stdout.split()[0]
    if current_remote != sha:
        raise ValueError("remote changed; reject concurrent overwrite")
    command("git", "push", "origin", "HEAD:refs/heads/" + BRANCH)
    source_sha = command("git", "rev-parse", "HEAD", capture_output=True).stdout.strip()
    request_id = "app-file-integrity-ledger-" + source_sha[:12]
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with open(output, "a", encoding="utf-8") as f:
            f.write(f"source_sha={source_sha}\nrequest_id={request_id}\n")
    print(json.dumps({"FACTORY_PRODUCT_GENERATED": True, "slug": SLUG,
                      "source_branch": BRANCH, "source_sha": source_sha,
                      "request_id": request_id, "product_tests": 18}))


if __name__ == "__main__":
    try:
        run()
    except Exception as exc:
        print("LEDGER_PROMOTE_HOLD:", type(exc).__name__, str(exc), file=sys.stderr)
        raise
