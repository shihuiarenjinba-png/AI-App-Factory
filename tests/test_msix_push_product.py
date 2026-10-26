"""Regression: a multi-commit push must be inspected as one range."""
from pathlib import Path
import subprocess
import tempfile
import unittest

from tools.msix_push_product import SelectionHold, choose_slug, push_paths, slug_from_paths


class PushSelectionTests(unittest.TestCase):
    def test_one_product_across_multiple_commits(self):
        self.assertEqual(slug_from_paths([
            "products/demo-app/main.py", "products/demo-app/store/approved-identity.json",
        ]), "demo-app")

    def test_multiple_products_across_commits_holds(self):
        with self.assertRaisesRegex(SelectionHold, "exactly one"):
            slug_from_paths(["products/demo-app/main.py", "products/other-app/main.py"])

    def test_non_product_only_push_holds(self):
        with self.assertRaises(SelectionHold):
            slug_from_paths(["docs/readme.md"])

    def test_malformed_product_path_holds(self):
        for path in ("products/BadName/main.py", "products/../manifest.json", "products/demo-app"):
            with self.subTest(path=path), self.assertRaises(SelectionHold):
                slug_from_paths([path])

    def test_zero_before_does_not_guess_head_commit(self):
        with self.assertRaisesRegex(SelectionHold, "manual dispatch"):
            push_paths("0" * 40, "a" * 40)

    def test_manual_dispatch_requires_safe_slug(self):
        self.assertEqual(choose_slug("workflow_dispatch", "demo-app", "", ""), "demo-app")
        with self.assertRaises(SelectionHold):
            choose_slug("workflow_dispatch", "../other", "", "")

    def test_unknown_event_holds(self):
        with self.assertRaises(SelectionHold):
            choose_slug("pull_request", "demo-app", "", "")

    def test_cross_product_rename_reports_both_products_and_holds(self):
        # Git's default rename detection reports only the destination in
        # --name-only output.  That must not hide the source product.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            def git(*args):
                return subprocess.run(["git", *args], cwd=root, check=True,
                                      stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout.decode().strip()
            git("init", "-q")
            git("config", "user.email", "ci@example.invalid")
            git("config", "user.name", "CI")
            git("config", "diff.renames", "true")
            (root / "products" / "first-app").mkdir(parents=True)
            (root / "products" / "first-app" / "main.py").write_text("print(1)\\n")
            git("add", ".")
            git("commit", "-qm", "initial product")
            before = git("rev-parse", "HEAD")
            (root / "products" / "other-app").mkdir(parents=True)
            git("mv", "products/first-app/main.py", "products/other-app/main.py")
            git("commit", "-qm", "move file across products")
            after = git("rev-parse", "HEAD")
            self.assertEqual(sorted(push_paths(before, after, cwd=root)), [
                "products/first-app/main.py", "products/other-app/main.py",
            ])
            with self.assertRaisesRegex(SelectionHold, "exactly one"):
                choose_slug("push", "", before, after, cwd=root)

    def test_real_multi_commit_git_range(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            def git(*args):
                return subprocess.run(["git", *args], cwd=root, check=True,
                                      stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout.decode().strip()
            git("init", "-q")
            git("config", "user.email", "ci@example.invalid")
            git("config", "user.name", "CI")
            (root / "README.md").write_text("initial\n")
            git("add", ".")
            git("commit", "-qm", "initial")
            before = git("rev-parse", "HEAD")
            (root / "products" / "demo-app").mkdir(parents=True)
            (root / "products" / "demo-app" / "main.py").write_text("print(1)\n")
            git("add", ".")
            git("commit", "-qm", "first product change")
            (root / "docs.md").write_text("docs\n")
            git("add", ".")
            git("commit", "-qm", "non-product HEAD")
            after = git("rev-parse", "HEAD")
            self.assertEqual(choose_slug("push", "", before, after, cwd=root), "demo-app")
            (root / "products" / "other-app").mkdir(parents=True)
            (root / "products" / "other-app" / "main.py").write_text("print(2)\n")
            git("add", ".")
            git("commit", "-qm", "second product")
            after = git("rev-parse", "HEAD")
            with self.assertRaisesRegex(SelectionHold, "exactly one"):
                choose_slug("push", "", before, after, cwd=root)


if __name__ == "__main__":
    unittest.main()
