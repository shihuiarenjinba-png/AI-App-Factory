"""Validate the declarative final Windows QA plan generated with each product."""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any

SCHEMA_VERSION = "windows-product-qa-plan-v1"
SLUG = re.compile(r"^[a-z][a-z0-9-]{3,39}$")
STEP_ID = re.compile(r"^[a-z][a-z0-9_]{2,63}$")
TEST_ID = re.compile(r"^[A-Z][A-Z0-9_]{2,63}$")
KNOWN_TEST_IDS = {
    "ARTIFACT_HASH", "PROCESS_START", "WINDOW_RESPONSIVE",
    "UIA_FIND_CONTROL", "UIA_INVOKE", "UIA_READ_TEXT", "UIA_ASSERT_TEXT",
    "NORMAL_EXIT", "SAVE_RELOAD", "PACKAGE_IDENTITY_READ",
    "PACKAGE_VERSION_READ", "FILE_OUTPUT_EXISTS",
    "EVENT_LOG_QUERY", "PROCESS_STATUS", "WINDOW_ENUMERATION",
}
DIAGNOSTIC_TEST_IDS = {"EVENT_LOG_QUERY", "PROCESS_STATUS", "WINDOW_ENUMERATION"}
TOP_KEYS = {
    "schema_version", "product", "intent", "steps",
    "allowed_diagnostics", "success_criteria",
}
PRODUCT_KEYS = {"slug", "kind"}
STEP_KEYS = {
    "step_id", "test_id", "required", "requires", "purpose",
    "parameters", "evidence", "on_fail",
}
PARAM_KEYS = {
    "target_name", "expected_text", "expected_state", "file_role",
    "observation_seconds", "locale", "dpi_percent",
}
FORBIDDEN_TEXT = re.compile(
    r"(?i)(powershell|pwsh|cmd\\.exe|\\bgit\\s+(?:add|commit|push|merge|reset)|"
    r"\\b(?:curl|wget)\\s|(?:^|\\s)(?:python|py)\\.exe\\s|[;&|])"
)


class QAPlanError(ValueError):
    pass


def _fail(reason: str) -> None:
    raise QAPlanError("PRODUCT_QA_PLAN_HOLD: " + reason)


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")


def _safe_text(value: Any, field: str, *, maximum: int = 800) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        _fail(field + " must be a bounded non-empty string")
    if FORBIDDEN_TEXT.search(value):
        _fail(field + " contains command-like text")
    return value


def _parameters(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) - PARAM_KEYS:
        _fail("unsupported parameter key")
    clean: dict[str, Any] = {}
    for key, item in value.items():
        if key in {"observation_seconds", "dpi_percent"}:
            if type(item) is not int:
                _fail("numeric QA parameter must be integer")
            if key == "observation_seconds" and not 0 <= item <= 120:
                _fail("observation_seconds out of range")
            if key == "dpi_percent" and item not in {100, 125, 150, 175, 200}:
                _fail("unsupported dpi_percent")
            clean[key] = item
            continue
        if not isinstance(item, str) or not item.strip() or len(item) > 200:
            _fail("string QA parameter is invalid")
        if FORBIDDEN_TEXT.search(item):
            _fail("QA parameter contains command-like text")
        if key == "locale" and item not in {"ja-JP", "en-US"}:
            _fail("unsupported locale")
        clean[key] = item
    return clean


