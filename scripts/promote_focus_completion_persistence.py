#!/usr/bin/env python3
"""Factory owner: promote a reviewed Focus completion-persistence fix only."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import factory

BRANCH = "codex/app-focus-completion-persistence-20261030"
SLUG = "focus-session-desk"
FILES = ("main.py", "tests/test_smoke.py")
EXPECTED = {"schema": 1, "kind": "app", "stage": "improve",
            "cycle": 2, "revision": 2, "slug": SLUG}

def run(*args, **kwargs):
    return subprocess.run(args, cwd=ROOT, check=True, **kwargs)

def out(*args):
    return run(*args, capture_output=True, text=True).stdout.strip()

def remote_matches(sha):
    line = out("git", "ls-remote", "origin", "refs/heads/" + BRANCH).split()
    if not line or line[0] != sha:
        raise ValueError("Remote HEAD changed; refuse blind overwrite")

def main():
    if os.environ.get("GITHUB_REF") != "refs/heads/" + BRANCH:
        raise ValueError("Wrong owner ref")
    initial = out("git", "rev-parse", "HEAD")
    if initial != os.environ.get("GITHUB_SHA"):
        raise ValueError("Stale checkout")
    if out("git", "symbolic-ref", "--quiet", "--short", "HEAD") != BRANCH:
        raise ValueError("Wrong checkout branch")
    if out("git", "status", "--porcelain"):
        raise ValueError("Dirty checkout")
    remote_matches(initial)
    cfg, state = factory.settings(ROOT)
    if cfg["kind"] != "app" or state != EXPECTED:
        raise ValueError("Unexpected lifecycle state")
    product = ROOT / "products" / SLUG
    candidate = ROOT / ".candidate" / "product"
    existing = {p.relative_to(product).as_posix(): p for p in product.rglob("*") if p.is_file()}
    staged = {p.relative_to(candidate).as_posix(): p for p in candidate.rglob("*") if p.is_file()}
    if set(existing) != set(staged) or set(FILES) - set(existing):
        raise ValueError("Unexpected product/candidate files")
    for name in set(existing) - set(FILES):
        if existing[name].read_bytes() != staged[name].read_bytes():
            raise ValueError("Unreviewed candidate change: " + name)
    for name in FILES:
        if candidate.joinpath(name).is_symlink():
            raise ValueError("Symlink candidate forbidden")
    if all(existing[name].read_bytes() == staged[name].read_bytes() for name in FILES):
        if "def persist_completed_session" not in existing["main.py"].read_text(encoding="utf-8"):
            raise ValueError("Completion fix missing")
        output = os.environ.get("GITHUB_OUTPUT")
        if output:
            with open(output, "a", encoding="utf-8") as f:
                f.write("source_sha=" + initial + "\nrequest_id=app-focus-completion-" + initial[:12] + "\n")
        print(json.dumps({"status": "ALREADY_PROMOTED_VERIFIED", "source_sha": initial}))
        return
    if any(existing[name].read_bytes() == staged[name].read_bytes() for name in FILES):
        raise ValueError("Both source and regression tests must change")
    with tempfile.TemporaryDirectory(prefix="focus-completion-owner-") as folder:
        reviewed = Path(folder)
        for name in FILES:
            dest = reviewed / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(candidate / name, dest)
        factory.save(ROOT / "factory/state.json", dict(EXPECTED, revision=1))
        if factory.plan(ROOT) != dict(EXPECTED, revision=1):
            raise ValueError("Plan mismatch")
        for name in FILES:
            shutil.copyfile(reviewed / name, candidate / name)
        if factory.validate(ROOT) != {"stage": "improve", "slug": SLUG}:
            raise ValueError("Validation failed")
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        run(sys.executable, "-m", "unittest", "discover", "-s",
            str(candidate / "tests"), "-v", env=env, timeout=180)
        if factory.promote(ROOT) != {"stage": "improve", "slug": SLUG}:
            raise ValueError("Promotion failed")
        if factory.settings(ROOT)[1] != EXPECTED:
            raise ValueError("Lifecycle revision mismatch")
        for name in FILES:
            if (product / name).read_bytes() != (reviewed / name).read_bytes():
                raise ValueError("Promoted source differs from candidate")
        run(sys.executable, "-m", "unittest", "discover", "-s",
            str(product / "tests"), "-v", env=env, timeout=180)
        run(sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v",
            env=env, timeout=180)
        paths = ["products/" + SLUG + "/" + name for name in FILES]
        run("git", "add", "--", *paths)
        changed = set(out("git", "diff", "--cached", "--name-only").splitlines())
        if changed != set(paths):
            raise ValueError("Unexpected staged files: " + repr(changed))
        run("git", "diff", "--cached", "--check")
        remote_matches(initial)
        run("git", "-c", "user.name=github-actions[bot]",
            "-c", "user.email=41898282+github-actions[bot]@users.noreply.github.com",
            "commit", "-m", "fix(focus): persist finished sessions before claiming success")
        remote_matches(initial)
        run("git", "push", "origin", "HEAD:refs/heads/" + BRANCH)
        sha = out("git", "rev-parse", "HEAD")
        request = "app-focus-completion-" + sha[:12]
        output = os.environ.get("GITHUB_OUTPUT")
        if output:
            with open(output, "a", encoding="utf-8") as f:
                f.write("source_sha=" + sha + "\nrequest_id=" + request + "\n")
        print(json.dumps({"status": "FACTORY_IMPROVEMENT_PROMOTED",
                          "slug": SLUG, "source_branch": BRANCH,
                          "source_sha": sha, "request_id": request}))

if __name__ == "__main__":
    main()
