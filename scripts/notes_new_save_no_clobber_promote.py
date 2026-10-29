#!/usr/bin/env python3
"""Factory owner cycle 8: no-clobber creation of a NEW notes database.

Only the owner script stages an improve candidate. The production product is
modified exclusively by factory.promote after headless tests and validation.
"""
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import factory

BRANCH = "codex/app-notes-new-save-no-clobber-20261030"
SLUG = "offline-notes-canary"
START = {"schema": 1, "kind": "app", "stage": "research",
         "cycle": 8, "revision": 0, "slug": None}


def cmd(*args, **kwargs):
    return subprocess.run(args, cwd=ROOT, check=True, text=True, **kwargs)


def remote_sha():
    result = cmd("git", "ls-remote", "origin", "refs/heads/" + BRANCH,
                 capture_output=True).stdout.split()
    return result[0] if result else None


def replace_exact(source, old, new, label):
    if source.count(old) != 1:
        raise ValueError("Unexpected product layout: " + label)
    return source.replace(old, new, 1)


def main():
    if os.environ.get("GITHUB_REF") != "refs/heads/" + BRANCH:
        raise ValueError("Wrong branch ref")
    initial = cmd("git", "rev-parse", "HEAD", capture_output=True).stdout.strip()
    if initial != os.environ.get("GITHUB_SHA"):
        raise ValueError("Checkout differs from workflow event SHA")
    if cmd("git", "symbolic-ref", "--short", "HEAD",
           capture_output=True).stdout.strip() != BRANCH:
        raise ValueError("Wrong checked-out branch")
    if cmd("git", "status", "--porcelain", capture_output=True).stdout.strip():
        raise ValueError("Dirty checkout")
    if remote_sha() != initial:
        raise ValueError("Remote HEAD changed before start")
    if factory.settings(ROOT)[1] != START or (ROOT / ".candidate").exists():
        raise ValueError("Factory state changed or stale candidate exists")

    planned = {**START, "stage": "improve", "revision": 2, "slug": SLUG}
    factory.save(ROOT / "factory/state.json", planned)
    if factory.plan(ROOT) != planned:
        raise ValueError("Factory plan mismatch")

    product = ROOT / ".candidate/product"
    main_py = product / "main.py"
    source = main_py.read_text(encoding="utf-8")
    source = replace_exact(
        source,
        '        atomic_write(backup, path.read_bytes())\n'
        '    atomic_write(path, payload)\n',
        '        atomic_write(backup, path.read_bytes())\n'
        '        atomic_write(path, payload)\n'
        '    else:\n'
        '        # New-file Save must never replace a file created after the dialog.\n'
        '        # Atomic hardlink publication fails closed on any name collision.\n'
        '        atomic_create_new(path, payload)\n',
        "new-file Save race protection")
    main_py.write_text(source, encoding="utf-8")

    tests_path = product / "tests/test_commercial_metadata.py"
    tests = tests_path.read_text(encoding="utf-8")
    insertion = '''    def test_new_notes_database_save_uses_exclusive_creation(self):
        save_notes(self.path, [self.note])
        notes, recovered = read_notes(self.path)
        self.assertEqual(notes, [self.note])
        self.assertFalse(recovered)
        self.assertFalse(self.path.with_name(self.path.name + ".bak").exists())
        self.assertEqual(list(Path(self.tmp.name).glob(".notes-*")), [])

    def test_new_notes_database_save_cannot_clobber_concurrent_file(self):
        real_link = os.link

        def competing_writer(src, dst):
            Path(dst).write_bytes(b"OTHER PROCESS DATA")
            return real_link(src, dst)

        with patch("main.os.link", side_effect=competing_writer):
            with self.assertRaises(FileExistsError):
                save_notes(self.path, [self.note])
        self.assertEqual(self.path.read_bytes(), b"OTHER PROCESS DATA")
        self.assertFalse(self.path.with_name(self.path.name + ".bak").exists())
        self.assertEqual(list(Path(self.tmp.name).glob(".notes-*")), [])

    def test_new_notes_database_save_fails_closed_without_hardlinks(self):
        with patch("main.os.link", side_effect=PermissionError("hardlinks unavailable")):
            with self.assertRaises(PermissionError):
                save_notes(self.path, [self.note])
        self.assertFalse(self.path.exists())
        self.assertEqual(list(Path(self.tmp.name).glob(".notes-*")), [])

'''
    tests = replace_exact(tests,
                          "    def test_schema1_backward_compatibility(self):\n",
                          insertion + "    def test_schema1_backward_compatibility(self):\n",
                          "new Save regression tests")
    tests_path.write_text(tests, encoding="utf-8")

    readme = product / "README.md"
    readme.write_text(readme.read_text(encoding="utf-8").rstrip() +
        "\n\nCommercial first Save safety: a new notes JSON database is created "
        "with atomic no-clobber publication. If another process creates the "
        "selected filename before publication, the save fails without "
        "overwriting that file. Unsupported hardlink destinations fail closed. "
        "Three regression tests cover success, concurrent creation and "
        "hardlink-denied cleanup.\n", encoding="utf-8")

    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    result = subprocess.run(
        (sys.executable, "-m", "unittest", "discover", "-s",
         str(product / "tests"), "-p", "test*.py", "-v"),
        cwd=ROOT, text=True, capture_output=True, env=env, timeout=180)
    print(result.stdout, result.stderr, flush=True)
    match = re.search(r"Ran (\d+) tests in", result.stderr)
    if result.returncode or not match or int(match.group(1)) < 54 or "\nOK" not in result.stderr:
        raise ValueError("Candidate tests failed; no promote")
    if factory.validate(ROOT) != {"stage": "improve", "slug": SLUG}:
        raise ValueError("Candidate validation mismatch")
    if factory.promote(ROOT) != {"stage": "improve", "slug": SLUG}:
        raise ValueError("Factory promotion mismatch")
    if factory.settings(ROOT)[1] != {**START, "cycle": 9}:
        raise ValueError("Post-promote state mismatch")
    for path in product.rglob("*"):
        if path.is_file():
            target = ROOT / "products" / SLUG / path.relative_to(product)
            if target.read_bytes() != path.read_bytes():
                raise ValueError("Promoted bytes differ from tested candidate")
    shutil.rmtree(ROOT / ".candidate")

    cmd(sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v",
        env=env, timeout=180)
    cmd(sys.executable, "-m", "unittest", "discover",
        "-s", "products/offline-notes-canary/tests", "-p", "test*.py", "-v",
        env=env, timeout=180)

    paths = ["factory/state.json", "products/offline-notes-canary/main.py",
             "products/offline-notes-canary/tests/test_commercial_metadata.py",
             "products/offline-notes-canary/README.md"]
    cmd("git", "add", "--", *paths)
    staged = set(cmd("git", "diff", "--cached", "--name-only",
                     capture_output=True).stdout.splitlines())
    if staged != set(paths):
        raise ValueError("Unexpected staged paths: " + repr(staged))
    cmd("git", "diff", "--cached", "--check")
    if remote_sha() != initial:
        raise ValueError("Remote changed before commit")
    cmd("git", "-c", "user.name=github-actions[bot]",
        "-c", "user.email=41898282+github-actions[bot]@users.noreply.github.com",
        "commit", "-m", "fix(notes): prevent new database Save from clobbering competing files")
    if remote_sha() != initial:
        raise ValueError("Remote changed before push")
    cmd("git", "push", "origin", "HEAD:refs/heads/" + BRANCH)
    sha = cmd("git", "rev-parse", "HEAD", capture_output=True).stdout.strip()
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
        output.write("source_sha=" + sha + "\n")
        output.write("request_id=app-offline-notes-canary-" + sha[:12] + "\n")
    print({"factory_product_generated": True, "source_sha": sha,
           "candidate_tests": int(match.group(1)), "identity_cas_allowed": False})


if __name__ == "__main__":
    main()
