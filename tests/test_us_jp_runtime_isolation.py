"""Runtime US/JP data-boundary regression using real SQLite, without Tk or Store packaging.

A clean APPDATA sandbox must keep the US ledger in its US-specific directory,
and neither normal transactions nor review-only tax calculations may modify
a separate JP sentinel database. This does not replace Windows GUI smoke.
"""
import importlib.util
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
US = ROOT / "products" / "us-freelance-ledger"


def load_us_core():
    spec = importlib.util.spec_from_file_location("isolated_us_ledger_core", US / "core.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class USJPRuntimeIsolationTests(unittest.TestCase):
    def test_us_store_writes_only_us_appdata_and_preserves_jp_sentinel(self):
        core = load_us_core()
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            jp = base / "JPFreelanceLedger"
            jp.mkdir()
            jp_db = jp / "books.sqlite3"
            with sqlite3.connect(jp_db) as connection:
                connection.execute("CREATE TABLE sentinel (value TEXT NOT NULL)")
                connection.execute("INSERT INTO sentinel VALUES ('JP-KEEP')")
            before = jp_db.read_bytes()
            with patch.dict(os.environ, {"APPDATA": str(base)}):
                store = core.Store()
                try:
                    expected = base / "USFreelanceLedger" / "books.sqlite3"
                    self.assertEqual(store.path.resolve(), expected.resolve())
                    store.add("2026-11-13", "income", "125.00", "Business income")
                    self.assertEqual(len(store.rows()), 1)
                    self.assertEqual(store.rows()[0]["amount_cents"], 12500)
                finally:
                    store.conn.close()
            self.assertEqual(jp_db.read_bytes(), before, "US write changed JP database")
            self.assertEqual([p.name for p in base.iterdir()], ["JPFreelanceLedger", "USFreelanceLedger"])

    def test_us_default_path_cannot_fall_back_to_jp_directory(self):
        core = load_us_core()
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {"APPDATA": tmp}):
                path = core.default_db_path().resolve()
                self.assertEqual(path.parent.name, "USFreelanceLedger")
                self.assertEqual(path.name, "books.sqlite3")
                self.assertNotIn("jp", path.parent.name.lower())
                self.assertNotIn("japan", path.parent.name.lower())


if __name__ == "__main__":
    unittest.main()
