"""
tests/dry_run_check.py

Sanity-checks the orchestrator/agent/config wiring WITHOUT a mic,
speaker, or macOS — used in CI/dev environments (like the sandbox this
project was built in) that can't do real audio I/O. Run:

    python tests/dry_run_check.py

This does NOT replace testing on an actual Mac (voice, permissions,
and the real `say`/Whisper stack still need to be checked there — see
README > "First run checklist").
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import yaml

from core.orchestrator import Orchestrator

ROOT = Path(__file__).parent.parent


def load_config():
    with open(ROOT / "config.yaml") as f:
        return yaml.safe_load(f)


def main():
    failures = []

    config = load_config()
    orch = Orchestrator(config, log_fn=lambda m: print(f"  [log] {m}"))

    roster = orch.agent_roster()
    print(f"Loaded {len(roster)} agents: {[a['id'] for a in roster]}")
    expected = {"system", "web", "files", "reminders", "jobs"}
    if {a["id"] for a in roster} != expected:
        failures.append(f"Agent roster mismatch: {roster}")

    test_commands = [
        "open Safari",
        "launch Calculator",
        "set volume to 40",
        "take a screenshot",
        "search for python tutorials",
        "google best pizza in berlin",
        "remind me to buy milk",
        "add a meeting standup",
        "organize my downloads",
        "find files named resume",
        "draft an application for Software Engineer at Acme Corp",
    ]

    print("\n-- intent matching --")
    for cmd in test_commands:
        match = orch.interpret(cmd)
        if match is None:
            failures.append(f"NO MATCH: '{cmd}'")
            print(f"  [MISS] '{cmd}'")
        else:
            print(f"  [OK]   '{cmd}' -> {match['agent_id']}: {match['plan']}")
            # immediately cancel so we don't leave dangling pending actions
            orch.cancel(match["pending_id"])

    unmatched = "asdlkfj qwoeiru nonsense command"
    if orch.interpret(unmatched) is not None:
        failures.append("Unmatched gibberish incorrectly matched an agent")
    else:
        print(f"\n[OK] correctly found no match for gibberish input")

    print("\n-- double confirmation flow (system agent: take a screenshot) --")
    match = orch.interpret("take a screenshot")
    assert match is not None
    r1 = orch.confirm(match["pending_id"])
    print(f"  first confirm -> {r1['status']}")
    if r1["status"] != "need_second_confirmation":
        failures.append(f"Expected need_second_confirmation, got {r1['status']}")
    r2 = orch.confirm(match["pending_id"])
    print(f"  second confirm -> {r2['status']} success={r2.get('success')} msg={r2.get('message')}")
    if r2["status"] != "executed":
        failures.append(f"Expected executed after second confirm, got {r2['status']}")

    print("\n-- cancel flow --")
    match = orch.interpret("open Safari")
    cancel_result = orch.cancel(match["pending_id"])
    followup = orch.confirm(match["pending_id"])
    if followup["status"] != "unknown_pending":
        failures.append("Cancelled action should no longer be confirmable")
    else:
        print("  [OK] cancelled action can no longer be confirmed")

    print("\n-- job agent auto_submit safety default --")
    jobs_cfg = next(a for a in config["agents"] if a["id"] == "jobs")
    if jobs_cfg.get("auto_submit", False) is not False:
        failures.append("auto_submit should default to false in shipped config.yaml")
    else:
        print("  [OK] auto_submit defaults to false")

    print("\n" + "=" * 50)
    if failures:
        print(f"FAILED ({len(failures)} issue(s)):")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)
    else:
        print("ALL CHECKS PASSED")


if __name__ == "__main__":
    main()
