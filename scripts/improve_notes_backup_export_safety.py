#!/usr/bin/env python3
"""Owner-controlled Offline Notes safety improvement; no Store or Identity mutations."""
import os
from pathlib import Path
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
                "cycle": 1, "revision": 1, "slug": SLUG}
    if state != expected:
        raise ValueError("Unexpected Factory state: " + repr(state))
    if factory.plan(ROOT) != expected:
        raise ValueError("Factory owner plan failed")

    candidate = ROOT / ".candidate" / "product"
    main = candidate / "main.py"
    source = main.read_text(encoding="utf-8")
    old_backup = '''    if path.exists():
        try:
            _, recovered = read_notes(path)
            if not recovered:
                atomic_write(path.with_name(path.name + ".bak"), path.read_bytes())
        except (OSError, ValueError):
            pass
    atomic_write(path, payload)
'''
    new_backup = '''    if path.exists():
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
    if source.count(old_backup) != 1:
        raise ValueError("Unexpected backup implementation; refuse blind edit")
    source = source.replace(old_backup, new_backup, 1)

    old_export = '''            path = Path(selected)
            if path.exists() and not messagebox.askyesno(self.t(0), self.t(17)):
                return
            atomic_write(path, (n["title"] + "\\n\\n" + n["body"] + "\\n").encode("utf-8"))
'''
    new_export = '''            path = Path(selected)
            if self.path is not None:
                active = Path(self.path).absolute()
                protected = (active, active.with_name(active.name + ".bak"))
                output = path.absolute()
                if any(output == item or (
                    path.exists() and item.exists() and os.path.samefile(path, item)
                ) for item in protected):
                    raise ValueError("TXT export cannot overwrite the notes database or backup")
            if path.exists() and not messagebox.askyesno(self.t(0), self.t(17)):
                return
            atomic_write(path, (n["title"] + "\\n\\n" + n["body"] + "\\n").encode("utf-8"))
'''
    if source.count(old_export) != 1:
        raise ValueError("Unexpected export implementation; refuse blind edit")
    main.write_text(source.replace(old_export, new_export, 1), encoding="utf-8")

    tests = candidate / "tests" / "test_smoke.py"
    original = tests.read_text(encoding="utf-8")
    anchor = "    def test_roundtrip(self):"
    extra = '''    def test_backup_failure_must_abort_save_without_overwriting_primary(self):
        save_notes(self.path, [self.note])
        original = self.path.read_bytes()
        with patch("main.atomic_write", side_effect=OSError("backup disk full")) as writer:
            with self.assertRaisesRegex(OSError, "backup disk full"):
                save_notes(self.path, [self.note, new_note()])
        self.assertEqual(writer.call_count, 1, "must not attempt primary write")
        self.assertEqual(writer.call_args.args[0], self.path.with_name("notes.json.bak"))
        self.assertEqual(self.path.read_bytes(), original)

    def test_txt_export_cannot_overwrite_open_notes_database(self):
        from main import App
        from unittest.mock import Mock
        save_notes(self.path, [self.note])
        original = self.path.read_bytes()
        app = App.__new__(App)
        app.notes, app.current, app.path = [dict(self.note)], self.note["id"], self.path
        app.lang, app.dirty = "en", True
        app.commit_editor, app.error = lambda: None, Mock()
        with (patch("main.filedialog.asksaveasfilename", return_value=str(self.path)),
              patch("main.messagebox.askyesno", return_value=True) as confirm):
            app.export()
        app.error.assert_called_once()
        confirm.assert_not_called()
        self.assertEqual(self.path.read_bytes(), original)
        self.assertTrue(app.dirty)

    def test_txt_export_cannot_overwrite_database_backup_name(self):
        from main import App
        from unittest.mock import Mock
        save_notes(self.path, [self.note])
        backup = self.path.with_name("notes.json.bak")
        app = App.__new__(App)
        app.notes, app.current, app.path = [dict(self.note)], self.note["id"], self.path
        app.lang, app.dirty = "ja", True
        app.commit_editor, app.error = lambda: None, Mock()
        with patch("main.filedialog.asksaveasfilename", return_value=str(backup)):
            app.export()
        app.error.assert_called_once()
        self.assertFalse(backup.exists(), "export must not create/overwrite backup")

    def test_txt_export_cannot_overwrite_hardlinked_database(self):
        import os
        from main import App
        from unittest.mock import Mock
        save_notes(self.path, [self.note])
        alias = self.path.with_name("export.txt")
        try:
            os.link(self.path, alias)
        except (OSError, NotImplementedError):
            self.skipTest("hardlinks unavailable")
        original = self.path.read_bytes()
        app = App.__new__(App)
        app.notes, app.current, app.path = [dict(self.note)], self.note["id"], self.path
        app.lang, app.dirty = "en", True
        app.commit_editor, app.error = lambda: None, Mock()
        with patch("main.filedialog.asksaveasfilename", return_value=str(alias)):
            app.export()
        app.error.assert_called_once()
        self.assertEqual(alias.read_bytes(), original)
        self.assertEqual(self.path.read_bytes(), original)

