"""Validate and bind model-authored Windows product QA plans.

The model describes *what* should be tested with closed action IDs and bounded
parameters.  It never supplies shell commands, executable paths, Git actions,
Store actions, or authority flags.  Runtime provenance is injected only by the
verified MSIX handoff.
"""
from __future__ import annotations

from copy import deepcopy
import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any

TEMPLATE_SCHEMA = "windows-product-qa-plan-template-v1"
BOUND_SCHEMA = "windows-product-qa-plan-v1"
SLUG = re.compile(r"^[a-z][a-z0-9-]{3,39}$")
STEP_ID = re.compile(r"^[a-z][a-z0-9-]{2,63}$")
SHA40 = re.compile(r"^[0-9a-f]{40}$")
SHA64 = re.compile(r"^[0-9a-f]{64}$")

ACTIONS = {
    "ARTIFACT_HASH",
    "PROCESS_START",
    "PROCESS_STATUS",
    "EVENT_LOG_QUERY",
    "UIA_FIND_WINDOW",
    "UIA_FIND_CONTROL",
    "UIA_INVOKE",
    "UIA_READ_TEXT",
}
DIAGNOSTICS = {
    "PROCESS_STATUS",
    "EVENT_LOG_QUERY",
    "UIA_FIND_WINDOW",
    "UIA_FIND_CONTROL",
    "UIA_READ_TEXT",
}
FORBIDDEN_ACTIONS = [
    "SOURCE_EDIT",
    "ARBITRARY_SHELL",
    "GIT_WRITE",
    "STORE_SUBMIT",
    "STORE_PUBLISH",
    "SECURITY_POLICY_CHANGE",
]
TOP_KEYS = {
    "schema_version", "product_slug", "product_type", "plan_version",
    "steps", "allowed_diagnostics", "forbidden_actions", "success_policy",
}
STEP_KEYS = {"step_id", "action", "requires", "required", "params"}
SUCCESS_KEYS = {
    "required_steps_must_pass", "evidence_return_required",
    "product_e2e_authority", "release_authority", "store_authority",
}
BOUND_KEYS = TOP_KEYS | {
    "template_sha256", "source_repository", "source_sha", "package_sha256",
    "executable_sha256", "identity",
}
IDENTITY_KEYS = {"name", "publisher", "version"}


class QAPlanError(ValueError):
    pass


