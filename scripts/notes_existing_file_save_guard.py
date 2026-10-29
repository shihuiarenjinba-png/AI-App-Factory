#!/usr/bin/env python3
"""Owner-controlled third Offline Notes revision: refuse unsafe existing save targets."""
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import factory

BRANCH = "codex/app-notes-backup-export-safety-20261029"
SLUG = "offline-notes-canary"


def command(*args, **kwargs):
    return subprocess.run(args, cwd=ROOT, check=True, text=True, **kwargs)


def run():
    if os.environ.get("GITHUB_REF") != "refs/heads/" + BRANCH:
        raise ValueError("Unexpected branch")
    start = command("git", "rev-parse", "HEAD", capture_output=True).stdout.strip()
    if start != os.environ.get("GITHUB_SHA"):
        raise ValueError("Event SHA mismatch")
    active = command("git", "symbolic-ref", "--short", "HEAD",
                     capture_output=True).stdout.strip()
    if active != BRANCH or command("git", "status", "--porcelain",
                                   capture_output=True).stdout.strip():
        raise ValueError("Dirty or wrong checkout")

    _, state = factory.settings(ROOT)
    expected = {"schema": 1, "kind": "app", "stage": "improve",
                "cycle": 1, "revision": 2, "slug": SLUG}
    if state != expected:
        raise ValueError("Unexpected Factory state: " + repr(state))
    if factory.plan(ROOT) != expected:
        raise ValueError("Factory owner plan failed")

    candidate = ROOT / ".candidate" / "product"
    main = candidate / "main.py"
    source = main.read_text(encoding="utf-8")
    old = '''    path = Path(path)
    if path.exists():
        try:
            _, recovered = read_notes(path)
        except (OSError, ValueError):
            # A damaged primary is allowed to be saved over; an existing
            # recoverable backup must not be replaced with damaged data.
            recovered = True
        if not recovered:
            # If this fails, abort the save: never replace the only good
            # primary after silently losing the previous-version backup.
            atomic_write(path.with_name(path.name + ".bak"), path.read_bytes())
    atomic_write(path, payload)
'''
    new = '''    path = Path(path)
    if path.is_symlink():
        raise ValueError("Cannot save through a symbolic link")
    if path.exists():
        try:
            _, recovered = read_notes(path)
        except (OSError, ValueError) as exc:
            raise ValueError(
                "Existing file is not a valid notes database; choose another filename"
            ) from exc
        if recovered:
            raise ValueError(
                "Primary notes file is damaged; save recovered notes to a new filename"
            )
        backup = path.with_name(path.name + ".bak")
        if backup.is_symlink():
            raise ValueError("Cannot overwrite a symbolic-link backup")
        if backup.exists():
            try:
                _, backup_recovered = read_notes(backup)
            except (OSError, ValueError) as exc:
                raise ValueError(
                    "Existing backup is not a valid notes database; choose another filename"
                ) from exc
            if backup_recovered:
                raise ValueError("Existing backup is damaged; choose another filename")
        # Backup failure is fatal; never replace the primary in that case.
        atomic_write(backup, path.read_bytes())
    atomic_write(path, payload)
'''
    if source.count(old) != 1:
        raise ValueError("Unexpected save implementation; refuse blind edit")
    main.write_text(source.replace(old, new, 1), encoding="utf-8")

    tests = candidate / "tests" / "test_smoke.py"
    original = tests.read_text(encoding="utf-8")
    anchor = "    def test_roundtrip(self):"
    extra = '''    def test_existing_unrelated_json_is_not_overwritten(self):
        foreign = b'{"schema": 99, "private": "do not overwrite"}\\\\n'
        self.path.write_bytes(foreign)
        with self.assertRaisesRegex(ValueError, "choose another filename"):
            save_notes(self.path, [self.note])
        self.assertEqual(self.path.read_bytes(), foreign)
        self.assertFalse(self.path.with_name("notes.json.bak").exists())

    def test_damaged_primary_with_valid_backup_is_not_overwritten(self):
        save_notes(self.path, [self.note])
        good = self.path.read_bytes()
        backup = self.path.with_name("notes.json.bak")
        backup.write_bytes(good)
        damaged = b"not a notes database"
        self.path.write_bytes(damaged)
        with self.assertRaisesRegex(ValueError, "damaged"):
            save_notes(self.path, [new_note()])
        self.assertEqual(self.path.read_bytes(), damaged)
        self.assertEqual(backup.read_bytes(), good)

    def test_existing_unrelated_backup_is_not_overwritten(self):
        save_notes(self.path, [self.note])
        good = self.path.read_bytes()
        backup = self.path.with_name("notes.json.bak")
        foreign = b"foreign backup contents"
        backup.write_bytes(foreign)
        with self.assertRaisesRegex(ValueError, "Existing backup"):
            save_notes(self.path, [new_note()])
        self.assertEqual(self.path.read_bytes(), good)
        self.assertEqual(backup.read_bytes(), foreign)

    def test_existing_valid_notes_can_still_save_and_rotate_backup(self):
        save_notes(self.path, [self.note])
        old = self.path.read_bytes()
        second = new_note()
        save_notes(self.path, [self.note, second])
        self.assertEqual(self.path.with_name("notes.json.bak").read_bytes(), old)
        self.assertEqual(read_notes(self.path), ([self.note, second], False))

'''
    if original.count(anchor) != 1 or "test_existing_unrelated_json_is_not_overwritten" in original:
        raise ValueError("Unexpected tests; refuse blind edit")
    tests.write_text(original.replace(anchor, extra + anchor, 1), encoding="utf-8")

    readme = candidate / "README.md"
    readme.write_text(readme.read_text(encoding="utf-8").rstrip()
        + "\n\nSafety revision 3: Save refuses unrelated JSON, damaged primary "
          "files (even with a valid backup), and unrelated/damaged backup paths. "
          "Users must choose a new filename rather than lose existing data. "
          "Four new headless regressions cover these cases; GUI remains unverified.\n",
        encoding="utf-8")

    if factory.validate(ROOT) != {"stage": "improve", "slug": SLUG}:
        raise ValueError("Factory validation failed")
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    result = subprocess.run((sys.executable, "-m", "unittest", "discover", "-s",
                             str(candidate / "tests"), "-v"), cwd=ROOT,
                            text=True, capture_output=True, env=env, timeout=180)
    print(result.stdout, flush=True)
    print(result.stderr, flush=True)
    if result.returncode:
        raise ValueError("Candidate regression failed")
    if "Ran 26 tests in" not in result.stderr or "\nOK" not in result.stderr:
        raise ValueError("26 candidate tests not established")

    if factory.promote(ROOT) != {"stage": "improve", "slug": SLUG}:
        raise ValueError("Factory owner promote failed")
    new_state = {"schema": 1, "kind": "app", "stage": "research",
                 "cycle": 2, "revision": 0, "slug": None}
    if factory.settings(ROOT)[1] != new_state:
        raise ValueError("Unexpected post-promotion state")
    for name in ("main.py", "tests/test_smoke.py", "README.md"):
        if (ROOT / "products" / SLUG / name).read_bytes() != (candidate / name).read_bytes():
            raise ValueError("Promoted source differs from tested candidate: " + name)

    # The owner/controller completed revision 2 -> next research cycle.
    # Clear stale candidate product before any future research plan; do not start a new product.
    shutil.rmtree(ROOT / ".candidate")
    command(sys.executable, "-m", "unittest", "discover", "-s", "tests",
            "-v", env=env, timeout=180)
    command(sys.executable, "-m", "unittest", "discover", "-s",
            f"products/{SLUG}/tests", "-v", env=env, timeout=180)

    paths = ["factory/state.json"] + [
        f"products/{SLUG}/{name}" for name in ("main.py", "tests/test_smoke.py", "README.md")
    ]
    command("git", "add", "--", *paths)
    command("git", "add", "-u", "--", ".candidate")
    staged = set(command("git", "diff", "--cached", "--name-only",
                         capture_output=True).stdout.splitlines())
    allowed = set(paths) | {
        ".candidate/product/main.py", ".candidate/product/tests/test_smoke.py",
        ".candidate/product/README.md", ".candidate/product/manifest.json"
    }
    required = {"factory/state.json", f"products/{SLUG}/main.py",
                f"products/{SLUG}/tests/test_smoke.py"}
    if not required.issubset(staged) or not staged.issubset(allowed):
        raise ValueError("Unexpected staged changes: " + repr(sorted(staged)))
    command("git", "diff", "--cached", "--check")
    remote = command("git", "ls-remote", "origin", "refs/heads/" + BRANCH,
                     capture_output=True).stdout.split()
    if not remote or remote[0] != start:
        raise ValueError("Concurrent branch update; refuse blind push")
    command("git", "-c", "user.name=github-actions[bot]",
            "-c", "user.email=41898282+github-actions[bot]@users.noreply.github.com",
            "commit", "-m", "fix(notes): reject unsafe existing save destinations")
    remote = command("git", "ls-remote", "origin", "refs/heads/" + BRANCH,
                     capture_output=True).stdout.split()
    if not remote or remote[0] != start:
        raise ValueError("Concurrent update before push; HOLD")
    command("git", "push", "origin", "HEAD:refs/heads/" + BRANCH)
    sha = command("git", "rev-parse", "HEAD", capture_output=True).stdout.strip()
    request_id = "app-offline-notes-canary-" + sha[:12]
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
        output.write(f"source_sha={sha}\nrequest_id={request_id}\n")
    print({"FACTORY_IMPROVEMENT_PASS": True, "source_sha": sha,
           "request_id": request_id, "product_tests": 26,
           "candidate_cleaned": True, "store_identity_bound": False})


if __name__ == "__main__":
    run()
