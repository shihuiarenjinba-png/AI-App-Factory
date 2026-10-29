#!/usr/bin/env python3
"""Owner-only Factory improvement promotion: Focus 1024x768 window-fit fix."""
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

BRANCH = "codex/app-focus-window-fit-promote-20261030"
SLUG = "focus-session-desk"
REVIEWED_FILES = ("main.py", "tests/test_smoke.py")


def run(*args, **kwargs):
    return subprocess.run(args, cwd=ROOT, check=True, **kwargs)


def stdout(*args):
    return run(*args, capture_output=True, text=True).stdout.strip()


def main():
    if os.environ.get("GITHUB_REF") != "refs/heads/" + BRANCH:
        raise ValueError("Only the dedicated owner improvement branch is permitted")
    initial = stdout("git", "rev-parse", "HEAD")
    if initial != os.environ.get("GITHUB_SHA"):
        raise ValueError("Checkout differs from triggering commit")
    if stdout("git", "symbolic-ref", "--quiet", "--short", "HEAD") != BRANCH:
        raise ValueError("Wrong checkout branch")
    if stdout("git", "status", "--porcelain"):
        raise ValueError("Dirty owner checkout")
    cfg, state = factory.settings(ROOT)
    expected = {"schema": 1, "kind": "app", "stage": "improve",
                "cycle": 1, "revision": 2, "slug": SLUG}
    if cfg["kind"] != "app" or state != expected:
        raise ValueError("Factory state changed; refuse unsafe promotion")
    candidate = ROOT / ".candidate" / "product"
    product = ROOT / "products" / SLUG
    if not (product / "manifest.json").is_file():
        raise ValueError("Committed Focus product missing")
    with tempfile.TemporaryDirectory(prefix="focus-window-fit-reviewed-") as folder:
        review = Path(folder)
        for name in REVIEWED_FILES:
            source = candidate / name
            if not source.is_file() or source.is_symlink():
                raise ValueError("Reviewed candidate file missing: " + name)
            destination = review / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
        planned = factory.plan(ROOT)
        if planned["stage"] != "improve" or planned["slug"] != SLUG:
            raise ValueError("Factory planned wrong lifecycle stage")
        for name in REVIEWED_FILES:
            shutil.copyfile(review / name, candidate / name)
        if factory.validate(ROOT) != {"stage": "improve", "slug": SLUG}:
            raise ValueError("Factory candidate validation failed")
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        run(sys.executable, "-m", "unittest", "discover", "-s",
            str(candidate / "tests"), "-v", env=env, timeout=180)
        if factory.promote(ROOT) != {"stage": "improve", "slug": SLUG}:
            raise ValueError("Factory promote returned wrong product")
        next_state = factory.settings(ROOT)[1]
        if next_state != {"schema": 1, "kind": "app", "stage": "research",
                          "cycle": 2, "revision": 0, "slug": None}:
            raise ValueError("Expected revision-2 completion to advance to cycle 2")
        for name in REVIEWED_FILES:
            if (product / name).read_bytes() != (review / name).read_bytes():
                raise ValueError("Promoted source differs from reviewed candidate")
        run(sys.executable, "-m", "unittest", "discover", "-s",
            str(product / "tests"), "-v", env=env, timeout=180)
        run(sys.executable, "-m", "unittest", "discover", "-s",
            "tests", "-v", env=env, timeout=180)
        run("git", "add", "--", "factory/state.json",
            "products/focus-session-desk/main.py",
            "products/focus-session-desk/tests/test_smoke.py")
        changed = stdout("git", "diff", "--cached", "--name-only").splitlines()
        allowed = {"factory/state.json", "products/focus-session-desk/main.py",
                   "products/focus-session-desk/tests/test_smoke.py"}
        if not changed or set(changed) - allowed or "factory/state.json" not in changed:
            raise ValueError("Unexpected promotion changes: " + repr(changed))
        run("git", "diff", "--cached", "--check")
        remote = stdout("git", "ls-remote", "origin", "refs/heads/" + BRANCH).split()
        if not remote or remote[0] != initial:
            raise ValueError("Remote branch changed; refuse blind overwrite")
        run("git", "-c", "user.name=github-actions[bot]",
            "-c", "user.email=41898282+github-actions[bot]@users.noreply.github.com",
            "commit", "-m", "fix(focus): Factory-promote 1024x768 taskbar-safe window")
        remote = stdout("git", "ls-remote", "origin", "refs/heads/" + BRANCH).split()
        if not remote or remote[0] != initial:
            raise ValueError("Concurrent remote update before push")
        run("git", "push", "origin", "HEAD:refs/heads/" + BRANCH)
        sha = stdout("git", "rev-parse", "HEAD")
        request_id = "app-focus-window-fit-" + sha[:12]
        output = os.environ.get("GITHUB_OUTPUT")
        if output:
            with open(output, "a", encoding="utf-8") as stream:
                stream.write(f"source_sha={sha}\nrequest_id={request_id}\n")
        print(json.dumps({"status": "FACTORY_IMPROVEMENT_PROMOTED",
                          "slug": SLUG, "source_branch": BRANCH,
                          "source_sha": sha, "request_id": request_id,
                          "factory_stage": "research", "factory_cycle": 2}))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("FOCUS_WINDOW_FIT_HOLD:", type(exc).__name__, str(exc), file=sys.stderr)
        raise
