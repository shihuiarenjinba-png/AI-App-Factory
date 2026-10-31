#!/usr/bin/env python3
"""Owner/controller-only improvement promotion for a review-gated image preflight."""
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import factory

BRANCH = "codex/app-image-msix-preflight-candidate-20261031"
SLUG = "offline-image-inventory-desk"
BASE_SHA = "28fd060c2400bd9382cd1a5a14cd70b63b724de3"
CANDIDATE_FILES = ("main.py", "README.md", "manifest.json", "tests/test_smoke.py")


def run(*args, **kwargs):
    return subprocess.run(args, check=True, text=True, **kwargs)


def main():
    if os.environ.get("GITHUB_REF") != "refs/heads/" + BRANCH:
        raise ValueError("Wrong promotion branch")
    initial = run("git", "rev-parse", "HEAD", capture_output=True).stdout.strip()
    if initial != os.environ.get("GITHUB_SHA"):
        raise ValueError("Event/source HEAD mismatch")
    current_branch = run("git", "branch", "--show-current", capture_output=True).stdout.strip()
    if current_branch != BRANCH:
        raise ValueError("Detached or unexpected branch")
    if run("git", "status", "--porcelain", capture_output=True).stdout.strip():
        raise ValueError("Dirty initial checkout")
    cfg, state = factory.settings(ROOT)
    if cfg["kind"] != "app" or state != {
        "schema": 1, "kind": "app", "stage": "improve",
        "cycle": 1, "revision": 2, "slug": SLUG,
    }:
        raise ValueError("Unexpected owner-controlled Factory lifecycle")
    if not run("git", "merge-base", "--is-ancestor", BASE_SHA, "HEAD", capture_output=True).returncode == 0:
        raise ValueError("Revision-2 source ancestry missing")
    # Plan first; the controller then installs exactly the reviewed candidate files.
    assert factory.plan(ROOT)["stage"] == "improve"
    for relative in CANDIDATE_FILES:
        path = ".candidate/product/" + relative
        reviewed = run("git", "show", "HEAD:" + path, capture_output=True).stdout
        (ROOT / path).write_text(reviewed, encoding="utf-8")
    assert factory.validate(ROOT) == {"stage": "improve", "slug": SLUG}
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    run(sys.executable, "-m", "unittest", "discover", "-s",
        str(ROOT / ".candidate/product/tests"), "-v", cwd=ROOT, env=env, timeout=120)
    assert factory.promote(ROOT) == {"stage": "improve", "slug": SLUG}
    _, next_state = factory.settings(ROOT)
    if next_state["stage"] != "research" or next_state["cycle"] != 2:
        raise ValueError("Unexpected post-promotion lifecycle")
    run(sys.executable, "-m", "unittest", "discover", "-s",
        str(ROOT / "products" / SLUG / "tests"), "-v", cwd=ROOT, env=env, timeout=120)
    run(sys.executable, "-m", "unittest", "discover", "-s", "tests",
        "-v", cwd=ROOT, env=env, timeout=180)
    run("git", "add", "--", "factory/state.json", "products/" + SLUG)
    changed = run("git", "diff", "--cached", "--name-only", capture_output=True).stdout.splitlines()
    if not changed or any(p != "factory/state.json" and not p.startswith("products/" + SLUG + "/") for p in changed):
        raise ValueError("Unexpected staged files: " + repr(changed))
    run("git", "diff", "--cached", "--check")
    remote = run("git", "ls-remote", "origin", "refs/heads/" + BRANCH,
                 capture_output=True).stdout.split()[0]
    if remote != initial:
        raise ValueError("Remote HEAD changed; no blind overwrite")
    run("git", "-c", "user.name=github-actions[bot]",
        "-c", "user.email=41898282+github-actions[bot]@users.noreply.github.com",
        "commit", "-m", "feat(image): promote reviewed MSIX screenshot triage through Factory")
    run("git", "push", "origin", "HEAD:refs/heads/" + BRANCH)
    sha = run("git", "rev-parse", "HEAD", capture_output=True).stdout.strip()
    request = "app-offline-image-inventory-desk-" + sha[:12]
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with open(output, "a", encoding="utf-8") as stream:
            stream.write(f"source_sha={sha}\nrequest_id={request}\n")
    print(json.dumps({"FACTORY_PRODUCT_GENERATED": True, "slug": SLUG,
                      "source_branch": BRANCH, "source_sha": sha,
                      "request_id": request, "stage": "PRE_IDENTITY_BUILD_PENDING"}))


if __name__ == "__main__":
    main()
