#!/usr/bin/env python3
"""Factory owner/controller: promote Offline Notes search highlights safely.

This is NOT an agent editing Factory state. All product edits are made in the
candidate, validated and tested, then promoted with a remote-head lease.
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import factory

BRANCH = "codex/app-notes-search-highlight-promote-20261029"
SLUG = "offline-notes-canary"
START = {"schema": 1, "kind": "app", "stage": "research",
         "cycle": 3, "revision": 0, "slug": None}


def run_cmd(*args, **kwargs):
    return subprocess.run(args, cwd=ROOT, check=True, text=True, **kwargs)


def replace_once(text, old, new, label):
    if text.count(old) != 1:
        raise ValueError("Source layout changed, HOLD: " + label)
    return text.replace(old, new, 1)


def main():
    if os.environ.get("GITHUB_REF") != "refs/heads/" + BRANCH:
        raise ValueError("Ref mismatch")
    initial = run_cmd("git", "rev-parse", "HEAD", capture_output=True).stdout.strip()
    if initial != os.environ.get("GITHUB_SHA"):
        raise ValueError("Event HEAD mismatch")
    if run_cmd("git", "symbolic-ref", "--short", "HEAD",
               capture_output=True).stdout.strip() != BRANCH:
        raise ValueError("Wrong checkout")
    if run_cmd("git", "status", "--porcelain", capture_output=True).stdout.strip():
        raise ValueError("Dirty checkout")
    if factory.settings(ROOT)[1] != START or (ROOT / ".candidate").exists():
        raise ValueError("Unexpected state or stale candidate: HOLD")

    # Owner-authorized reentry of an existing product only. No new APP.
    state = {**START, "stage": "improve", "revision": 2, "slug": SLUG}
    factory.save(ROOT / "factory/state.json", state)
    if factory.plan(ROOT) != state:
        raise ValueError("Factory plan mismatch")
    candidate = ROOT / ".candidate/product"
    source_file = candidate / "main.py"
    source = source_file.read_text(encoding="utf-8")
    matcher = '''def find_matches(text, query, limit=200):
    """Return bounded, non-overlapping offsets for a visible search highlight."""
    if not isinstance(text, str) or not isinstance(query, str):
        raise ValueError("Search requires text")
    needle = query.strip()
    if not needle or len(needle) > 200:
        return []
    return [(match.start(), match.end()) for _, match in zip(
        range(limit), re.finditer(re.escape(needle), text, flags=re.IGNORECASE))]

'''
    source = replace_once(source, "def safe_filename(title):\n",
                          matcher + "def safe_filename(title):\n", "match helper")
    source = replace_once(source,
        'self.body.bind("<<Modified>>", self.body_changed)',
        'self.body.bind("<<Modified>>", self.body_changed)\n'
        '        self.body.tag_configure("search_match", background="#ffe59a")',
        "highlight tag")
    source = replace_once(source,
        'self.query.trace_add("write", lambda *_: self.refresh_list())',
        'self.query.trace_add("write", lambda *_: (self.refresh_list(), self.highlight_search()))',
        "search trace")
    source = replace_once(source,
        '    def body_changed(self, _event=None):\n'
        '        if self.body.edit_modified():\n'
        '            self.body.edit_modified(False)\n'
        '            self.changed()\n',
        '    def body_changed(self, _event=None):\n'
        '        if self.body.edit_modified():\n'
        '            self.body.edit_modified(False)\n'
        '            self.changed()\n'
        '            self.highlight_search()\n',
        "live body highlights")
    highlight = '''    def highlight_search(self):
        """Highlight matches in the active note body; never modify note data."""
        self.body.tag_remove("search_match", "1.0", "end")
        if not self.current:
            return
        query = self.query.get()
        if not query.strip():
            return
        text = self.body.get("1.0", "end-1c")
        for start, end in find_matches(text, query):
            self.body.tag_add("search_match", f"1.0+{start}c", f"1.0+{end}c")

'''
    source = replace_once(source, "    def select(self, _event=None):\n",
                          highlight + "    def select(self, _event=None):\n",
                          "search highlight method")
    source = replace_once(source,
        '        self.loading = False\n        self.refresh_list()\n\n    def select',
        '        self.loading = False\n        self.refresh_list()\n'
        '        self.highlight_search()\n\n    def select',
        "highlight on note switch") if False else source
    # Use a unique anchor that remains valid after inserting highlight_search.
    source = replace_once(source,
        '        self.body.edit_modified(False)\n'
        '        self.loading = False\n'
        '        self.refresh_list()\n',
        '        self.body.edit_modified(False)\n'
        '        self.loading = False\n'
        '        self.refresh_list()\n'
        '        self.highlight_search()\n',
        "highlight on note switch")
    source_file.write_text(source, encoding="utf-8")

    test_file = candidate / "tests/test_commercial_metadata.py"
    tests = test_file.read_text(encoding="utf-8")
    tests = replace_once(tests,
        "from main import App, new_note, normalize_tags, read_notes, save_notes, search_notes, validate_notes",
        "from main import App, find_matches, new_note, normalize_tags, read_notes, save_notes, search_notes, validate_notes",
        "test import")
    new_tests = '''    def test_search_match_offsets_unicode_case_and_bounds(self):
        self.assertEqual(find_matches("alpha ALPHA alpha", "alpha"),
                         [(0, 5), (6, 11), (12, 17)])
        self.assertEqual(find_matches("メモで検索メモ", "メモ"), [(0, 2), (5, 7)])
        self.assertEqual(find_matches("abc", ""), [])
        self.assertEqual(find_matches("aaaaa", "a", limit=2), [(0, 1), (1, 2)])

    def test_body_highlights_are_visual_only_and_cleared(self):
        app = App.__new__(App)
        app.current = self.note["id"]
        app.body, app.query = Mock(), Mock()
        app.body.get.return_value = "Alpha alpha"
        app.query.get.return_value = "alpha"
        app.highlight_search()
        self.assertEqual(app.body.tag_add.call_count, 2)
        app.body.tag_add.assert_any_call("search_match", "1.0+0c", "1.0+5c")
        app.body.tag_add.assert_any_call("search_match", "1.0+6c", "1.0+11c")
        app.query.get.return_value = ""
        app.highlight_search()
        self.assertEqual(app.body.tag_remove.call_count, 2)
        self.assertEqual(app.body.tag_add.call_count, 2)

'''
    tests = replace_once(tests, "    def test_schema1_backward_compatibility(self):\n",
                         new_tests + "    def test_schema1_backward_compatibility(self):\n",
                         "regression tests")
    test_file.write_text(tests, encoding="utf-8")
    readme = candidate / "README.md"
    readme.write_text(readme.read_text(encoding="utf-8").rstrip() +
        "\n\nCommercial search increment: while searching, visible matches in the "
        "selected note body are highlighted in place (up to 200 matches). "
        "No data is altered by search; matching and clearing are headlessly tested. "
        "Windows GUI 1024x768 and consumer review remain unverified.\n",
        encoding="utf-8")

    if factory.validate(ROOT) != {"stage": "improve", "slug": SLUG}:
        raise ValueError("Factory validation mismatch")
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    result = subprocess.run(
        (sys.executable, "-m", "unittest", "discover",
         "-s", str(candidate / "tests"), "-p", "test*.py", "-v"),
        cwd=ROOT, text=True, capture_output=True, env=env, timeout=180)
    print(result.stdout, result.stderr, flush=True)
    if result.returncode or "Ran 39 tests in" not in result.stderr or "\nOK" not in result.stderr:
        raise ValueError("Candidate tests failed; HOLD without promote")
    if factory.promote(ROOT) != {"stage": "improve", "slug": SLUG}:
        raise ValueError("Factory promote failed")
    expected = {**START, "cycle": 4}
    if factory.settings(ROOT)[1] != expected:
        raise ValueError("Post-promotion state mismatch")
    for path in candidate.rglob("*"):
        if path.is_file():
            dest = ROOT / "products" / SLUG / path.relative_to(candidate)
            if dest.read_bytes() != path.read_bytes():
                raise ValueError("Promoted file differs from tested candidate")
    shutil.rmtree(ROOT / ".candidate")
    run_cmd(sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v",
            env=env, timeout=180)
    run_cmd(sys.executable, "-m", "unittest", "discover",
            "-s", f"products/{SLUG}/tests", "-p", "test*.py", "-v",
            env=env, timeout=180)
    paths = ["factory/state.json", f"products/{SLUG}/main.py",
             f"products/{SLUG}/tests/test_commercial_metadata.py",
             f"products/{SLUG}/README.md"]
    run_cmd("git", "add", "--", *paths)
    staged = set(run_cmd("git", "diff", "--cached", "--name-only",
                         capture_output=True).stdout.splitlines())
    if staged != set(paths):
        raise ValueError("Unexpected staged paths: " + repr(staged))
    run_cmd("git", "diff", "--cached", "--check")
    def remote_sha():
        output = run_cmd("git", "ls-remote", "origin", "refs/heads/" + BRANCH,
                         capture_output=True).stdout.split()
        return output[0] if output else None
    if remote_sha() != initial:
        raise ValueError("Remote changed before commit: HOLD")
    run_cmd("git", "-c", "user.name=github-actions[bot]",
            "-c", "user.email=41898282+github-actions[bot]@users.noreply.github.com",
            "commit", "-m", "feat(notes): promote bounded search highlights")
    if remote_sha() != initial:
        raise ValueError("Remote changed before push: HOLD")
    run_cmd("git", "push", "origin", "HEAD:refs/heads/" + BRANCH)
    sha = run_cmd("git", "rev-parse", "HEAD", capture_output=True).stdout.strip()
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
        output.write("source_sha=" + sha + "\n")
        output.write("request_id=app-offline-notes-canary-" + sha[:12] + "\n")
    print({"factory_product_generated": True, "source_sha": sha,
           "candidate_tests": 39, "identity_cas_allowed": False})


if __name__ == "__main__":
    main()