'''
    if original.count(anchor) != 1 or "test_backup_failure_must_abort_save" in original:
        raise ValueError("Unexpected regression tests; refuse blind edit")
    tests.write_text(original.replace(anchor, extra + anchor, 1), encoding="utf-8")

    readme = candidate / "README.md"
    readme.write_text(readme.read_text(encoding="utf-8").rstrip()
        + "\n\nSafety revision 2: if writing the previous-version backup fails, "
          "saving stops without replacing the primary notes database. TXT export "
          "refuses the currently open notes JSON file, its .bak path, and hardlink "
          "aliases even when the file chooser suggests an overwrite. Four headless "
          "regressions cover these protections; Windows GUI remains unverified.\n",
        encoding="utf-8")

    if factory.validate(ROOT) != {"stage": "improve", "slug": SLUG}:
        raise ValueError("Factory validation failed")
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    result = command(sys.executable, "-m", "unittest", "discover", "-s",
                     str(candidate / "tests"), "-v", env=env,
                     capture_output=True, timeout=180)
    print(result.stderr, flush=True)
    if "Ran 22 tests in" not in result.stderr or "\nOK" not in result.stderr:
        raise ValueError("22 product tests not established")
    if factory.promote(ROOT) != {"stage": "improve", "slug": SLUG}:
        raise ValueError("Owner Factory promote failed")
    if factory.settings(ROOT)[1] != {**expected, "revision": 2}:
        raise ValueError("Unexpected post-promotion state")
    for name in ("main.py", "tests/test_smoke.py", "README.md"):
        if (ROOT / "products" / SLUG / name).read_bytes() != (candidate / name).read_bytes():
            raise ValueError("Promoted source differs from tested candidate: " + name)
    command(sys.executable, "-m", "unittest", "discover", "-s", "tests",
            "-v", env=env, timeout=180)
    command(sys.executable, "-m", "unittest", "discover", "-s",
            f"products/{SLUG}/tests", "-v", env=env, timeout=180)

    paths = ["factory/state.json"] + [
        f"products/{SLUG}/{name}" for name in ("main.py", "tests/test_smoke.py", "README.md")
    ]
    command("git", "add", "--", *paths)
    command("git", "add", "-f", "--", ".candidate/product/main.py",
            ".candidate/product/tests/test_smoke.py", ".candidate/product/README.md")
    staged = set(command("git", "diff", "--cached", "--name-only",
                         capture_output=True).stdout.splitlines())
    allowed = set(paths) | {".candidate/product/main.py",
                            ".candidate/product/tests/test_smoke.py",
                            ".candidate/product/README.md"}
    if staged != allowed:
        raise ValueError("Unexpected staged changes: " + repr(sorted(staged)))
    command("git", "diff", "--cached", "--check")
    remote = command("git", "ls-remote", "origin", "refs/heads/" + BRANCH,
                     capture_output=True).stdout.split()
    if not remote or remote[0] != start:
        raise ValueError("Concurrent branch update; refuse blind push")
    command("git", "-c", "user.name=github-actions[bot]",
            "-c", "user.email=41898282+github-actions[bot]@users.noreply.github.com",
            "commit", "-m", "fix(notes): protect primary and backup during save and TXT export")
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
           "request_id": request_id, "product_tests": 22})


if __name__ == "__main__":
    run()
