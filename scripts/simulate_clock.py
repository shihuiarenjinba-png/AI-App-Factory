#!/usr/bin/env python3
"""Deterministic 24h schedule simulation. No external services or credentials."""
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WF = ROOT / ".github/workflows/factory-cycle.yml"

def inspect_schedule(source: str):
    match = re.search(r'^\s+- cron:\s*"([^"]+)"\s*$', source, re.M)
    if match is None:
        raise ValueError("missing scheduled cron expression")
    parts = match.group(1).split()
    if len(parts) != 5 or parts[1:] != ["*", "*", "*", "*"]:
        raise ValueError("unexpected schedule pattern")
    minutes = [int(m) for m in parts[0].split(",")]
    if len(minutes) != 4 or len(set(minutes)) != 4 or any(m < 0 or m >= 60 for m in minutes):
        raise ValueError("cron should have exactly four unique minute positions")
    minutes.sort()
    ticks = [
        datetime(2026, 10, 26, hour, minute, tzinfo=timezone.utc)
        for hour in range(24) for minute in minutes
    ]
    if len(ticks) != 96:
        raise ValueError("expected 96 scheduled ticks")
    for a, b in zip(ticks, ticks[1:]):
        if b-a != timedelta(minutes=15):
            raise ValueError("invalid 15 minute spacing")
    if (ticks[0] + timedelta(days=1)) - ticks[-1] != timedelta(minutes=15):
        raise ValueError("wrong midnight spacing")
    return {"kind": json.loads((ROOT/"factory/config.json").read_text())["kind"],
            "cron": match.group(1), "simulated_minutes": minutes,
            "simulated_timestamps_per_24h": 96,
            "actual_github_schedule_executed": False}

if __name__ == "__main__":
    try:
        print(json.dumps(inspect_schedule(WF.read_text()),indent=2))
    except ValueError as e:
        print("HOLD:",str(e),file=sys.stderr)
        sys.exit(2)
