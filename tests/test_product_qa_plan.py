import unittest

from tools.product_qa_plan import (
    QAPlanError, bind_plan, canonical, validate_template,
)
from hashlib import sha256


def plan():
    return {
        "schema_version": "windows-product-qa-plan-template-v1",
        "product_slug": "demo-product",
        "product_type": "APP",
        "plan_version": 1,
        "steps": [
            {
                "step_id": "artifact-hash",
                "action": "ARTIFACT_HASH",
                "requires": [],
                "required": True,
                "params": {},
            },
            {
                "step_id": "process-start",
                "action": "PROCESS_START",
                "requires": ["artifact-hash"],
                "required": True,
                "params": {"observation_seconds": 5},
            },
            {
                "step_id": "main-window",
                "action": "UIA_FIND_WINDOW",
                "requires": ["artifact-hash", "process-start"],
                "required": True,
                "params": {"title_contains": "Demo"},
            },
        ],
        "allowed_diagnostics": [
            "PROCESS_STATUS",
            "EVENT_LOG_QUERY",
            "UIA_FIND_WINDOW",
        ],
        "forbidden_actions": [
            "SOURCE_EDIT",
            "ARBITRARY_SHELL",
            "GIT_WRITE",
            "STORE_SUBMIT",
            "STORE_PUBLISH",
            "SECURITY_POLICY_CHANGE",
        ],
        "success_policy": {
            "required_steps_must_pass": True,
            "evidence_return_required": True,
            "product_e2e_authority": False,
            "release_authority": False,
            "store_authority": False,
        },
    }


class ProductQAPlanTests(unittest.TestCase):
    def test_valid_template_and_binding(self):
        value = validate_template(plan(), expected_slug="demo-product",
                                  expected_type="APP")
        bound = bind_plan(
            value,
            source_repository="https://github.com/shihuiarenjinba-png/AI-App-Factory",
            source_sha="a" * 40,
            package_sha256="b" * 64,
            executable_sha256="c" * 64,
            identity={
                "name": "OkinawaDesktopTools.Demo",
                "publisher": "CN=TEST",
                "version": "1.0.0.0",
            },
        )
        self.assertEqual(bound["schema_version"], "windows-product-qa-plan-v1")
        self.assertEqual(
            bound["template_sha256"],
            sha256(canonical(value)).hexdigest(),
        )
        self.assertFalse(bound["success_policy"]["store_authority"])

    def test_raw_command_or_unknown_field_is_rejected(self):
        value = plan()
        value["steps"][1]["command"] = "powershell.exe -Command whoami"
        with self.assertRaisesRegex(QAPlanError, "step fields"):
            validate_template(value)

    def test_unknown_action_is_rejected(self):
        value = plan()
        value["steps"][1]["action"] = "RUN_ARBITRARY_COMMAND"
        with self.assertRaisesRegex(QAPlanError, "unsupported action"):
            validate_template(value)

    def test_dependency_must_reference_earlier_step(self):
        value = plan()
        value["steps"][1]["requires"] = ["main-window"]
        with self.assertRaisesRegex(QAPlanError, "earlier"):
            validate_template(value)

    def test_process_start_requires_hash(self):
        value = plan()
        value["steps"][1]["requires"] = []
        with self.assertRaisesRegex(QAPlanError, "ARTIFACT_HASH"):
            validate_template(value)

    def test_uia_requires_process_start(self):
        value = plan()
        value["steps"][2]["requires"] = ["artifact-hash"]
        with self.assertRaisesRegex(QAPlanError, "PROCESS_START"):
            validate_template(value)

    def test_forbidden_authority_contract_is_fixed(self):
        value = plan()
        value["forbidden_actions"].remove("STORE_PUBLISH")
        with self.assertRaisesRegex(QAPlanError, "forbidden action"):
            validate_template(value)
        value = plan()
        value["success_policy"]["store_authority"] = True
        with self.assertRaisesRegex(QAPlanError, "authority"):
            validate_template(value)

    def test_unbounded_parameters_are_rejected(self):
        value = plan()
        value["steps"][1]["params"]["observation_seconds"] = 3600
        with self.assertRaisesRegex(QAPlanError, "observation"):
            validate_template(value)

    def test_binding_requires_real_hash_shapes(self):
        with self.assertRaisesRegex(QAPlanError, "source SHA"):
            bind_plan(
                plan(),
                source_repository="https://github.com/shihuiarenjinba-png/AI-App-Factory",
                source_sha="not-a-sha",
                package_sha256="b" * 64,
                executable_sha256="c" * 64,
                identity={
                    "name": "N",
                    "publisher": "P",
                    "version": "1.0.0.0",
                },
            )


if __name__ == "__main__":
    unittest.main()
