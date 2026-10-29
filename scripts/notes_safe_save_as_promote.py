#!/usr/bin/env python3
"""Owner-only Factory improve transaction: safe Save As for Offline Notes.

Never directly patch promoted product. Work in Factory candidate, validate,
test, promote, verify exact bytes, and push with a remote HEAD lease.
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

BRANCH = "codex/app-notes-safe-save-as-20261030"
SLUG = "offline-notes-canary"
START = {"schema": 1, "kind": "app", "stage": "research",
         "cycle": 5, "revision": 0, "slug": None}


def cmd(*args, **kwargs):
    return subprocess.run(args, cwd=ROOT, check=True, text=True, **kwargs)


def replace_once(source, old, new, label):
    if source.count(old) != 1:
        raise ValueError("Source layout changed; HOLD: " + label)
    return source.replace(old, new, 1)


def remote_sha():
    out = cmd("git", "ls-remote", "origin", "refs/heads/" + BRANCH,
              capture_output=True).stdout.split()
    return out[0] if out else None


def main():
    if os.environ.get("GITHUB_REF") != "refs/heads/" + BRANCH:
        raise ValueError("Wrong GitHub ref")
    initial = cmd("git", "rev-parse", "HEAD", capture_output=True).stdout.strip()
    if initial != os.environ.get("GITHUB_SHA"):
        raise ValueError("Event SHA differs from checkout")
    if cmd("git", "symbolic-ref", "--short", "HEAD",
           capture_output=True).stdout.strip() != BRANCH:
        raise ValueError("Wrong checked out branch")
    if cmd("git", "status", "--porcelain", capture_output=True).stdout.strip():
        raise ValueError("Dirty checkout")
    if remote_sha() != initial:
        raise ValueError("Remote changed since event; HOLD")
    if factory.settings(ROOT)[1] != START or (ROOT / ".candidate").exists():
        raise ValueError("Wrong lifecycle state or stale candidate; HOLD")

    state = {**START, "stage": "improve", "revision": 2, "slug": SLUG}
    factory.save(ROOT / "factory/state.json", state)
    if factory.plan(ROOT) != state:
        raise ValueError("Owner plan mismatch")

    candidate = ROOT / ".candidate/product"
    source_file = candidate / "main.py"
    source = source_file.read_text(encoding="utf-8")
    source = replace_once(source,
        '        self.favorite_button.grid(row=0, column=7, padx=3)\n',
        '        self.favorite_button.grid(row=0, column=7, padx=3)\n'
        '        self.save_as_button = ttk.Button(bar, command=self.save_as)\n'
        '        self.save_as_button.grid(row=0, column=8, padx=3)\n',
        "Save As toolbar button")
    source = replace_once(source,
        '        self.favorites_check.configure(text=self.t(23))\n',
        '        self.favorites_check.configure(text=self.t(23))\n'
        '        self.save_as_button.configure(text=self.t(24))\n',
        "Save As bilingual toolbar label")
    source = replace_once(source,
        '        root.bind("<Control-s>", lambda _: self.save())\n',
        '        root.bind("<Control-s>", lambda _: self.save())\n'
        '        root.bind("<Control-Shift-S>", lambda _: self.save_as())\n',
        "Save As shortcut")
    source = replace_once(source,
        '"お気に入りのみ"],',
        '"お気に入りのみ", "名前を付けて保存"],',
        "Japanese Save As label")
    source = replace_once(source,
        '"Favorites only"]',
        '"Favorites only", "Save As"]',
        "English Save As label")
    save_as = '''    def save_as(self):
        """Save a separate notes copy; never overwrite another existing file."""
        try:
            self.commit_editor()
            selected = filedialog.asksaveasfilename(
                initialfile=self.path.name if self.path else "notes.json",
                defaultextension=".json", filetypes=[("JSON", "*.json")])
            if not selected:
                return False
            destination = Path(selected)
            if destination.exists() or destination.is_symlink():
                raise ValueError("Save As requires a new, unused filename")
            save_notes(destination, self.notes)
            self.path, self.dirty = destination, False
            self.status.set(self.t(11) + " — " + str(destination))
            self.refresh_list()
            return True
        except (OSError, ValueError) as exc:
            self.error(exc)
            return False

'''
    source = replace_once(source, '    def confirm(self):\n',
                          save_as + '    def confirm(self):\n', "Save As implementation")
    source_file.write_text(source, encoding="utf-8")

    test_file = candidate / "tests/test_commercial_metadata.py"
    tests = test_file.read_text(encoding="utf-8")
    tests = replace_once(tests, 'from unittest.mock import Mock\n',
                         'from unittest.mock import Mock, patch\n',
                         "test mocks")
    regressions = '''    def test_save_as_new_file_preserves_original_and_sets_current_path(self):
        original = self.path
        save_notes(original, [self.note])
        original_bytes = original.read_bytes()
        other = {**self.note, "title": "A different draft"}
        app = App.__new__(App)
        app.notes, app.path, app.dirty, app.lang = [other], original, True, "en"
        app.commit_editor, app.refresh_list, app.status = Mock(), Mock(), Mock()
        app.error = Mock()
        destination = Path(self.tmp.name) / "copy.json"
        with patch("main.filedialog.asksaveasfilename", return_value=str(destination)):
            self.assertTrue(app.save_as())
        self.assertEqual(original.read_bytes(), original_bytes)
        self.assertEqual(read_notes(destination), ([other], False))
        self.assertEqual(app.path, destination)
        self.assertFalse(app.dirty)
        app.error.assert_not_called()

    def test_save_as_existing_destination_is_fail_closed(self):
        existing = Path(self.tmp.name) / "existing.json"
        existing.write_bytes(b"FOREIGN CUSTOMER DATA")
        app = App.__new__(App)
        app.notes, app.path, app.dirty, app.lang = [self.note], self.path, True, "ja"
        app.commit_editor, app.refresh_list, app.status = Mock(), Mock(), Mock()
        app.error = Mock()
        with patch("main.filedialog.asksaveasfilename", return_value=str(existing)):
            self.assertFalse(app.save_as())
        self.assertEqual(existing.read_bytes(), b"FOREIGN CUSTOMER DATA")
        self.assertEqual(app.path, self.path)
        self.assertTrue(app.dirty)
        app.error.assert_called_once()
        from main import STRINGS
        self.assertEqual(STRINGS["ja"][24], "名前を付けて保存")
        self.assertEqual(STRINGS["en"][24], "Save As")

'''
    tests = replace_once(tests, '    def test_schema1_backward_compatibility(self):\n',
                         regressions + '    def test_schema1_backward_compatibility(self):\n',
                         "Save As regression tests")
    test_file.write_text(tests, encoding="utf-8")
    readme = candidate / "README.md"
    readme.write_text(readme.read_text(encoding="utf-8").rstrip() +
        "\n\nCommercial Save As: bilingual toolbar action and Ctrl+Shift+S "
        "create a separate JSON notes file. Existing destinations and symlinks "
        "are rejected without changing the original. Saving a new copy "
        "changes the current document path only after successful persistence. "
        "The regular Save action continues to support backup-safe updates.\n",
        encoding="utf-8")

    if factory.validate(ROOT) != {"stage": "improve", "slug": SLUG}:
        raise ValueError("Candidate validation mismatch")
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    result = subprocess.run(
        (sys.executable, "-m", "unittest", "discover",
         "-s", str(candidate / "tests"), "-p", "test*.py", "-v"),
        cwd=ROOT, text=True, capture_output=True, env=env, timeout=180)
    print(result.stdout, result.stderr, flush=True)
    match = re.search(r"Ran (\d+) tests in", result.stderr)
    if result.returncode or not match or int(match.group(1)) < 45 or "\nOK" not in result.stderr:
        raise ValueError("Candidate tests failed; HOLD without promote")
    if factory.promote(ROOT) != {"stage": "improve", "slug": SLUG}:
        raise ValueError("Factory promotion mismatch")
    if factory.settings(ROOT)[1] != {**START, "cycle": 6}:
        raise ValueError("Post-promotion lifecycle mismatch")
    for path in candidate.rglob("*"):
        if path.is_file():
            target = ROOT / "products" / SLUG / path.relative_to(candidate)
            if target.read_bytes() != path.read_bytes():
                raise ValueError("Promoted bytes differ from tested candidate")
    shutil.rmtree(ROOT / ".candidate")
    cmd(sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v",
        env=env, timeout=180)
    cmd(sys.executable, "-m", "unittest", "discover",
        "-s", f"products/{SLUG}/tests", "-p", "test*.py", "-v",
        env=env, timeout=180)
    paths = ["factory/state.json", f"products/{SLUG}/main.py",
             f"products/{SLUG}/tests/test_commercial_metadata.py",
             f"products/{SLUG}/README.md"]
    cmd("git", "add", "--", *paths)
    staged = set(cmd("git", "diff", "--cached", "--name-only",
                     capture_output=True).stdout.splitlines())
    if staged != set(paths):
        raise ValueError("Unexpected staged paths: " + repr(staged))
    cmd("git", "diff", "--cached", "--check")
    if remote_sha() != initial:
        raise ValueError("Remote changed before commit; HOLD")
    cmd("git", "-c", "user.name=github-actions[bot]",
        "-c", "user.email=41898282+github-actions[bot]@users.noreply.github.com",
        "commit", "-m", "feat(notes): promote non-destructive bilingual Save As")
    if remote_sha() != initial:
        raise ValueError("Remote changed before push; HOLD")
    cmd("git", "push", "origin", "HEAD:refs/heads/" + BRANCH)
    sha = cmd("git", "rev-parse", "HEAD", capture_output=True).stdout.strip()
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as out:
        out.write("source_sha=" + sha + "\n")
        out.write("request_id=app-offline-notes-canary-" + sha[:12] + "\n")
    print({"factory_product_generated": True, "source_sha": sha,
           "candidate_tests": int(match.group(1)), "identity_cas_allowed": False})


if __name__ == "__main__":
    main()
