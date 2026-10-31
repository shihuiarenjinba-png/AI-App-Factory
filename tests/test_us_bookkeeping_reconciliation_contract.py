"""Load US statement reconciliation fixtures without requiring a package __init__.py."""
import importlib.util
import unittest
from pathlib import Path

def load_tests(loader, tests, pattern):
    path=(Path(__file__).resolve().parents[1]/"products"/"us-bookkeeping-desk"/"tests"/"test_reconciliation.py")
    if not path.is_file():
        raise AssertionError("US bookkeeping reconciliation tests missing")
    spec=importlib.util.spec_from_file_location("us_bookkeeping_reconciliation_fixtures",path)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    suite=loader.loadTestsFromModule(module)
    if suite.countTestCases()==0:
        raise AssertionError("No reconciliation tests discovered")
    return suite
