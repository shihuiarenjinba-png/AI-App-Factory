#!/usr/bin/env python3
"""Validate a deterministic 15-minute slot model; never assert a live task ran."""
from datetime import datetime,timedelta,timezone
from pathlib import Path
import json
import re
import sys

ROOT=Path(__file__).resolve().parents[1]
WORKFLOW=ROOT/".github/workflows/factory-autoloop.yml"

def inspect_schedule(source:str)->dict:
    if not isinstance(source,str) or "workflow_dispatch:" not in source:
        raise ValueError("Missing explicit GitHub verification entry point")
    if re.search(r"(?m)^\s+schedule:\s*$",source):
        raise ValueError("Do not schedule AI/model actions from GitHub Actions")
    if "openai/codex-action" in source or "OPENAI_API_KEY" in source:
        raise ValueError("Paid AI API workflow is prohibited by the agreed design")
    minutes=[0,15,30,45]
    ticks=[datetime(2026,10,26,h,m,tzinfo=timezone.utc)
           for h in range(24) for m in minutes]
    if len(ticks)!=96 or any(b-a!=timedelta(minutes=15) for a,b in zip(ticks,ticks[1:])):
        raise ValueError("Invalid local 15-minute model")
    return {
       "kind":json.loads((ROOT/"factory/config.json").read_text())["kind"],
       "orchestrator":"ChatGPT scheduled tasks via GitHub MCP",
       "simulated_minutes":minutes,
       "simulated_timestamps_per_24h":len(ticks),
       "external_schedule_verified":False,
       "actual_github_schedule_executed":False,
       "note":"Only the ChatGPT task system can confirm real scheduled runs."
    }

if __name__=="__main__":
    try:
        print(json.dumps(inspect_schedule(WORKFLOW.read_text()),indent=2))
    except (ValueError,OSError,KeyError) as e:
        print("HOLD:",str(e),file=sys.stderr)
        sys.exit(2)
