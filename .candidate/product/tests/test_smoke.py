import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from main import Book, Line, load_book, save_atomic

def test_simple_entry_is_balanced():
    book = Book()
    entry = book.add_simple_entry(
        "2026-10-31", "Owner contribution", "OPEN", "1000", "3000", "1000"
    )
    assert sum(line.debit for line in entry.lines) == 100000
    assert sum(line.credit for line in entry.lines) == 100000

def test_unbalanced_split_is_rejected():
    book = Book()
    try:
        book.add_entry(
            "2026-10-31", "bad", "",
            [Line("1000", debit=100), Line("3000", credit=99)]
        )
    except ValueError:
        return
    raise AssertionError("unbalanced entry accepted")

def test_profit_loss():
    book = Book()
    book.add_simple_entry("2026-10-31", "sale", "", "1000", "4000", "500")
    book.add_simple_entry("2026-10-31", "rent", "", "5000", "1000", "100")
    assert book.profit_loss() == {
        "income": 50000, "expenses": 10000, "profit": 40000
    }

def test_balance_sheet_includes_current_earnings():
    book = Book()
    book.add_simple_entry("2026-10-31", "capital", "", "1000", "3000", "1000")
    book.add_simple_entry("2026-10-31", "sale", "", "1000", "4000", "500")
    book.add_simple_entry("2026-10-31", "rent", "", "5000", "1000", "100")
    assert book.balance_sheet()["difference"] == 0

def test_duplicate_account_is_rejected():
    book = Book()
    try:
        book.add_account("1000", "Duplicate", "asset")
    except ValueError:
        return
    raise AssertionError("duplicate account accepted")

def test_atomic_save_has_backup_recovery():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "book.json"
        book = Book()
        book.add_simple_entry("2026-10-31", "capital", "", "1000", "3000", "100")
        save_atomic(path, book)
        book.add_simple_entry("2026-10-31", "sale", "", "1000", "4000", "50")
        save_atomic(path, book)
        path.write_text("{broken", encoding="utf-8")
        recovered = load_book(path)
        assert len(recovered.entries) == 1
