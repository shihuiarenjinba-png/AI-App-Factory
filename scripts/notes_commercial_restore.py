#!/usr/bin/env python3
"""Owner-controlled commercial restore increment for Offline Notes.

Uses Factory plan -> candidate regression -> validate -> promote. Never changes
main/release, Partner Center, Identity, or the immutable prior EXE.
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import factory

BRANCH = "codex/app-notes-commercial-restore-20261029"
SLUG = "offline-notes-canary"
START_STATE = {"schema": 1, "kind": "app", "stage": "research",
               "cycle": 2, "revision": 0, "slug": None}

def command(*args, **kwargs):
    return subprocess.run(args, cwd=ROOT, check=True, text=True, **kwargs)

def replace_once(source, old, new, label):
    if source.count(old) != 1:
        raise ValueError("Refuse unexpected source layout: " + label)
    return source.replace(old, new, 1)

def run():
    if os.environ.get("GITHUB_REF") != "refs/heads/" + BRANCH:
        raise ValueError("Wrong branch")
    start = command("git", "rev-parse", "HEAD", capture_output=True).stdout.strip()
    if start != os.environ.get("GITHUB_SHA"):
        raise ValueError("Event SHA mismatch")
    active = command("git", "symbolic-ref", "--short", "HEAD",
                     capture_output=True).stdout.strip()
    if active != BRANCH or command("git", "status", "--porcelain",
                                   capture_output=True).stdout.strip():
        raise ValueError("Dirty checkout or wrong branch")
    if factory.settings(ROOT)[1] != START_STATE:
        raise ValueError("Unexpected Factory lifecycle; do not overwrite")
    if (ROOT / ".candidate").exists():
        raise ValueError("Stale candidate; refuse to discard other work")
    # Explicit owner/controller reentry for an existing commercial product,
    # not a research-stage agent writing Factory state.
    improvement = {**START_STATE, "stage": "improve",
                   "revision": 2, "slug": SLUG}
    factory.save(ROOT / "factory/state.json", improvement)
    if factory.plan(ROOT) != improvement:
        raise ValueError("Factory plan failed")
    candidate = ROOT / ".candidate/product"
    main = candidate / "main.py"
    source = main.read_text(encoding="utf-8")
    source = replace_once(source,
        'self.new, self.open_file, self.save, self.export, self.delete, self.language',
        'self.new, self.open_file, self.save, self.export, self.delete, self.language, self.restore_backup',
        "toolbar")
    source = replace_once(source,
        'b.configure(text=self.t(i + 1))',
        'b.configure(text=self.t(i + 1 if i < 6 else 19))',
        "localized toolbar")
    source = replace_once(source,
        '"入力内容とファイルの保存先を確認し、もう一度お試しください。"]',
        '"入力内容とファイルの保存先を確認し、もう一度お試しください。", "バックアップから復元"]',
        "Japanese label")
    source = replace_once(source,
        '"Check your input and file location, then try again."]',
        '"Check your input and file location, then try again.", "Restore backup"]',
        "English label")
    restore = '''    def restore_backup(self):
        """Explicit, non-destructive restore to a NEW JSON file."""
        try:
            if not self.confirm():
                return
            selected = filedialog.askopenfilename(
                filetypes=[("Notes backup", "*.bak"), ("All files", "*.*")])
            if not selected:
                return
            backup = Path(selected)
            if not backup.name.lower().endswith(".bak") or backup.is_symlink():
                raise ValueError("Choose a regular .bak notes backup")
            recovered_notes, used_fallback = read_notes(backup)
            if used_fallback:
                raise ValueError("Selected backup is damaged")
            output = filedialog.asksaveasfilename(
                initialfile="restored-notes.json", defaultextension=".json",
                filetypes=[("JSON", "*.json")])
            if not output:
                return
            destination = Path(output)
            # Never overwrite an existing file during recovery, even if valid.
            if destination.exists() or destination.is_symlink():
                raise ValueError("Restore requires a new, unused filename")
            save_notes(destination, recovered_notes)
            self.notes, self.path, self.dirty = recovered_notes, destination, False
            self.query.set("")
            self.show(recovered_notes[0]["id"] if recovered_notes else None)
            self.status.set(self.t(11) + " — " + str(destination))
        except (OSError, ValueError) as exc:
            self.error(exc)

'''
    source = replace_once(source, "    def export(self):\n", restore + "    def export(self):\n",
                          "restore method")
    main.write_text(source, encoding="utf-8")

    tests = candidate / "tests/test_smoke.py"
    original = tests.read_text(encoding="utf-8")
    extra = '''    def test_explicit_backup_restore_creates_new_database(self):
        from main import App
        from unittest.mock import Mock
        save_notes(self.path, [self.note])
        backup = self.path.with_name(self.path.name + ".bak")
        backup.write_bytes(self.path.read_bytes())
        target = Path(self.tmp.name) / "restored.json"
        app = App.__new__(App)
        app.confirm, app.show, app.error = Mock(return_value=True), Mock(), Mock()
        app.query, app.status = Mock(), Mock()
        app.lang = "en"
        with patch("main.filedialog.askopenfilename", return_value=str(backup)), \\
             patch("main.filedialog.asksaveasfilename", return_value=str(target)):
            app.restore_backup()
        app.error.assert_not_called()
        self.assertEqual(read_notes(target), ([self.note], False))
        self.assertEqual(app.path, target)
        self.assertFalse(app.dirty)
        self.assertEqual(backup.read_bytes(), self.path.read_bytes())
        app.show.assert_called_once_with(self.note["id"])

    def test_backup_restore_refuses_existing_destination(self):
        from main import App
        from unittest.mock import Mock
        save_notes(self.path, [self.note])
        backup = self.path.with_name(self.path.name + ".bak")
        backup.write_bytes(self.path.read_bytes())
        target = Path(self.tmp.name) / "unrelated.json"
        target.write_bytes(b"foreign content")
        app = App.__new__(App)
        app.confirm, app.error = Mock(return_value=True), Mock()
        app.lang = "ja"
        with patch("main.filedialog.askopenfilename", return_value=str(backup)), \\
             patch("main.filedialog.asksaveasfilename", return_value=str(target)):
            app.restore_backup()
        app.error.assert_called_once()
        self.assertEqual(target.read_bytes(), b"foreign content")

    def test_backup_restore_refuses_damaged_backup(self):
        from main import App
        from unittest.mock import Mock
        backup = self.path.with_name(self.path.name + ".bak")
        backup.write_text("corrupt", encoding="utf-8")
        app = App.__new__(App)
        app.confirm, app.error = Mock(return_value=True), Mock()
        app.lang = "en"
        with patch("main.filedialog.askopenfilename", return_value=str(backup)), \\
             patch("main.filedialog.asksaveasfilename") as save_dialog:
            app.restore_backup()
        app.error.assert_called_once()
        save_dialog.assert_not_called()

'''
    original = replace_once(original, "    def test_roundtrip(self):\n",
                            extra + "    def test_roundtrip(self):\n",
                            "restore regression anchor")
    tests.write_text(original, encoding="utf-8")
    readme = candidate / "README.md"
    readme.write_text(readme.read_text(encoding="utf-8").rstrip()
        + "\n\nCommercial increment: an explicit bilingual Restore backup action "
          "loads a selected .bak database and writes recovery to a NEW unused "
          "JSON file. Existing files, damaged backups and symlinks are rejected. "
          "Three headless regressions cover non-destructive recovery. "
          "Consumer GUI and 1024x768 checks remain HOLD.\n", encoding="utf-8")

    if factory.validate(ROOT) != {"stage": "improve", "slug": SLUG}:
        raise ValueError("Factory validate failed")
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    result = subprocess.run((sys.executable, "-m", "unittest", "discover",
                             "-s", str(candidate / "tests"), "-v"),
                            cwd=ROOT, text=True, capture_output=True,
                            env=env, timeout=180)
    print(result.stdout, flush=True)
    print(result.stderr, flush=True)
    if result.returncode or "Ran 29 tests in" not in result.stderr or "\nOK" not in result.stderr:
        raise ValueError("Candidate regression failed; do not promote")
    if factory.promote(ROOT) != {"stage": "improve", "slug": SLUG}:
        raise ValueError("Factory promote failed")
    expected_final = {**START_STATE, "cycle": 3}
    if factory.settings(ROOT)[1] != expected_final:
        raise ValueError("Unexpected post-promotion state")
    for name in ("main.py", "tests/test_smoke.py", "README.md"):
        if (ROOT / "products" / SLUG / name).read_bytes() != (candidate / name).read_bytes():
            raise ValueError("Promoted source differs from tested candidate")
    shutil.rmtree(ROOT / ".candidate")
    command(sys.executable, "-m", "unittest", "discover", "-s", "tests",
            "-v", env=env, timeout=180)
    command(sys.executable, "-m", "unittest", "discover",
            "-s", f"products/{SLUG}/tests", "-v", env=env, timeout=180)
    paths = ["factory/state.json"] + [
        f"products/{SLUG}/{name}" for name in ("main.py", "tests/test_smoke.py", "README.md")]
    command("git", "add", "--", *paths)
    staged = set(command("git", "diff", "--cached", "--name-only",
                         capture_output=True).stdout.splitlines())
    if staged != set(paths):
        raise ValueError("Unexpected staged paths: " + repr(staged))
    command("git", "diff", "--cached", "--check")
    remote = command("git", "ls-remote", "origin", "refs/heads/" + BRANCH,
                     capture_output=True).stdout.split()
    if not remote or remote[0] != start:
        raise ValueError("Concurrent branch update; HOLD")
    command("git", "-c", "user.name=github-actions[bot]",
            "-c", "user.email=41898282+github-actions[bot]@users.noreply.github.com",
            "commit", "-m", "feat(notes): add non-destructive backup restore action")
    remote = command("git", "ls-remote", "origin", "refs/heads/" + BRANCH,
                     capture_output=True).stdout.split()
    if not remote or remote[0] != start:
        raise ValueError("Concurrent update before push; HOLD")
    command("git", "push", "origin", "HEAD:refs/heads/" + BRANCH)
    sha = command("git", "rev-parse", "HEAD", capture_output=True).stdout.strip()
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
        output.write("source_sha=" + sha + "\n")
        output.write("request_id=app-offline-notes-canary-" + sha[:12] + "\n")
    print({"factory_product_generated": True, "source_sha": sha,
           "product_tests": 29, "identity_cas_allowed": False})

if __name__ == "__main__":
    run()
