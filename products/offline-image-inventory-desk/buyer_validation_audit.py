"""Offline audit of independent buyer sessions. Never upgrades market-fit.

Run inside the downloaded synthetic kit:
    python buyer_validation_audit.py --out .
Keep completed CSV and events.jsonl private; do not upload them to CI/GitHub.
Event timings and answers are observer-entered, not independently attested.
"""
import argparse
import csv
from datetime import datetime
import json
from pathlib import Path

from buyer_validation_evidence import FIELDS, PHASES, verify

PARTICIPANTS = frozenset("P%02d" % n for n in range(1, 6))
ACTIONS = frozenset(("start", "stop", "error"))
OBSERVED_YES_NO_FIELDS = ("first_30sec_goal_understood",
                          "recipient_can_identify_changes",
                          "recipient_can_explain_limits")


def audit(out):
    out = Path(out).resolve()
    verify(out)  # refuse to interpret evidence if fixture or EXE was altered
    with (out / "participant-responses.csv").open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if tuple(reader.fieldnames or ()) != FIELDS:
            raise ValueError("Participant CSV schema mismatch")
        responses = {}
        for row in reader:
            pid = row["participant_id"]
            if pid not in PARTICIPANTS or pid in responses:
                raise ValueError("Unknown or duplicate anonymous participant ID")
            responses[pid] = row

    phases = {}
    event_count = 0
    for number, line in enumerate((out / "events.jsonl").read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            raise ValueError("Blank event line %d" % number)
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError("Malformed event line %d" % number) from exc
        if not isinstance(event, dict) or event.get("participant") not in PARTICIPANTS or event.get("phase") not in PHASES or event.get("action") not in ACTIONS:
            raise ValueError("Invalid event identity or action at line %d" % number)
        try:
            stamp = datetime.fromisoformat(event["utc"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("Invalid event timestamp at line %d" % number) from exc
        if stamp.tzinfo is None or stamp.utcoffset() is None:
            raise ValueError("Timezone-free event timestamp")
        key = (event["participant"], event["phase"])
        state = phases.setdefault(key, {"start": None, "stop": None, "stop_at": None, "errors": 0})
        action = event["action"]
        if action == "start":
            if state["start"] is not None:
                raise ValueError("Duplicate phase start: %s/%s" % key)
            state["start"] = stamp
        elif action == "error":
            if state["start"] is None or state["stop"] is not None or stamp < state["start"]:
                raise ValueError("Error event outside active phase")
            state["errors"] += 1
        else:
            if state["start"] is None or state["stop"] is not None or stamp < state["start"]:
                raise ValueError("Stop event without active phase")
            clicks, errors, elapsed = event.get("clicks"), event.get("errors"), event.get("elapsed_sec")
            if (type(clicks) is not int or clicks < 0 or type(errors) is not int or errors < 0
                    or type(elapsed) not in (int, float) or not 0 <= elapsed < 86400):
                raise ValueError("Invalid observed metrics")
            actual = (stamp - state["start"]).total_seconds()
            if abs(actual - elapsed) > 1.0:
                raise ValueError("Event elapsed time disagrees with timestamps")
            state["stop"] = {"elapsed_sec": elapsed, "clicks": clicks, "errors": errors}
            state["stop_at"] = stamp
        event_count += 1

    sessions = {}
    for pid in sorted(PARTICIPANTS):
        recorded = {phase: phases.get((pid, phase), {}).get("stop") for phase in PHASES}
        if pid in responses or any((pid, phase) in phases for phase in PHASES):
            complete = all(value is not None for value in recorded.values())
            ordered = complete and all(
                phases[(pid, later)]["start"] >= phases[(pid, earlier)]["stop_at"]
                for earlier, later in zip(PHASES, PHASES[1:]))
            observed = (pid in responses
                        and all(responses[pid][field].strip().lower() in ("yes", "no")
                                for field in OBSERVED_YES_NO_FIELDS)
                        and bool(responses[pid]["recipient_feedback"].strip()))
            consent = pid in responses and responses[pid]["consent"].strip().lower() in ("yes", "true", "1")
            purchase = pid in responses and bool(responses[pid]["willingness_to_pay_JPY"].strip())
            sessions[pid] = {
                "phases": recorded,
                "all_phases_complete": complete,
                "phase_order_valid": ordered,
                "recipient_observations_recorded": observed,
                "manual_journey_complete": bool(ordered and observed and consent and purchase),
                "response_recorded": pid in responses,
                "consent_recorded": pid in responses and responses[pid]["consent"].strip().lower() in ("yes", "true", "1"),
                "purchase_answer_recorded": pid in responses and bool(responses[pid]["willingness_to_pay_JPY"].strip()),
            }
    return {
        "classification": "PRIVATE_MANUAL_BUYER_SESSION_AUDIT_NOT_PURCHASE_VERIFICATION",
        "status": "NOT_RUN" if not responses and not event_count else "HUMAN_REVIEW_REQUIRED",
        "source_sha": json.loads((out / "manifest.json").read_text(encoding="utf-8"))["source_sha"],
        "response_rows": len(responses),
        "event_count": event_count,
        "complete_observed_phase_sets": sum(s["all_phases_complete"] for s in sessions.values()),
        "complete_ordered_phase_sets": sum(s["phase_order_valid"] for s in sessions.values()),
        "complete_manual_journey_sets": sum(s["manual_journey_complete"] for s in sessions.values()),
        "sessions": sessions,
        "timing_source": "MANUALLY_LOGGED_NOT_INDEPENDENTLY_ATTESTED",
        "market_score": 64,
        "market_fit": "MARKET_FIT_HOLD",
        "why_pay_verified": False,
        "local_gui_pass": False,
        "independent_review_sha": None,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True, help="Downloaded buyer kit folder")
    args = parser.parse_args()
    print(json.dumps(audit(args.out), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
