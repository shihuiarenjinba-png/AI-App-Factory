#!/usr/bin/env python3
"""Factory owner/controller: promote Offline Notes search highlights safely.

This is NOT an agent editing Factory state. All product edits are made in the
candidate, validated and tested, then promoted with a remote-head lease.
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

BRANCH = "codex/app-notes-search-highlight-promote-20261029"
SLUG = "offline-notes-canary"
START = {"schema": 1, "kind": "app", "stage": "research",
         "cycle": 4, "revision": 0, "slug": None}


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
    # Add a genuine, optional favorites-only filter to the existing search UI.
    # The filter does not alter saved notes or silently change selection.
    source = replace_once(source,
        '        left.rowconfigure(2, weight=1)\n',
        '        left.rowconfigure(3, weight=1)\n', "sidebar grid")
    source = replace_once(source,
        '        self.recent_ids = []\n',
        '        self.recent_ids = []\n'
        '        self.favorites_only = tk.BooleanVar(value=False)\n',
        "filter state")
    source = replace_once(source,
        '        self.listbox = tk.Listbox(left, exportselection=False)\n'
        '        self.listbox.grid(row=2, column=0, sticky="nsew")\n',
        '        self.favorites_check = ttk.Checkbutton(\n'
        '            left, variable=self.favorites_only, command=self.refresh_list)\n'
        '        self.favorites_check.grid(row=2, column=0, sticky="w", pady=(5, 3))\n'
        '        self.listbox = tk.Listbox(left, exportselection=False)\n'
        '        self.listbox.grid(row=3, column=0, sticky="nsew")\n',
        "sidebar checkbox")
    source = replace_once(source,
        '        self.search_label.configure(text=self.t(7))\n',
        '        self.search_label.configure(text=self.t(7))\n'
        '        self.favorites_check.configure(text=self.t(23))\n',
        "translated filter")
    source = replace_once(source,
        '        filtered = search_notes(notes, self.query.get())\n',
        '        filtered = search_notes(notes, self.query.get())\n'
        '        only_favorites = getattr(self, "favorites_only", None)\n'
        '        if only_favorites is not None and only_favorites.get():\n'
        '            filtered = [n for n in filtered if n.get("favorite", False)]\n',
        "filter results")
    source = replace_once(source,
        '"★ お気に入り"],',
        '"★ お気に入り", "お気に入りのみ"],', "Japanese label")
    source = replace_once(source,
        '"★ Favorited"]',
        '"★ Favorited", "Favorites only"]', "English label")
    source_file.write_text(source, encoding="utf-8")

    test_file = candidate / "tests/test_commercial_metadata.py"
    tests = test_file.read_text(encoding="utf-8")
    new_tests = '''    def test_favorites_only_filters_without_mutating_notes(self):
        favorite = {**self.note, "favorite": True}
        other = new_note()
        other.update(title="Report two", body="Other report")
        favorite["title"] = "Report one"
        app = App.__new__(App)
        app.notes, app.current, app.loading = [favorite, other], None, False
        app.recent_ids = []
        app.query, app.listbox, app.favorites_only = Mock(), Mock(), Mock()
        app.query.get.return_value = "report"
        app.favorites_only.get.return_value = True
        app.refresh_list()
        self.assertEqual(app.visible, [favorite["id"]])
        app.favorites_only.get.return_value = False
        app.refresh_list()
        self.assertEqual(set(app.visible), {favorite["id"], other["id"]})
        self.assertEqual(app.notes, [favorite, other])

    def test_favorites_only_empty_state_and_bilingual_label(self):
        from main import STRINGS
        self.assertEqual(STRINGS["ja"][23], "お気に入りのみ")
        self.assertEqual(STRINGS["en"][23], "Favorites only")
        app = App.__new__(App)
        app.notes, app.current, app.loading = [], None, False
        app.query, app.listbox, app.favorites_only = Mock(), Mock(), Mock()
        app.query.get.return_value = ""
        app.favorites_only.get.return_value = True
        app.refresh_list()
        self.assertEqual(app.visible, [])

'''
    tests = replace_once(tests,
        "    def test_schema1_backward_compatibility(self):\n",
        new_tests + "    def test_schema1_backward_compatibility(self):\n",
        "favorites filter regression tests")
    test_file.write_text(tests, encoding="utf-8")
    readme = candidate / "README.md"
    readme.write_text(readme.read_text(encoding="utf-8").rstrip() +
        "\n\nCommercial favorites filter: a bilingual sidebar checkbox narrows "
        "search results to starred notes without deleting or changing notes. "
        "Headless tests cover filtering, clearing and empty state. "
        "Windows GUI evidence for this exact revision is required.\n",
        encoding="utf-8")

    if factory.validate(ROOT) != {"stage": "improve", "slug": SLUG}:
        raise ValueError("Factory validation mismatch")
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    result = subprocess.run(
        (sys.executable, "-m", "unittest", "discover",
         "-s", str(candidate / "tests"), "-p", "test*.py", "-v"),
        cwd=ROOT, text=True, capture_output=True, env=env, timeout=180)
    print(result.stdout, result.stderr, flush=True)
    match = re.search(r"Ran (\d+) tests in", result.stderr)
    if result.returncode or not match or int(match.group(1)) < 43 or "\nOK" not in result.stderr:
        raise ValueError("Candidate tests failed; HOLD without promote")
    if factory.promote(ROOT) != {"stage": "improve", "slug": SLUG}:
        raise ValueError("Factory promote failed")
    expected = {**START, "cycle": 5}
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
            "commit", "-m", "feat(notes): promote bilingual favorites-only search filter")
    if remote_sha() != initial:
        raise ValueError("Remote changed before push: HOLD")
    run_cmd("git", "push", "origin", "HEAD:refs/heads/" + BRANCH)
    sha = run_cmd("git", "rev-parse", "HEAD", capture_output=True).stdout.strip()
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
        output.write("source_sha=" + sha + "\n")
        output.write("request_id=app-offline-notes-canary-" + sha[:12] + "\n")
    print({"factory_product_generated": True, "source_sha": sha,
           "candidate_tests": int(match.group(1)), "identity_cas_allowed": False})


if __name__ == "__main__":
    main()
