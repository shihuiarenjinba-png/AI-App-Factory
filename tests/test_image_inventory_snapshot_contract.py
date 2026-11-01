"""Run image-delivery product regressions in Factory root CI on Linux and Windows."""
import importlib.util
from pathlib import Path
path=Path(__file__).resolve().parents[1]/"products"/"offline-image-inventory-desk"/"tests"/"test_snapshot.py"
spec=importlib.util.spec_from_file_location("image_snapshot_product_tests",path)
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
SnapshotTests=module.SnapshotTests

def test_snapshot_review_workflow_checks_out_exact_head():
    """Prevent a PR merge SHA being mislabeled as source SHA."""
    workflow=(Path(__file__).resolve().parents[1]/".github"/"workflows"/"image-snapshot-review.yml").read_text(encoding="utf-8")
    assert workflow.count("ref: ${{ github.event.pull_request.head.sha || github.sha }}")==2
    assert "SOURCE_SHA: ${{ github.event.pull_request.head.sha || github.sha }}" in workflow
    assert "git rev-parse HEAD" in workflow
    assert "source_sha=$env:SOURCE_SHA" in workflow
    assert "source_sha=$env:GITHUB_SHA" not in workflow
