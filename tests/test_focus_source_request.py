import hashlib
import unittest

from tools.focus_source_request import (
    EXPECTED_SOURCE_SHA,
    build_payload,
    canonical_bytes,
    assert_product_paths_unchanged,
    assert_source_head,
    idempotency_key,
    replay_decision,
    verify_payload_bytes,
)


class FocusSourceRequestTests(unittest.TestCase):
    def test_payload_is_deterministic_and_source_bound(self):
        first = build_payload()
        second = build_payload()
        self.assertEqual(first, second)
        raw = canonical_bytes(first)
        payload, digest = verify_payload_bytes(raw)
        self.assertEqual(payload["source_sha"], EXPECTED_SOURCE_SHA)
        self.assertEqual(payload["expected_head_sha"], EXPECTED_SOURCE_SHA)
        self.assertEqual(digest, hashlib.sha256(raw).hexdigest())
        self.assertEqual(idempotency_key(payload), payload["idempotency_key"])

    def test_partner_center_selection_and_safety_flags_are_explicit(self):
        payload = build_payload()
        self.assertEqual(payload["partner_center"]["selection_code"], "MSIX_OR_PWA_APP")
        self.assertEqual(payload["partner_center"]["selection_label"], "MSIX or PWA app")
        self.assertIs(payload["execution"]["dry_run"], True)
        self.assertIs(payload["execution"]["request_submitted"], False)
        self.assertIs(payload["execution"]["partner_center_write"], False)
        self.assertIs(payload["execution"]["identity_write"], False)
        self.assertIs(payload["execution"]["msix_build"], False)
        self.assertIs(payload["package_version"]["value"], None)
        self.assertEqual(payload["package_version"]["status"], "HOLD_NOT_INFERRED")

    def test_historical_identity_cannot_be_reused(self):
        payload = build_payload()
        self.assertEqual(payload["historical_identity"]["status"], "HISTORICAL_ONLY_NOT_REUSED")
        self.assertIs(payload["historical_identity"]["reuse_for_current_source"], False)
        self.assertNotIn("store_id", payload["historical_identity"])
        self.assertNotIn("name", payload["historical_identity"])
        self.assertNotIn("publisher", payload["historical_identity"])
        self.assertNotIn("version", payload["historical_identity"])

    def test_source_drift_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "source branch drift"):
            assert_source_head(EXPECTED_SOURCE_SHA, "0" * 40)

    def test_product_tree_drift_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "product source changed"):
            assert_product_paths_unchanged([
                "handoff/focus-session-desk/source-request/request.json",
                "products/focus-session-desk/main.py",
            ])
        assert_product_paths_unchanged(["handoff/focus-session-desk/source-request/request.json"])

    def test_request_tampering_is_rejected(self):
        payload = build_payload()
        payload["partner_center"]["selection_code"] = "PWA_ONLY"
        tampered = canonical_bytes(payload)
        with self.assertRaisesRegex(ValueError, "pinned contract"):
            verify_payload_bytes(tampered)

    def test_request_byte_tampering_and_hash_mismatch_are_rejected(self):
        raw = canonical_bytes(build_payload())
        with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
            verify_payload_bytes(raw, "0" * 64)
        with self.assertRaisesRegex(ValueError, "not canonical"):
            verify_payload_bytes(raw + b" ")

    def test_same_request_replay_is_noop(self):
        payload = build_payload()
        digest = hashlib.sha256(canonical_bytes(payload)).hexdigest()
        existing = {}
        self.assertEqual(replay_decision(existing, payload, digest), "NEW_DRY_RUN")
        existing[payload["idempotency_key"]] = digest
        self.assertEqual(replay_decision(existing, payload, digest), "IDEMPOTENT_REPLAY_NOOP")

    def test_same_idempotency_key_with_different_payload_is_rejected(self):
        payload = build_payload()
        with self.assertRaisesRegex(ValueError, "different request bytes"):
            replay_decision({payload["idempotency_key"]: "f" * 64}, payload, "a" * 64)


if __name__ == "__main__":
    unittest.main()
