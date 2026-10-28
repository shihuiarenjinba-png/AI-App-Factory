#!/usr/bin/env python3
"""Owner-controlled image inventory improvement: never drop old snapshot rows on Add."""
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import factory

BRANCH = "codex/app-image-inventory-append-safety-20261029"
SLUG = "offline-image-inventory-desk"


def cmd(*args, **kwargs):
    return subprocess.run(args, check=True, text=True, **kwargs)


def run():
    if os.environ.get("GITHUB_REF") != "refs/heads/" + BRANCH:
        raise ValueError("Wrong workflow ref")
    start = cmd("git", "rev-parse", "HEAD", capture_output=True).stdout.strip()
    if start != os.environ.get("GITHUB_SHA"):
        raise ValueError("Event source SHA mismatch")
    branch = cmd("git", "symbolic-ref", "--short", "HEAD", capture_output=True).stdout.strip()
    if branch != BRANCH or cmd("git", "status", "--porcelain", capture_output=True).stdout.strip():
        raise ValueError("Dirty or unexpected checkout")
    _, state = factory.settings(ROOT)
    expected = {"schema": 1, "kind": "app", "stage": "improve", "cycle": 1,
                "revision": 1, "slug": SLUG}
    if state != expected:
        raise ValueError("Unexpected lifecycle state: " + repr(state))

    # Only the owner controller may create the candidate and promote it.
    if factory.plan(ROOT)["stage"] != "improve":
        raise ValueError("Improvement plan not created")
    candidate = ROOT / ".candidate" / "product"
    main = candidate / "main.py"
    code = main.read_text(encoding="utf-8")
    anchor = "def validate_session(value):"
    addition = '''def append_images(existing, paths):
    """Append new files without rescanning or silently dropping saved inventory rows."""
    if not isinstance(existing, list) or not isinstance(paths, (list, tuple)):
        raise ValueError("Invalid inventory")
    if len(existing) + len(paths) > MAX_ITEMS:
        raise ValueError("Too many images")
    rows = list(existing)
    errors = []
    seen = {row["path"] for row in existing}
    for item in paths:
        try:
            if not isinstance(item, (str, Path)):
                raise ValueError("Invalid path")
            path = Path(item).absolute()
            if len(str(path)) > 4096 or str(path) in seen:
                raise ValueError("Duplicate or oversized path")
            seen.add(str(path))
            rows.append(inspect_image(path))
        except (OSError, ValueError, struct.error) as exc:
            errors.append((str(item), str(exc)))
    return rows, errors


'''
    if code.count(anchor) != 1 or "def append_images(" in code:
        raise ValueError("Unexpected image inventory code")
    code = code.replace(anchor, addition + anchor)
    before = 'try:rows,errors=scan([r["path"] for r in self.rows]+list(paths))'
    after = 'try:rows,errors=append_images(self.rows,list(paths))'
    if code.count(before) != 1:
        raise ValueError("Unexpected Add handler")
    main.write_text(code.replace(before, after), encoding="utf-8")

    tests = candidate / "tests" / "test_smoke.py"
    original = tests.read_text(encoding="utf-8")
    test_anchor = "    def test_session_roundtrip(self):"
    extra = '''    def test_append_preserves_snapshot_if_old_file_disappears(self):
        old = app.inspect_image(self.png)
        self.png.unlink()
        new = self.d / "new.gif"
        new.write_bytes(b"GIF89a" + struct.pack("<HH", 12, 34))
        rows, errors = app.append_images([old], [new])
        self.assertEqual(errors, [])
        self.assertEqual(rows[0], old)
        self.assertEqual((rows[1]["width"], rows[1]["height"]), (12, 34))

    def test_append_duplicate_does_not_modify_existing_rows(self):
        old = app.inspect_image(self.png)
        rows, errors = app.append_images([old], [self.png])
        self.assertEqual(rows, [old])
        self.assertEqual(len(errors), 1)
        self.assertIn("Duplicate", errors[0][1])

    def test_append_bad_new_file_preserves_existing_rows(self):
        old = app.inspect_image(self.png)
        rows, errors = app.append_images([old], [self.d / "missing.png"])
        self.assertEqual(rows, [old])
        self.assertEqual(len(errors), 1)

'''
    if original.count(test_anchor) != 1 or "test_append_preserves_snapshot" in original:
        raise ValueError("Unexpected product regression tests")
    tests.write_text(original.replace(test_anchor, extra + test_anchor), encoding="utf-8")

    if factory.validate(ROOT) != {"stage": "improve", "slug": SLUG}:
        raise ValueError("Factory candidate validation failed")
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    test = cmd(sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v",
               cwd=candidate, capture_output=True, env=env, timeout=120)
    if "Ran 26 tests in" not in test.stderr or "FAILED" in test.stderr or "skipped=" in test.stderr:
        raise ValueError("26 unskipped image product tests not established")
    print(test.stderr, flush=True)

    if factory.promote(ROOT) != {"stage": "improve", "slug": SLUG}:
        raise ValueError("Owner-controlled promote failed")
    if factory.settings(ROOT)[1]["revision"] != 2:
        raise ValueError("Revision 2 was not reached")
    cmd(sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v",
        cwd=ROOT, env=env, timeout=180)

    paths = ["factory/state.json", f"products/{SLUG}/main.py",
             f"products/{SLUG}/tests/test_smoke.py"]
    cmd("git", "add", "--", *paths)
    cmd("git", "add", "-u", "--", ".candidate/product/main.py",
        ".candidate/product/tests/test_smoke.py")
    staged = set(cmd("git", "diff", "--cached", "--name-only",
                     capture_output=True).stdout.splitlines())
    allowed = set(paths) | {".candidate/product/main.py",
                            ".candidate/product/tests/test_smoke.py"}
    if staged != allowed:
        raise ValueError("Unexpected staged paths: " + repr(sorted(staged)))
    cmd("git", "diff", "--cached", "--check")
    cmd("git", "-c", "user.name=github-actions[bot]",
        "-c", "user.email=41898282+github-actions[bot]@users.noreply.github.com",
        "commit", "-m", "fix(image-inventory): preserve prior rows when adding images")
    remote = cmd("git", "ls-remote", "origin", "refs/heads/" + BRANCH,
                 capture_output=True).stdout.split()[0]
    if remote != start:
        raise ValueError("Concurrent branch update; refuse blind push")
    cmd("git", "push", "origin", "HEAD:refs/heads/" + BRANCH)
    sha = cmd("git", "rev-parse", "HEAD", capture_output=True).stdout.strip()
    request = "app-offline-image-inventory-desk-" + sha[:12]
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
        output.write(f"source_sha={sha}\nrequest_id={request}\n")
    print({"FACTORY_IMPROVEMENT_PASS": True, "source_sha": sha,
           "request_id": request, "product_tests": 26})


if __name__ == "__main__":
    run()
