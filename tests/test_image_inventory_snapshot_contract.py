"""Run image-delivery product regressions in Factory root CI on Linux and Windows."""
import importlib.util
from pathlib import Path
path=Path(__file__).resolve().parents[1]/"products"/"offline-image-inventory-desk"/"tests"/"test_snapshot.py"
spec=importlib.util.spec_from_file_location("image_snapshot_product_tests",path)
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
SnapshotTests=module.SnapshotTests
