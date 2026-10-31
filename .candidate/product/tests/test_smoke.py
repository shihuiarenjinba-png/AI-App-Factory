import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from main import Ledger, format_minor, load_ledger, parse_amount, save_atomic

def test_jpy_amount_rounds_to_integer():
    assert parse_amount("1234.6", "JP") == 1235
    assert format_minor(1235, "JP") == "¥1,235"

def test_us_amount_uses_cents():
    assert parse_amount("12.345", "US") == 1235
    assert format_minor(1235, "US") == "$12.35"

def test_business_use_adjusts_expenses_only():
    ledger = Ledger()
    expense = ledger.add(
        date_text="2026-10-31", region="US", kind="expense",
        category="Office expense", amount_text="100", business_use_pct=60
    )
    income = ledger.add(
        date_text="2026-10-31", region="US", kind="income",
        category="Services", amount_text="100", business_use_pct=20
    )
    assert expense.adjusted_minor == 6000
    assert income.adjusted_minor == 10000
    assert ledger.summary("US")["net"] == 4000

def test_cross_region_category_is_rejected():
    ledger = Ledger()
    try:
        ledger.add(
            date_text="2026-10-31", region="JP", kind="expense",
            category="Office expense", amount_text="100"
        )
    except ValueError:
        return
    raise AssertionError("cross-region category accepted")

def test_invalid_percentage_is_rejected():
    ledger = Ledger()
    for pct in (-1, 101, "x"):
        try:
            ledger.add(
                date_text="2026-10-31", region="US", kind="expense",
                category="Supplies", amount_text="10", business_use_pct=pct
            )
        except ValueError:
            continue
        raise AssertionError("invalid percentage accepted")

def test_atomic_save_has_backup_recovery():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "ledger.json"
        ledger = Ledger()
        ledger.add(
            date_text="2026-10-31", region="JP", kind="income",
            category="Sales / 売上", amount_text="1000"
        )
        save_atomic(path, ledger)
        ledger.add(
            date_text="2026-10-31", region="JP", kind="income",
            category="Sales / 売上", amount_text="2000"
        )
        save_atomic(path, ledger)
        assert path.with_suffix(".json.bak").exists()
        path.write_text("{broken", encoding="utf-8")
        recovered = load_ledger(path)
        assert len(recovered.transactions) == 1
