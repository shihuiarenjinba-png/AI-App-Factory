#!/usr/bin/env python3
"""Owner-controlled, review-only improvement promotion for File Integrity Ledger.

This runner uses factory.plan/validate/promote; it never edits state directly.
It refuses concurrent branch changes and never touches main/release or Store.
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

BRANCH = "codex/app-ledger-snapshot-size-20261028"
BASE_SHA = "deaa9f324326a1ee276596c325f7a360adf27877"
SLUG = "file-integrity-ledger"
FILES = ("main.py", "tests/test_smoke.py")


def run_command(*args, **kwargs):
    return subprocess.run(args, cwd=ROOT, check=True, **kwargs)


def run():
    if os.environ.get("GITHUB_REF") != "refs/heads/" + BRANCH:
        raise ValueError("Only the dedicated Draft improvement branch is permitted")
    initial_sha = run_command("git", "rev-parse", "HEAD",
                              capture_output=True, text=True).stdout.strip()
    if initial_sha != os.environ.get("GITHUB_SHA"):
        raise ValueError("Event SHA / checkout mismatch")
    current_branch = run_command("git", "symbolic-ref", "--quiet", "--short", "HEAD",
                                 capture_output=True, text=True).stdout.strip()
    if current_branch != BRANCH:
        raise ValueError("Not on dedicated improvement branch")
    if run_command("git", "status", "--porcelain",
                   capture_output=True, text=True).stdout.strip():
        raise ValueError("Dirty initial checkout")
    cfg, state = factory.settings(ROOT)
    if cfg["kind"] != "app" or state != {
        "schema": 1, "kind": "app", "stage": "improve",
        "cycle": 1, "revision": 1, "slug": SLUG
    }:
        raise ValueError("Unexpected state; refuse replay or cross-product promotion")
    product = ROOT / "products" / SLUG
    if not (product / "manifest.json").is_file():
        raise ValueError("Reviewed product manifest missing")
    with tempfile.TemporaryDirectory(prefix="ledger-reviewed-") as tmp:
        reviewed = Path(tmp)
        for name in FILES:
            source = product / name
            if not source.is_file() or source.is_symlink():
                raise ValueError("Missing or linked reviewed source: " + name)
            dest = reviewed / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, dest)
            baseline = run_command(
                "git", "show", BASE_SHA + ":products/" + SLUG + "/" + name,
                capture_output=True
            ).stdout
            source.write_bytes(baseline)
        try:
            # The controller must stage a candidate based on the frozen product,
            # then validate the reviewed improvements against that frozen source.
            result = factory.plan(ROOT)
            if result["stage"] != "improve" or result["slug"] != SLUG:
                raise ValueError("Controller planned the wrong product")
            candidate = ROOT / ".candidate" / "product"
            for name in FILES:
                shutil.copyfile(reviewed / name, candidate / name)
            if factory.validate(ROOT) != {"stage": "improve", "slug": SLUG}:
                raise ValueError("Factory improvement validation did not pass")
            env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
            run_command(sys.executable, "-m", "unittest", "discover", "-s",
                        str(candidate / "tests"), "-v", env=env, timeout=180)
            if factory.promote(ROOT) != {"stage": "improve", "slug": SLUG}:
                raise ValueError("Factory improvement promotion failed")
            if factory.settings(ROOT)[1]["revision"] != 2:
                raise ValueError("Expected revision 2 after promotion")
            for name in FILES:
                if (product / name).read_bytes() != (reviewed / name).read_bytes():
                    raise ValueError("Promoted source differs from reviewed source: " + name)
            run_command(sys.executable, "-m", "unittest", "discover", "-s",
                        "tests", "-v", env=env, timeout=180)
            run_command(sys.executable, "-m", "unittest", "discover", "-s",
                        str(product / "tests"), "-v", env=env, timeout=180)
            run_command("git", "add", "--", "factory/state.json",
                        "products/file-integrity-ledger/main.py",
                        "products/file-integrity-ledger/tests/test_smoke.py")
            # .candidate is ignored by design; explicitly stage only the
            # reviewed candidate files, never the whole ignored directory.
            run_command("git", "add", "-f", "--",
                        ".candidate/product/main.py",
                        ".candidate/product/tests/test_smoke.py")
            staged = run_command("git", "diff", "--cached", "--name-only",
                                 capture_output=True, text=True).stdout.splitlines()
            allowed = {"factory/state.json",
                       ".candidate/product/main.py",
                       ".candidate/product/tests/test_smoke.py",
                       "products/file-integrity-ledger/main.py",
                       "products/file-integrity-ledger/tests/test_smoke.py"}
            if "factory/state.json" not in staged or set(staged) - allowed:
                raise ValueError("Missing state or unexpected staged changes: " + repr(staged))
            run_command("git", "diff", "--cached", "--check")
            remote = run_command("git", "ls-remote", "origin",
                                 "refs/heads/" + BRANCH,
                                 capture_output=True, text=True).stdout.split()
            if not remote or remote[0] != initial_sha:
                raise ValueError("Remote branch changed; no blind overwrite")
            run_command("git", "-c", "user.name=github-actions[bot]",
                        "-c", "user.email=41898282+github-actions[bot]@users.noreply.github.com",
                        "commit", "-m", "fix(ledger): promote snapshot recovery improvement via Factory")
            # Recheck immediately before push. A normal fast-forward push is the only write.
            remote = run_command("git", "ls-remote", "origin",
                                 "refs/heads/" + BRANCH,
                                 capture_output=True, text=True).stdout.split()
            if not remote or remote[0] != initial_sha:
                raise ValueError("Concurrent update before push; HOLD")
            run_command("git", "push", "origin", "HEAD:refs/heads/" + BRANCH)
            sha = run_command("git", "rev-parse", "HEAD",
                              capture_output=True, text=True).stdout.strip()
            request_id = "app-file-integrity-ledger-" + sha[:12]
            output = os.environ.get("GITHUB_OUTPUT")
            if output:
                with open(output, "a", encoding="utf-8") as stream:
                    stream.write("source_sha=" + sha + "\n")
                    stream.write("request_id=" + request_id + "\n")
            print(json.dumps({"status": "IMPROVEMENT_PROMOTED",
                              "source_branch": BRANCH, "source_sha": sha,
                              "request_id": request_id, "slug": SLUG,
                              "factory_revision": 2}, sort_keys=True))
        finally:
            # GitHub Actions workspace is ephemeral; no cleanup push on failure.
            pass


if __name__ == "__main__":
    try:
        run()
    except Exception as exc:
        print("LEDGER_IMPROVE_HOLD:", type(exc).__name__, str(exc), file=sys.stderr)
        raise
