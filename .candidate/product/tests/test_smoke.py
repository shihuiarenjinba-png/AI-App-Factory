import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from main import Book, Line, load_book, save_atomic

class DoubleEntryTests(unittest.TestCase):
    def test_simple_entry_is_balanced(self):
        book = Book()
        entry = book.add_simple_entry(
            "2026-10-31", "Owner contribution", "OPEN", "1000", "3000", "1000"
        )
        self.assertEqual(sum(line.debit for line in entry.lines), 100000)
        self.assertEqual(sum(line.credit for line in entry.lines), 100000)

    def test_unbalanced_split_is_rejected(self):
        book = Book()
        with self.assertRaises(ValueError):
            book.add_entry(
                "2026-10-31", "bad", "",
                [Line("1000", debit=100), Line("3000", credit=99)]
            )

    def test_profit_loss(self):
        book = Book()
        book.add_simple_entry("2026-10-31", "sale", "", "1000", "4000", "500")
        book.add_simple_entry("2026-10-31", "rent", "", "5000", "1000", "100")
        self.assertEqual(
            book.profit_loss(),
            {"income": 50000, "expenses": 10000, "profit": 40000}
        )

    def test_balance_sheet_includes_current_earnings(self):
        book = Book()
        book.add_simple_entry("2026-10-31", "capital", "", "1000", "3000", "1000")
        book.add_simple_entry("2026-10-31", "sale", "", "1000", "4000", "500")
        book.add_simple_entry("2026-10-31", "rent", "", "5000", "1000", "100")
        self.assertEqual(book.balance_sheet()["difference"], 0)

    def test_duplicate_account_is_rejected(self):
        book = Book()
        with self.assertRaises(ValueError):
            book.add_account("1000", "Duplicate", "asset")

    def test_atomic_save_has_backup_recovery(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "book.json"
            book = Book()
            book.add_simple_entry("2026-10-31", "capital", "", "1000", "3000", "100")
            save_atomic(path, book)
            book.add_simple_entry("2026-10-31", "sale", "", "1000", "4000", "50")
            save_atomic(path, book)
            path.write_text("{broken", encoding="utf-8")
            recovered = load_book(path)
            self.assertEqual(len(recovered.entries), 1)

if __name__ == "__main__":
    unittest.main()