def validate_plan(value: Any, *, slug: str, kind: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != TOP_KEYS:
        _fail("top-level fields are invalid")
    if value.get("schema_version") != SCHEMA_VERSION:
        _fail("schema version mismatch")
    product = value.get("product")
    if not isinstance(product, dict) or set(product) != PRODUCT_KEYS:
        _fail("product binding is invalid")
    if product.get("slug") != slug or not SLUG.fullmatch(slug):
        _fail("product slug mismatch")
    if product.get("kind") != kind or kind not in {"app", "game"}:
        _fail("product kind mismatch")
    _safe_text(value.get("intent"), "intent", maximum=1000)

    steps = value.get("steps")
    if not isinstance(steps, list) or not 2 <= len(steps) <= 24:
        _fail("QA plan must contain 2-24 steps")
    seen: set[str] = set()
    normalized_steps: list[dict[str, Any]] = []
    for raw in steps:
        if not isinstance(raw, dict) or set(raw) != STEP_KEYS:
            _fail("QA step fields are invalid")
        step_id = raw.get("step_id")
        test_id = raw.get("test_id")
        if not isinstance(step_id, str) or not STEP_ID.fullmatch(step_id):
            _fail("invalid step_id")
        if step_id in seen:
            _fail("duplicate step_id")
        if (not isinstance(test_id, str) or not TEST_ID.fullmatch(test_id) or
                test_id not in KNOWN_TEST_IDS):
            _fail("invalid or unsupported test_id")
        if type(raw.get("required")) is not bool:
            _fail("required must be boolean")
        requires = raw.get("requires")
        if (not isinstance(requires, list) or
                any(not isinstance(x, str) or not STEP_ID.fullmatch(x) for x in requires) or
                len(requires) != len(set(requires))):
            _fail("invalid step dependencies")
        missing = [x for x in requires if x not in seen]
        if missing:
            _fail("step dependency must reference an earlier step")
        purpose = _safe_text(raw.get("purpose"), "purpose")
        evidence = raw.get("evidence")
        if (not isinstance(evidence, list) or not evidence or
                len(evidence) > 12 or
                any(not isinstance(x, str) or not x.strip() or len(x) > 80
                    or FORBIDDEN_TEXT.search(x) for x in evidence)):
            _fail("invalid evidence declaration")
        on_fail = raw.get("on_fail")
        if on_fail not in {"STOP_AND_RETURN", "CONTINUE_DIAGNOSTICS"}:
            _fail("invalid on_fail policy")
        parameters = _parameters(raw.get("parameters"))
        if test_id in {"ARTIFACT_HASH", "PROCESS_START"} and parameters:
            _fail("baseline ARTIFACT_HASH/PROCESS_START parameters must be empty")
        normalized_steps.append({
            "step_id": step_id,
            "test_id": test_id,
            "required": raw["required"],
            "requires": list(requires),
            "purpose": purpose,
            "parameters": parameters,
            "evidence": list(evidence),
            "on_fail": on_fail,
        })
        seen.add(step_id)

    if normalized_steps[0]["test_id"] != "ARTIFACT_HASH":
        _fail("first QA step must be ARTIFACT_HASH")
    hash_steps = [s for s in normalized_steps if s["test_id"] == "ARTIFACT_HASH"]
    if len(hash_steps) != 1 or hash_steps[0]["required"] is not True:
        _fail("ARTIFACT_HASH must be one required step")
    starts = [s for s in normalized_steps if s["test_id"] == "PROCESS_START"]
    if len(starts) != 1 or starts[0]["required"] is not True:
        _fail("PROCESS_START must be one required step")
    if hash_steps[0]["step_id"] not in starts[0]["requires"]:
        _fail("PROCESS_START must depend on ARTIFACT_HASH")

    diagnostics = value.get("allowed_diagnostics")
    if (not isinstance(diagnostics, list) or len(diagnostics) > 16 or
            len(diagnostics) != len(set(diagnostics)) or
            any(not isinstance(x, str) or not TEST_ID.fullmatch(x)
                or x not in DIAGNOSTIC_TEST_IDS for x in diagnostics)):
        _fail("invalid allowed_diagnostics")
    criteria = value.get("success_criteria")
    if (not isinstance(criteria, list) or not 1 <= len(criteria) <= 12 or
            any(not isinstance(x, str) or not x.strip() or len(x) > 240
                or FORBIDDEN_TEXT.search(x) for x in criteria)):
        _fail("invalid success_criteria")
    return value


def load_plan(path: Path, *, slug: str, kind: str) -> tuple[dict[str, Any], str]:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 128 * 1024:
        _fail("qa-plan.json missing, linked or oversized")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise QAPlanError("PRODUCT_QA_PLAN_HOLD: invalid JSON") from exc
    validate_plan(value, slug=slug, kind=kind)
    return value, sha256(_canonical(value)).hexdigest()
