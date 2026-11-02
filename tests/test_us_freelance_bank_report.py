"""Include product-local bank receipt fixtures in Factory Windows/Ubuntu discovery."""
import importlib.util
import sys
from pathlib import Path

PRODUCT = Path(__file__).resolve().parents[1] / "products" / "us-freelance-ledger"
sys.path.insert(0, str(PRODUCT))
SPEC = importlib.util.spec_from_file_location(
    "us_freelance_bank_receipt_cases", PRODUCT / "tests" / "test_bank_report.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
BankReceiptTests = MODULE.BankReceiptTests
