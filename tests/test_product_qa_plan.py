import json
from pathlib import Path
import tempfile
import unittest

from tools.product_qa_plan import QAPlanError, load_plan, validate_plan


def good_plan():
    return {
        "schema_version":"windows-product-qa-plan-v1",
        "product":{"slug":"demo-product","kind":"app"},
        "intent":"Final pre-sale local Windows QA for the exact generated product.",
        "steps":[
            {
                "step_id":"artifact_hash","test_id":"ARTIFACT_HASH","required":True,
                "requires":[],"purpose":"Verify exact artifact bytes.",
                "parameters":{},"evidence":["artifact_sha256"],"on_fail":"STOP_AND_RETURN"
            },
            {
                "step_id":"process_start","test_id":"PROCESS_START","required":True,
                "requires":["artifact_hash"],"purpose":"Launch and observe the exact product.",
                "parameters":{"observation_seconds":5},"evidence":["exit_code","runtime_state"],
                "on_fail":"STOP_AND_RETURN"
            }
        ],
        "allowed_diagnostics":["EVENT_LOG_QUERY","PROCESS_STATUS","WINDOW_ENUMERATION"],
        "success_criteria":["All required steps pass and sanitized Evidence is returned."]
    }


class ProductQAPlanTests(unittest.TestCase):
    def test_valid_plan_and_digest(self):
        p=good_plan()
        validate_plan(p,slug="demo-product",kind="app")
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/"qa-plan.json"
            path.write_text(json.dumps(p),encoding="utf-8")
            loaded,digest=load_plan(path,slug="demo-product",kind="app")
            self.assertEqual(loaded,p)
            self.assertRegex(digest,r"^[0-9a-f]{64}$")

    def test_raw_command_text_is_rejected(self):
        p=good_plan()
        p["steps"][1]["purpose"]="run powershell -Command whoami"
        with self.assertRaises(QAPlanError):
            validate_plan(p,slug="demo-product",kind="app")

    def test_process_start_requires_hash(self):
        p=good_plan()
        p["steps"][1]["requires"]=[]
        with self.assertRaisesRegex(QAPlanError,"PROCESS_START"):
            validate_plan(p,slug="demo-product",kind="app")

    def test_forward_dependency_is_rejected(self):
        p=good_plan()
        p["steps"][0]["requires"]=["process_start"]
        with self.assertRaisesRegex(QAPlanError,"earlier"):
            validate_plan(p,slug="demo-product",kind="app")

    def test_unknown_parameter_key_is_rejected(self):
        p=good_plan()
        p["steps"][1]["parameters"]={"command":"calc.exe"}
        with self.assertRaisesRegex(QAPlanError,"parameter"):
            validate_plan(p,slug="demo-product",kind="app")

    def test_product_binding_is_exact(self):
        p=good_plan()
        with self.assertRaisesRegex(QAPlanError,"slug"):
            validate_plan(p,slug="other-product",kind="app")


if __name__=="__main__":
    unittest.main()
