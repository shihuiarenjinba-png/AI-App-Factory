#!/usr/bin/env python3
"""Owner-controlled Factory improvement: TXT export never clobbers another file.

This is an authorized Factory plan -> candidate tests -> validate -> promote
transaction. It does not edit the promoted product directly or bind Store Identity.
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

BRANCH = "codex/app-notes-export-no-clobber-20261030"
SLUG = "offline-notes-canary"
START = {"schema": 1, "kind": "app", "stage": "research",
         "cycle": 7, "revision": 0, "slug": None}


def cmd(*args, **kwargs):
    return subprocess.run(args, cwd=ROOT, check=True, text=True, **kwargs)


def remote_sha():
    out = cmd("git", "ls-remote", "origin", "refs/heads/" + BRANCH,
              capture_output=True).stdout.split()
    return out[0] if out else None


def replace_exact(source, old, new, label):
    if source.count(old) != 1:
        raise ValueError("Unexpected product source layout: " + label)
    return source.replace(old, new, 1)


def replace_section(source, start, end, replacement, label):
    if source.count(start) != 1 or source.count(end) != 1:
        raise ValueError("Unexpected source section: " + label)
    a = source.index(start)
    b = source.index(end, a + len(start))
    return source[:a] + replacement + source[b:]


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

    # Reuse the already-proven exclusive hardlink publication for both
    # JSON Save As/Restore and plain TXT export. No TOCTOU overwrite window.
    source = replace_section(
        source, "def save_notes_new(path, notes):\n",
        "\ndef save_notes(path, notes):\n",
        '''def atomic_create_new(path, data):
    """Create an unused file atomically; never overwrite a concurrent writer."""
    path = Path(path)
    if not path.parent.is_dir():
        raise ValueError("Choose an existing destination folder")
    temp = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".notes-", delete=False) as f:
            temp = Path(f.name)
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        # Atomic no-clobber publication, including existing symlinks.
        # Unsupported hardlink filesystems fail closed.
        os.link(temp, path)
    finally:
        if temp is not None:
            temp.unlink(missing_ok=True)


def save_notes_new(path, notes):
    atomic_create_new(path, notes_payload(notes))

''',
        "exclusive publication helper")

    source = replace_exact(
        source,
        '            if path.exists() and not messagebox.askyesno(self.t(0), self.t(17)):\n'
        '                return\n'
        '            atomic_write(path, (n["title"] + "\\n\\n" + n["body"] + "\\n").encode("utf-8"))\n',
        '            try:\n'
        '                atomic_create_new(path, (n["title"] + "\\n\\n" + n["body"] + "\\n").encode("utf-8"))\n'
        '            except FileExistsError as exc:\n'
        '                raise ValueError(self.t(25)) from exc\n',
        "TXT export no-clobber")

    source = replace_exact(
        source, '"名前を付けて保存"],',
        '"名前を付けて保存", "TXT書き出しには未使用のファイル名を選択してください。"],',
        "Japanese export guidance")
    source = replace_exact(
        source, '"Save As"]',
        '"Save As", "Choose a new, unused filename for TXT export."]',
        "English export guidance")
    main_py.write_text(source, encoding="utf-8")

    smoke_file = product / "tests/test_smoke.py"
    smoke = smoke_file.read_text(encoding="utf-8")
    smoke = replace_section(
        smoke,
        "    def test_export_overwrite_confirmation_localized(self):\n",
        "    def test_error_guidance_localized(self):\n",
        '''    def test_export_existing_file_is_rejected_in_both_languages(self):
        from main import App
        from unittest.mock import Mock
        for lang, expected in (
            ("ja", "TXT書き出しには未使用のファイル名を選択してください。"),
            ("en", "Choose a new, unused filename for TXT export."),
        ):
            with self.subTest(lang=lang):
                path = Path(self.tmp.name) / ("existing_" + lang + ".txt")
                path.write_text("OTHER CUSTOMER DATA", encoding="utf-8")
                app = App.__new__(App)
                app.notes = [self.note]
                app.current = self.note["id"]
                app.lang = lang
                app.dirty = True
                app.status = Mock()
                app.error = Mock()
                app.commit_editor = lambda: None
                with patch("main.filedialog.asksaveasfilename", return_value=str(path)), \\
                     patch("main.messagebox.askyesno") as confirm:
                    app.export()
                confirm.assert_not_called()
                self.assertEqual(path.read_text(encoding="utf-8"), "OTHER CUSTOMER DATA")
                self.assertTrue(app.dirty)
                app.error.assert_called_once()
                self.assertEqual(str(app.error.call_args.args[0]), expected)

''',
        "replace unsafe overwrite confirmation test")
    smoke_file.write_text(smoke, encoding="utf-8")

    commercial_file = product / "tests/test_commercial_metadata.py"
    tests = commercial_file.read_text(encoding="utf-8")
    regressions = '''    def test_txt_export_to_unused_filename_preserves_notes_database(self):
        save_notes(self.path, [self.note])
        original = self.path.read_bytes()
        destination = Path(self.tmp.name) / "new-export.txt"
        app = App.__new__(App)
        app.notes, app.current, app.path = [self.note], self.note["id"], self.path
        app.lang, app.dirty = "en", True
        app.commit_editor, app.status, app.error = Mock(), Mock(), Mock()
        with patch("main.filedialog.asksaveasfilename", return_value=str(destination)):
            app.export()
        self.assertEqual(destination.read_text(encoding="utf-8"), "Project\\n\\nDraft text\\n")
        self.assertEqual(self.path.read_bytes(), original)
        self.assertTrue(app.dirty)
        app.error.assert_not_called()

    def test_txt_export_concurrent_create_cannot_clobber_foreign_file(self):
        destination = Path(self.tmp.name) / "race-export.txt"
        app = App.__new__(App)
        app.notes, app.current, app.path = [self.note], self.note["id"], self.path
        app.lang, app.dirty = "ja", True
        app.commit_editor, app.status, app.error = Mock(), Mock(), Mock()
        real_link = os.link

        def competing_create(src, dst):
            Path(dst).write_bytes(b"FOREIGN DATA")
            return real_link(src, dst)

        with patch("main.filedialog.asksaveasfilename", return_value=str(destination)), \\
             patch("main.os.link", side_effect=competing_create):
            app.export()
        self.assertEqual(destination.read_bytes(), b"FOREIGN DATA")
        self.assertTrue(app.dirty)
        self.assertEqual(list(Path(self.tmp.name).glob(".notes-*")), [])
        app.error.assert_called_once()

    def test_txt_export_hardlink_unavailable_fails_closed(self):
        destination = Path(self.tmp.name) / "denied-export.txt"
        app = App.__new__(App)
        app.notes, app.current, app.path = [self.note], self.note["id"], self.path
        app.lang, app.dirty = "en", True
        app.commit_editor, app.status, app.error = Mock(), Mock(), Mock()
        with patch("main.filedialog.asksaveasfilename", return_value=str(destination)), \\
             patch("main.os.link", side_effect=PermissionError("hardlink denied")):
            app.export()
        self.assertFalse(destination.exists())
        self.assertTrue(app.dirty)
        self.assertEqual(list(Path(self.tmp.name).glob(".notes-*")), [])
        app.error.assert_called_once()

'''
    tests = replace_exact(tests, "    def test_schema1_backward_compatibility(self):\n",
                          regressions + "    def test_schema1_backward_compatibility(self):\n",
                          "TXT export regressions")
    commercial_file.write_text(tests, encoding="utf-8")

    readme = product / "README.md"
    readme.write_text(readme.read_text(encoding="utf-8").rstrip() +
        "\n\nCommercial TXT export safety: exports now use the same atomic "
        "no-clobber publication as Save As/Restore. Existing filenames, "
        "concurrent creation and unsupported hardlink filesystems fail closed "
        "without destroying unrelated customer data. The UI explains the "
        "new-filename requirement in Japanese and English; three new "
        "regression tests cover success, race and hardlink failure.\n",
        encoding="utf-8")

    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    result = subprocess.run(
        (sys.executable, "-m", "unittest", "discover",
         "-s", str(product / "tests"), "-p", "test*.py", "-v"),
        cwd=ROOT, text=True, capture_output=True, env=env, timeout=180)
    print(result.stdout, result.stderr, flush=True)
    match = re.search(r"Ran (\d+) tests in", result.stderr)
    if result.returncode or not match or int(match.group(1)) < 51 or "\nOK" not in result.stderr:
        raise ValueError("Candidate product tests failed; no promote")
    if factory.validate(ROOT) != {"stage": "improve", "slug": SLUG}:
        raise ValueError("Candidate validation mismatch")
    if factory.promote(ROOT) != {"stage": "improve", "slug": SLUG}:
        raise ValueError("Factory promotion mismatch")
    if factory.settings(ROOT)[1] != {**START, "cycle": 8}:
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
             "products/offline-notes-canary/tests/test_smoke.py",
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
        "commit", "-m", "fix(notes): prevent TXT export from clobbering competing files")
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
