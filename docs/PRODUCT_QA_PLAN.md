# Final Windows product QA plan contract

Every built or improved product must contain `qa-plan.json`. This is a declarative
pre-sale QA contract for Windows-all-auto. It is data, not a script.

The GitHub coding model should create or update this file from the actual product UI,
features, persistence behavior, and package expectations. Do not put shell, PowerShell,
Python, Git, Store, or other executable commands into the plan.

## Required baseline

Every plan starts with these required steps:

1. `ARTIFACT_HASH`
2. `PROCESS_START`, depending on the hash step

Both baseline steps use `"parameters": {}` until the local trusted executor explicitly
supports parameter binding.

## Reviewed action vocabulary

Baseline/runtime:

- `ARTIFACT_HASH`
- `PROCESS_START`
- `WINDOW_RESPONSIVE`
- `NORMAL_EXIT`

UI automation:

- `UIA_FIND_CONTROL`
- `UIA_INVOKE`
- `UIA_READ_TEXT`
- `UIA_ASSERT_TEXT`

State/persistence:

- `SAVE_RELOAD`
- `FILE_OUTPUT_EXISTS`

Package checks:

- `PACKAGE_IDENTITY_READ`
- `PACKAGE_VERSION_READ`

Diagnostics:

- `EVENT_LOG_QUERY`
- `PROCESS_STATUS`
- `WINDOW_ENUMERATION`

A required action that Windows-all-auto does not yet implement must produce a
`QA_PLAN_CAPABILITY_HOLD`; it must never be silently skipped or replaced.

## Parameter vocabulary

Only these declarative parameter names are permitted:

- `target_name`
- `expected_text`
- `expected_state`
- `file_role`
- `observation_seconds`
- `locale` (`ja-JP` or `en-US`)
- `dpi_percent` (100/125/150/175/200)

Parameters are not executable text.

## Example

```json
{
  "schema_version": "windows-product-qa-plan-v1",
  "product": {
    "slug": "example-product",
    "kind": "app"
  },
  "intent": "Final pre-sale Windows QA for the exact generated product.",
  "steps": [
    {
      "step_id": "artifact_hash",
      "test_id": "ARTIFACT_HASH",
      "required": true,
      "requires": [],
      "purpose": "Verify the exact immutable executable bytes.",
      "parameters": {},
      "evidence": ["artifact_sha256"],
      "on_fail": "STOP_AND_RETURN"
    },
    {
      "step_id": "process_start",
      "test_id": "PROCESS_START",
      "required": true,
      "requires": ["artifact_hash"],
      "purpose": "Launch the exact product through the trusted local runner.",
      "parameters": {},
      "evidence": ["exit_code", "runtime_state"],
      "on_fail": "STOP_AND_RETURN"
    },
    {
      "step_id": "settings_visible",
      "test_id": "UIA_FIND_CONTROL",
      "required": true,
      "requires": ["process_start"],
      "purpose": "Verify the Settings control exists in the initial UI.",
      "parameters": {
        "target_name": "Settings",
        "locale": "en-US"
      },
      "evidence": ["uia_control"],
      "on_fail": "CONTINUE_DIAGNOSTICS"
    }
  ],
  "allowed_diagnostics": [
    "EVENT_LOG_QUERY",
    "PROCESS_STATUS",
    "WINDOW_ENUMERATION"
  ],
  "success_criteria": [
    "All required steps pass for the exact source and artifact hashes.",
    "Sanitized Evidence and GitHub ACK readback are verified."
  ]
}
```

## Authority

This plan never grants release or Store authority. Windows-all-auto keeps these gates
false until separate product-specific evidence and user approvals exist:

- `product_e2e_pass`
- `release_ready`
- `store_submission_allowed`
- user product approval
- user price approval

A source repair requires a new immutable source SHA and a fresh QA job.