def canonical(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")


def _fail(reason: str) -> None:
    raise QAPlanError("WINDOWS_QA_PLAN_HOLD: " + reason)


def _validate_params(action: str, params: Any) -> None:
    if not isinstance(params, dict):
        _fail("params must be an object")
    if action == "ARTIFACT_HASH":
        if params:
            _fail("ARTIFACT_HASH takes no parameters")
        return
    if action == "PROCESS_START":
        if set(params) - {"observation_seconds"}:
            _fail("PROCESS_START has unknown parameters")
        seconds = params.get("observation_seconds", 5)
        if type(seconds) is not int or not 1 <= seconds <= 60:
            _fail("invalid PROCESS_START observation_seconds")
        return
    if action == "PROCESS_STATUS":
        if params:
            _fail("PROCESS_STATUS takes no parameters")
        return
    if action == "EVENT_LOG_QUERY":
        if set(params) - {"lookback_seconds"}:
            _fail("EVENT_LOG_QUERY has unknown parameters")
        seconds = params.get("lookback_seconds", 300)
        if type(seconds) is not int or not 1 <= seconds <= 900:
            _fail("invalid EVENT_LOG_QUERY lookback_seconds")
        return
    if action == "UIA_FIND_WINDOW":
        if set(params) != {"title_contains"}:
            _fail("UIA_FIND_WINDOW requires title_contains only")
        title = params["title_contains"]
        if not isinstance(title, str) or not 1 <= len(title) <= 120:
            _fail("invalid UIA window title")
        return
    if action in {"UIA_FIND_CONTROL", "UIA_INVOKE", "UIA_READ_TEXT"}:
        if set(params) - {"name", "control_type"} or "name" not in params:
            _fail(action + " requires name and optional control_type")
        name = params["name"]
        if not isinstance(name, str) or not 1 <= len(name) <= 120:
            _fail("invalid UIA control name")
        control = params.get("control_type")
        if control is not None and control not in {
            "Button", "Edit", "Text", "CheckBox", "ComboBox", "ListItem", "TabItem"
        }:
            _fail("unsupported UIA control_type")
        return
    _fail("unsupported action")


def validate_template(value: Any, *, expected_slug: str | None = None,
                      expected_type: str | None = None) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != TOP_KEYS:
        _fail("template fields are invalid")
    if value.get("schema_version") != TEMPLATE_SCHEMA:
        _fail("template schema mismatch")
    slug = value.get("product_slug")
    if not isinstance(slug, str) or not SLUG.fullmatch(slug):
        _fail("invalid product slug")
    if expected_slug is not None and slug != expected_slug:
        _fail("product slug mismatch")
    product_type = value.get("product_type")
    if product_type not in {"APP", "GAME", "GAME_3D"}:
        _fail("invalid product type")
    if expected_type is not None and product_type != expected_type:
        _fail("product type mismatch")
    if value.get("plan_version") != 1:
        _fail("unsupported plan version")

    steps = value.get("steps")
    if not isinstance(steps, list) or not 2 <= len(steps) <= 32:
        _fail("plan must contain 2-32 steps")
    seen: set[str] = set()
    step_by_id: dict[str, dict[str, Any]] = {}
    actions: list[str] = []
    for step in steps:
        if not isinstance(step, dict) or set(step) != STEP_KEYS:
            _fail("step fields are invalid")
        step_id = step.get("step_id")
        action = step.get("action")
        requires = step.get("requires")
        if not isinstance(step_id, str) or not STEP_ID.fullmatch(step_id):
            _fail("invalid step_id")
        if step_id in seen:
            _fail("duplicate step_id")
        if action not in ACTIONS:
            _fail("unsupported action")
        if type(step.get("required")) is not bool:
            _fail("step required must be boolean")
        if (not isinstance(requires, list) or len(requires) != len(set(requires)) or
                any(not isinstance(item, str) or item not in seen for item in requires)):
            _fail("step dependencies must reference earlier unique steps")
        _validate_params(action, step.get("params"))
        seen.add(step_id)
        step_by_id[step_id] = step
        actions.append(action)

    if actions[0] != "ARTIFACT_HASH":
        _fail("first step must be ARTIFACT_HASH")
    hash_step = steps[0]["step_id"]
    for step in steps[1:]:
        if step["action"] != "ARTIFACT_HASH" and hash_step not in step["requires"]:
            _fail("every executable/diagnostic step must require ARTIFACT_HASH")
    process_ids = [
        step["step_id"] for step in steps if step["action"] == "PROCESS_START"
    ]
    if len(process_ids) != 1:
        _fail("exactly one PROCESS_START step is required")
    process_id = process_ids[0]
    if hash_step not in step_by_id[process_id]["requires"]:
        _fail("PROCESS_START must require ARTIFACT_HASH")
    for step in steps:
        if step["action"].startswith("UIA_") and process_id not in step["requires"]:
            _fail("UIA steps must require PROCESS_START")

    diagnostics = value.get("allowed_diagnostics")
    if (not isinstance(diagnostics, list) or
            len(diagnostics) != len(set(diagnostics)) or
            any(item not in DIAGNOSTICS for item in diagnostics)):
        _fail("invalid allowed diagnostics")
    if value.get("forbidden_actions") != FORBIDDEN_ACTIONS:
        _fail("forbidden action contract changed")
    success = value.get("success_policy")
    if not isinstance(success, dict) or set(success) != SUCCESS_KEYS:
        _fail("invalid success policy fields")
    if (success.get("required_steps_must_pass") is not True or
            success.get("evidence_return_required") is not True or
            success.get("product_e2e_authority") is not False or
            success.get("release_authority") is not False or
            success.get("store_authority") is not False):
        _fail("success policy may not grant release authority")
    return deepcopy(value)


def load_template(path: Path, *, expected_slug: str | None = None,
                  expected_type: str | None = None) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 128 * 1024:
        _fail("QA plan template is missing, linked, or oversized")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise QAPlanError("WINDOWS_QA_PLAN_HOLD: invalid JSON") from exc
    return validate_template(
        value, expected_slug=expected_slug, expected_type=expected_type,
    )


def bind_plan(template: dict[str, Any], *, source_repository: str,
              source_sha: str, package_sha256: str, executable_sha256: str,
              identity: dict[str, str]) -> dict[str, Any]:
    clean = validate_template(template)
    if not isinstance(source_repository, str) or not source_repository.startswith(
        "https://github.com/"
    ):
        _fail("invalid source repository")
    if not SHA40.fullmatch(source_sha):
        _fail("invalid source SHA")
    if not SHA64.fullmatch(package_sha256) or not SHA64.fullmatch(executable_sha256):
        _fail("invalid artifact SHA")
    if not isinstance(identity, dict) or set(identity) != IDENTITY_KEYS or any(
        not isinstance(identity[key], str) or not identity[key]
        for key in IDENTITY_KEYS
    ):
        _fail("invalid bound identity")
    bound = dict(clean)
    bound["schema_version"] = BOUND_SCHEMA
    bound["template_sha256"] = sha256(canonical(clean)).hexdigest()
    bound["source_repository"] = source_repository
    bound["source_sha"] = source_sha
    bound["package_sha256"] = package_sha256
    bound["executable_sha256"] = executable_sha256
    bound["identity"] = dict(identity)
    if set(bound) != BOUND_KEYS:
        _fail("bound plan fields are invalid")
    return bound


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--slug", required=True)
    parser.add_argument("--product-type", choices=("APP", "GAME", "GAME_3D"),
                        required=True)
    args = parser.parse_args(argv)
    try:
        value = load_template(
            args.plan, expected_slug=args.slug, expected_type=args.product_type,
        )
    except (QAPlanError, OSError, json.JSONDecodeError) as exc:
        print("HOLD:", str(exc))
        return 2
    print(json.dumps({
        "status": "QA_PLAN_TEMPLATE_VALID",
        "product_slug": value["product_slug"],
        "product_type": value["product_type"],
        "template_sha256": sha256(canonical(value)).hexdigest(),
        "step_count": len(value["steps"]),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
