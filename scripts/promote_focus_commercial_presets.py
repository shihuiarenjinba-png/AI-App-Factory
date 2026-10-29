#!/usr/bin/env python3
"""Owner-only, source-locked commercial improvement of an existing Focus product.

The research cycle is complete. Reopen its already-promoted product for a
reviewed improvement; never create another product or mutate main/release.
"""
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

BRANCH = "codex/app-focus-commercial-presets-20261030"
SLUG = "focus-session-desk"
FILES = ("main.py", "tests/test_smoke.py")


def run(*args, **kwargs):
    return subprocess.run(args, cwd=ROOT, check=True, **kwargs)


def out(*args):
    return run(*args, capture_output=True, text=True).stdout.strip()


def main():
    if os.environ.get("GITHUB_REF") != "refs/heads/" + BRANCH:
        raise ValueError("Not the dedicated Focus commercial owner branch")
    initial = out("git", "rev-parse", "HEAD")
    if initial != os.environ.get("GITHUB_SHA"):
        raise ValueError("Trigger SHA differs from owner checkout")
    if out("git", "symbolic-ref", "--quiet", "--short", "HEAD") != BRANCH:
        raise ValueError("Wrong checkout branch")
    if out("git", "status", "--porcelain"):
        raise ValueError("Dirty owner checkout")
    remote = out("git", "ls-remote", "origin", "refs/heads/" + BRANCH).split()
    if not remote or remote[0] != initial:
        raise ValueError("Remote HEAD changed before owner operation")

    cfg, state = factory.settings(ROOT)
    expected = {"schema": 1, "kind": "app", "stage": "research",
                "cycle": 2, "revision": 0, "slug": None}
    # Repeated owner checks after a successful promotion are read-only.
    # Never reset the lifecycle or rewrite product files on a retry.
    already_promoted = {"schema": 1, "kind": "app", "stage": "improve",
                        "cycle": 2, "revision": 2, "slug": SLUG}
    if cfg["kind"] == "app" and state == already_promoted:
        product = ROOT / "products" / SLUG
        candidate = ROOT / ".candidate" / "product"
        for name in FILES:
            if not (product / name).is_file() or not (candidate / name).is_file():
                raise ValueError("Promoted product or reviewed candidate missing")
            if (product / name).read_bytes() != (candidate / name).read_bytes():
                raise ValueError("Promoted product differs from reviewed candidate")
        if "def start_preset" not in (product / "main.py").read_text(encoding="utf-8"):
            raise ValueError("Commercial preset feature missing")
        request_id = "app-focus-presets-" + initial[:12]
        output = os.environ.get("GITHUB_OUTPUT")
        if output:
            with open(output, "a", encoding="utf-8") as stream:
                stream.write(f"source_sha={initial}\nrequest_id={request_id}\n")
        print(json.dumps({"status": "ALREADY_PROMOTED_VERIFIED",
                          "slug": SLUG, "source_branch": BRANCH,
                          "source_sha": initial, "request_id": request_id}))
        return
    if cfg["kind"] != "app" or state != expected:
        raise ValueError("Unexpected Factory lifecycle; do not reset state")
    product = ROOT / "products" / SLUG
    candidate = ROOT / ".candidate" / "product"
    if not (product / "manifest.json").is_file():
        raise ValueError("Previously promoted Focus product missing")
    # The candidate must differ only in the two reviewed files.
    existing = {p.relative_to(product).as_posix(): p
                for p in product.rglob("*") if p.is_file()}
    staged = {p.relative_to(candidate).as_posix(): p
              for p in candidate.rglob("*") if p.is_file()}
    if set(existing) != set(staged):
        raise ValueError("Candidate file set changed unexpectedly")
    for name in set(existing) - set(FILES):
        if existing[name].read_bytes() != staged[name].read_bytes():
            raise ValueError("Unreviewed candidate modification: " + name)
    for name in FILES:
        if existing[name].read_bytes() == staged[name].read_bytes():
            raise ValueError("Missing reviewed feature/test difference: " + name)

    with tempfile.TemporaryDirectory(prefix="focus-presets-owner-") as folder:
        reviewed = Path(folder)
        for name in FILES:
            source = candidate / name
            if source.is_symlink():
                raise ValueError("Symlink candidate is prohibited")
            dest = reviewed / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, dest)

        # Explicit owner-controlled reopening of an already-promoted product.
        # The standard Factory plan/validate/promote contract remains mandatory.
        reopened = dict(state, stage="improve", revision=1, slug=SLUG)
        factory.save(ROOT / "factory/state.json", reopened)
        planned = factory.plan(ROOT)
        if planned != reopened:
            raise ValueError("Factory plan mismatch")
        for name in FILES:
            shutil.copyfile(reviewed / name, candidate / name)
        if factory.validate(ROOT) != {"stage": "improve", "slug": SLUG}:
            raise ValueError("Factory validation failed")

        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        run(sys.executable, "-m", "unittest", "discover", "-s",
            str(candidate / "tests"), "-v", env=env, timeout=180)
        if factory.promote(ROOT) != {"stage": "improve", "slug": SLUG}:
            raise ValueError("Factory promotion failed")
        expected_next = dict(reopened, revision=2)
        if factory.settings(ROOT)[1] != expected_next:
            raise ValueError("Factory did not advance to improve revision 2")
        for name in FILES:
            if (product / name).read_bytes() != (reviewed / name).read_bytes():
                raise ValueError("Promoted source differs from reviewed candidate")

        run(sys.executable, "-m", "unittest", "discover", "-s",
            str(product / "tests"), "-v", env=env, timeout=180)
        run(sys.executable, "-m", "unittest", "discover", "-s",
            "tests", "-v", env=env, timeout=180)
        paths = ["factory/state.json"] + [f"products/{SLUG}/{name}" for name in FILES]
        run("git", "add", "--", *paths)
        changed = set(out("git", "diff", "--cached", "--name-only").splitlines())
        if changed != set(paths):
            raise ValueError("Unexpected staged promotion files: " + repr(changed))
        run("git", "diff", "--cached", "--check")
        remote = out("git", "ls-remote", "origin", "refs/heads/" + BRANCH).split()
        if not remote or remote[0] != initial:
            raise ValueError("Remote changed before commit; refuse blind overwrite")
        run("git", "-c", "user.name=github-actions[bot]",
            "-c", "user.email=41898282+github-actions[bot]@users.noreply.github.com",
            "commit", "-m", "feat(focus): Factory-promote one-click commercial presets")
        remote = out("git", "ls-remote", "origin", "refs/heads/" + BRANCH).split()
        if not remote or remote[0] != initial:
            raise ValueError("Remote changed before push; refuse blind overwrite")
        run("git", "push", "origin", "HEAD:refs/heads/" + BRANCH)
        sha = out("git", "rev-parse", "HEAD")
        request_id = "app-focus-presets-" + sha[:12]
        output = os.environ.get("GITHUB_OUTPUT")
        if output:
            with open(output, "a", encoding="utf-8") as stream:
                stream.write(f"source_sha={sha}\nrequest_id={request_id}\n")
        print(json.dumps({"status": "FACTORY_IMPROVEMENT_PROMOTED",
                          "slug": SLUG, "source_branch": BRANCH,
                          "source_sha": sha, "request_id": request_id,
                          "stage": "improve", "revision": 2}))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("FOCUS_PRESETS_OWNER_HOLD:", type(exc).__name__, str(exc), file=sys.stderr)
        raise
