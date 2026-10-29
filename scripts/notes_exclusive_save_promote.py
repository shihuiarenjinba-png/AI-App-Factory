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

BRANCH = "codex/app-notes-exclusive-save-20261030"
SLUG = "offline-notes-canary"
START = {"schema": 1, "kind": "app", "stage": "research",
         "cycle": 6, "revision": 0, "slug": None}


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
        'def save_notes(path, notes):\n    validate_notes(notes)\n'
        '    schema = 2 if any("tags" in n or "favorite" in n for n in notes) else 1\n'
        '    payload = (json.dumps({"schema": schema, "notes": notes}, ensure_ascii=False, indent=2) + "\\n").encode("utf-8")\n'
        '    if len(payload) > 5000000:\n'
        '        raise ValueError("Notes exceed 5 MB")\n',
        'def notes_payload(notes):\n'
        '    validate_notes(notes)\n'
        '    schema = 2 if any("tags" in n or "favorite" in n for n in notes) else 1\n'
        '    payload = (json.dumps({"schema": schema, "notes": notes}, ensure_ascii=False, indent=2) + "\\n").encode("utf-8")\n'
        '    if len(payload) > 5000000:\n'
        '        raise ValueError("Notes exceed 5 MB")\n'
        '    return payload\n\n'
        'def save_notes_new(path, notes):\n'
        '    """Atomically create a new notes file, never replacing a competing path."""\n'
        '    payload = notes_payload(notes)\n'
        '    path = Path(path)\n'
        '    if not path.parent.is_dir():\n'
        '        raise ValueError("Choose an existing destination folder")\n'
        '    temp = None\n'
        '    try:\n'
        '        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".notes-", delete=False) as f:\n'
        '            temp = Path(f.name)\n'
        '            f.write(payload)\n'
        '            f.flush()\n'
        '            os.fsync(f.fileno())\n'
        '        # Hard-link creation is atomic and fails if the destination exists,\n'
        '        # including when another process creates it after the file dialog.\n'
        '        # Unsupported filesystems fail closed rather than falling back to replace.\n'
        '        os.link(temp, path)\n'
        '    finally:\n'
        '        if temp is not None:\n'
        '            temp.unlink(missing_ok=True)\n\n'
        'def save_notes(path, notes):\n'
        '    payload = notes_payload(notes)\n',
        "Share validated serialization and add exclusive atomic create")
    source = replace_once(source,
        '            if destination.exists() or destination.is_symlink():\n'
        '                raise ValueError("Save As requires a new, unused filename")\n'
        '            save_notes(destination, self.notes)\n',
        '            save_notes_new(destination, self.notes)\n',
        "Save As no-clobber")
    source = replace_once(source,
        '            if destination.exists() or destination.is_symlink():\n'
        '                raise ValueError("Restore requires a new, unused filename")\n'
        '            save_notes(destination, recovered_notes)\n',
        '            save_notes_new(destination, recovered_notes)\n',
        "Restore backup no-clobber")
    source_file.write_text(source, encoding="utf-8")

    test_file = candidate / "tests/test_commercial_metadata.py"
    tests = test_file.read_text(encoding="utf-8")
    tests = replace_once(tests, 'import json\n', 'import json\nimport os\n',
                         "Test os.link race")
    regressions = '''    def test_save_as_concurrent_create_preserves_other_process_file(self):
        original = self.path
        save_notes(original, [self.note])
        old_bytes = original.read_bytes()
        app = App.__new__(App)
        app.notes, app.path, app.dirty, app.lang = [self.note], original, True, "en"
        app.commit_editor, app.refresh_list, app.status = Mock(), Mock(), Mock()
        app.error = Mock()
        destination = Path(self.tmp.name) / "raced.json"
        actual_link = os.link

        def competing_create(src, dst):
            Path(dst).write_bytes(b"OTHER PROCESS DATA")
            return actual_link(src, dst)

        with patch("main.filedialog.asksaveasfilename", return_value=str(destination)), \\
             patch("main.os.link", side_effect=competing_create):
            self.assertFalse(app.save_as())
        self.assertEqual(destination.read_bytes(), b"OTHER PROCESS DATA")
        self.assertEqual(original.read_bytes(), old_bytes)
        self.assertEqual(app.path, original)
        self.assertTrue(app.dirty)
        self.assertEqual(list(Path(self.tmp.name).glob(".notes-*")), [])
        app.error.assert_called_once()

    def test_exclusive_create_failure_leaves_no_partial_output(self):
        from main import save_notes_new
        destination = Path(self.tmp.name) / "denied.json"
        with patch("main.os.link", side_effect=PermissionError("Hardlinks unavailable")):
            with self.assertRaises(PermissionError):
                save_notes_new(destination, [self.note])
        self.assertFalse(destination.exists())
        self.assertEqual(list(Path(self.tmp.name).glob(".notes-*")), [])

    def test_restore_backup_concurrent_create_preserves_competing_file(self):
        backup = Path(self.tmp.name) / "source.json.bak"
        save_notes(backup, [self.note])
        destination = Path(self.tmp.name) / "restore-raced.json"
        app = App.__new__(App)
        app.notes, app.path, app.dirty, app.lang = [], self.path, True, "ja"
        app.confirm, app.error = Mock(return_value=True), Mock()
        actual_link = os.link

        def competing_create(src, dst):
            Path(dst).write_bytes(b"DO NOT REPLACE")
            return actual_link(src, dst)

        with patch("main.filedialog.askopenfilename", return_value=str(backup)), \\
             patch("main.filedialog.asksaveasfilename", return_value=str(destination)), \\
             patch("main.os.link", side_effect=competing_create):
            app.restore_backup()
        self.assertEqual(destination.read_bytes(), b"DO NOT REPLACE")
        self.assertEqual(app.notes, [])
        self.assertEqual(app.path, self.path)
        self.assertTrue(app.dirty)
        app.error.assert_called_once()

'''
    tests = replace_once(tests, '    def test_schema1_backward_compatibility(self):\n',
                         regressions + '    def test_schema1_backward_compatibility(self):\n',
                         "No-clobber race regressions")
    test_file.write_text(tests, encoding="utf-8")
    readme = candidate / "README.md"
    readme.write_text(readme.read_text(encoding="utf-8").rstrip() +
        "\n\nExclusive Save As and Restore: new files are written to a synced "
        "temporary file and published with an atomic no-clobber hard link. "
        "A concurrent file creation, existing symlink, or unsupported hardlink "
        "filesystem fails closed without overwriting the other file. "
        "Three regression tests exercise concurrent creation and cleanup.\n",
        encoding="utf-8")

    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    result = subprocess.run(
        (sys.executable, "-m", "unittest", "discover",
         "-s", str(candidate / "tests"), "-p", "test*.py", "-v"),
        cwd=ROOT, text=True, capture_output=True, env=env, timeout=180)
    print(result.stdout, result.stderr, flush=True)
    match = re.search(r"Ran (\d+) tests in", result.stderr)
    if result.returncode or not match or int(match.group(1)) < 48 or "\nOK" not in result.stderr:
        raise ValueError("Candidate tests failed; HOLD without promote")
    if factory.validate(ROOT) != {"stage": "improve", "slug": SLUG}:
        raise ValueError("Candidate validation mismatch")
    if factory.promote(ROOT) != {"stage": "improve", "slug": SLUG}:
        raise ValueError("Factory promotion mismatch")
    if factory.settings(ROOT)[1] != {**START, "cycle": 7}:
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
        "commit", "-m", "fix(notes): promote atomic no-clobber Save As and Restore")
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
