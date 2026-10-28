#!/usr/bin/env python3
"""Owner-controlled Text Diff improvement: prevent backup collisions and partial backup writes."""
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import factory

BRANCH = "codex/app-text-diff-backup-safety-20261029"
SLUG = "offline-text-diff-desk"


def command(*args, **kwargs):
    return subprocess.run(args, check=True, text=True, **kwargs)


def run():
    if os.environ.get("GITHUB_REF") != "refs/heads/" + BRANCH:
        raise ValueError("Unexpected workflow branch")
    start = command("git", "rev-parse", "HEAD", capture_output=True).stdout.strip()
    if start != os.environ.get("GITHUB_SHA"):
        raise ValueError("Event SHA mismatch")
    current = command("git", "symbolic-ref", "--short", "HEAD", capture_output=True).stdout.strip()
    if current != BRANCH or command("git", "status", "--porcelain", capture_output=True).stdout.strip():
        raise ValueError("Dirty or wrong checkout")
    _, state = factory.settings(ROOT)
    expected = {"schema": 1, "kind": "app", "stage": "improve",
                "cycle": 1, "revision": 2, "slug": SLUG}
    if state != expected:
        raise ValueError("Unexpected lifecycle state: " + repr(state))
    if factory.plan(ROOT)["stage"] != "improve":
        raise ValueError("Factory owner plan failed")

    candidate = ROOT / ".candidate" / "product"
    main = candidate / "main.py"
    source = main.read_text(encoding="utf-8")
    anchor = "def write_atomic(path, content, protected=()):\n"
    after = "\ndef save_session(path,session):"
    if source.count(anchor) != 1 or source.count(after) != 1:
        raise ValueError("Unexpected product source")
    before, remainder = source.split(anchor, 1)
    _, suffix = remainder.split(after, 1)
    replacement = '''def write_atomic(path, content, protected=()):
    p = Path(path).absolute()
    backup = p.with_name(p.name + ".bak")
    sources = {Path(item).absolute() for item in protected}
    # Both the requested output AND its implicit .bak are write targets.
    # A source document can have the exact .bak name or be hardlinked to it.
    for target in (p, backup):
        if target.is_symlink() or target in sources:
            raise ValueError("Output or backup overlaps a source document")
        if target.exists() and not target.is_file():
            raise ValueError("Output and backup must be regular files")
        if target.exists() and any(
            src.exists() and os.path.samefile(target, src) for src in sources
        ):
            raise ValueError("Output or backup aliases a source document")
    if not p.parent.is_dir() or p.parent.is_symlink():
        raise ValueError("Output folder missing or linked")

    # Write the new output first, before modifying any existing backup.
    fd, tmp = tempfile.mkstemp(prefix=".text-diff-", dir=p.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        if p.exists():
            backup_fd, backup_tmp = tempfile.mkstemp(
                prefix=".text-diff-backup-", dir=p.parent
            )
            try:
                with os.fdopen(backup_fd, "wb") as writer, p.open("rb") as reader:
                    shutil.copyfileobj(reader, writer)
                    writer.flush()
                    os.fsync(writer.fileno())
                os.replace(backup_tmp, backup)
            finally:
                if os.path.exists(backup_tmp):
                    os.unlink(backup_tmp)
        os.replace(tmp, p)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
'''
    # Preserve literal Python backslash-n in the generated source, not a newline in quotes.
    replacement = replacement.replace('newline="\n"', 'newline="\\n"')
    main.write_text(before + replacement + after + suffix, encoding="utf-8")

    tests = candidate / "tests" / "test_smoke.py"
    original = tests.read_text(encoding="utf-8")
    test_anchor = "    def test_session_roundtrip(self):"
    extra = '''    def test_export_backup_name_cannot_clobber_source(self):
        source = self.dir / "report.diff.bak"
        source.write_text("ORIGINAL SOURCE", encoding="utf-8")
        output = self.dir / "report.diff"
        output.write_text("old report", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "source document"):
            app.export_diff(output, app.compare("a", "b"), source, self.right)
        self.assertEqual(source.read_text(encoding="utf-8"), "ORIGINAL SOURCE")
        self.assertEqual(output.read_text(encoding="utf-8"), "old report")

    def test_export_rejects_hardlinked_backup_alias(self):
        source = self.dir / "protected.txt"
        source.write_text("PRIVATE SOURCE", encoding="utf-8")
        output = self.dir / "report.diff"
        output.write_text("old report", encoding="utf-8")
        try:
            os.link(source, self.dir / "report.diff.bak")
        except (OSError, NotImplementedError):
            self.skipTest("hardlinks unavailable")
        with self.assertRaisesRegex(ValueError, "source document"):
            app.export_diff(output, app.compare("a", "b"), source, self.right)
        self.assertEqual(source.read_text(encoding="utf-8"), "PRIVATE SOURCE")

    def test_failed_backup_replacement_preserves_previous_versions(self):
        output = self.dir / "report.diff"
        backup = self.dir / "report.diff.bak"
        output.write_text("CURRENT", encoding="utf-8")
        backup.write_text("PREVIOUS", encoding="utf-8")
        with mock.patch.object(app.os, "replace", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                app.export_diff(output, app.compare("a", "b"), self.left, self.right)
        self.assertEqual(output.read_text(encoding="utf-8"), "CURRENT")
        self.assertEqual(backup.read_text(encoding="utf-8"), "PREVIOUS")

'''
    if original.count(test_anchor) != 1 or "test_export_backup_name_cannot_clobber_source" in original:
        raise ValueError("Unexpected product tests")
    original = original.replace("import json\n", "import json\nimport os\nfrom unittest import mock\n", 1)
    tests.write_text(original.replace(test_anchor, extra + test_anchor), encoding="utf-8")

    readme = candidate / "README.md"
    readme.write_text(
        readme.read_text(encoding="utf-8").rstrip()
        + "\n\nSafety update: the explicit output and its automatic .bak are both checked "
          "against protected source documents (including hardlinks). New output and "
          "replacement backup are written to temporary files before atomic replacement; "
          "failed backup writes preserve the previous output and backup.\n",
        encoding="utf-8"
    )
    if factory.validate(ROOT) != {"stage": "improve", "slug": SLUG}:
        raise ValueError("Candidate validation failed")
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    product_test = command(
        sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v",
        cwd=candidate, capture_output=True, env=env, timeout=120
    )
    if "Ran 22 tests in" not in product_test.stderr or "FAILED" in product_test.stderr:
        raise ValueError("22 product tests not established")
    print(product_test.stderr, flush=True)
    if factory.promote(ROOT) != {"stage": "improve", "slug": SLUG}:
        raise ValueError("Factory promotion failed")
    # Final improvement of cycle 1 returns the controller to research cycle 2;
    # it does NOT authorize creating a sixth product.
    _, final = factory.settings(ROOT)
    if final != {"schema": 1, "kind": "app", "stage": "research",
                 "cycle": 2, "revision": 0, "slug": None}:
        raise ValueError("Unexpected post-promotion lifecycle: " + repr(final))
    command(sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v",
            cwd=ROOT, env=env, timeout=180)

    paths = ["factory/state.json", f"products/{SLUG}/main.py",
             f"products/{SLUG}/tests/test_smoke.py", f"products/{SLUG}/README.md"]
    command("git", "add", "--", *paths)
    command("git", "add", "-u", "--", ".candidate/product/main.py",
            ".candidate/product/tests/test_smoke.py", ".candidate/product/README.md")
    staged = set(command("git", "diff", "--cached", "--name-only",
                         capture_output=True).stdout.splitlines())
    allowed = set(paths) | {".candidate/product/main.py",
                            ".candidate/product/tests/test_smoke.py",
                            ".candidate/product/README.md"}
    if staged != allowed:
        raise ValueError("Unexpected staged files: " + repr(sorted(staged)))
    command("git", "diff", "--cached", "--check")
    command("git", "-c", "user.name=github-actions[bot]",
            "-c", "user.email=41898282+github-actions[bot]@users.noreply.github.com",
            "commit", "-m", "fix(text-diff): guard source files and atomically replace backups")
    remote = command("git", "ls-remote", "origin", "refs/heads/" + BRANCH,
                     capture_output=True).stdout.split()[0]
    if remote != start:
        raise ValueError("Concurrent update; refuse blind push")
    command("git", "push", "origin", "HEAD:refs/heads/" + BRANCH)
    sha = command("git", "rev-parse", "HEAD", capture_output=True).stdout.strip()
    request_id = "app-offline-text-diff-desk-" + sha[:12]
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
        output.write(f"source_sha={sha}\nrequest_id={request_id}\n")
    print({"FACTORY_IMPROVEMENT_PASS": True, "source_sha": sha,
           "request_id": request_id, "product_tests": 22})


if __name__ == "__main__":
    run()
