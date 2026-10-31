"""Run product-specific US bookkeeping roll-forward fixtures in Factory core CI."""
import unittest
from pathlib import Path

def load_tests(loader, tests, pattern):
    product_tests = Path(__file__).resolve().parents[1] / "products" / "us-bookkeeping-desk" / "tests"
    if not product_tests.is_dir():
        raise AssertionError("US bookkeeping product tests missing")
    return loader.discover(str(product_tests), pattern="test_rollforward.py", top_level_dir=str(product_tests))
