"""
Integration test — exercises the full orchestrator → agent path
using the rule-based brain (no API key needed).

This is the same code path a real voice command takes.
The only difference: the LLM brain step is replaced by regex matching.
"""

import sys
import yaml
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.orchestrator import Orchestrator

# Force rule-based brain so test runs without an API key
with open("config.yaml") as f:
    config = yaml.safe_load(f)
config["brain"]["engine"] = "rule_based"

spoken_lines = []
log_lines    = []

def speak(text, **kw):     spoken_lines.append(text)
def log(msg):              log_lines.append(msg)

orch = Orchestrator(config, speak_fn=speak, log_fn=log)

# ── Test cases: (description, command, expected_agent, expected_action) ──
TESTS = [
    ("Open an app",         "open Safari",                    "system",    "open_app"),
    ("Launch by name",      "launch Calculator",              "system",    "open_app"),
    ("Set volume",          "set volume to 60",               "system",    "set_volume"),
    ("Take screenshot",     "take a screenshot",              "system",    "take_screenshot"),
    ("Web search",          "search for python tutorials",    "web",       "search_web"),
    ("Google shorthand",    "google best coffee in berlin",   "web",       "search_web"),
    ("Add reminder",        "remind me to call mum",          "reminders", "add_reminder"),
    ("Add event",           "add an event standup meeting",   "reminders", "add_event"),
    ("Find files",          "find files named resume",        "files",     "search_files"),
    ("Organize folder",     "organize my downloads",          "files",     "organize_folder"),
    ("Draft job app",       "draft an application for ML Engineer at Google", "jobs", "draft_application"),
]

PASS = "\033[92m✓\033[0m"
FAIL = "\033[91m✗\033[0m"

print()
print("  ARIA — Integration Test  (rule-based brain, no API key needed)")
print("  " + "─" * 62)

passed = failed = 0

for desc, command, expected_agent, expected_action in TESTS:
    result = orch.interpret(command)

    if result is None:
        print(f"  {FAIL}  [{desc}]")
        print(f"       command : {command!r}")
        print(f"       expected: agent={expected_agent}, action={expected_action}")
        print(f"       got     : no match")
        failed += 1
        continue

    # Chat responses don't route to agents
    if result.get("type") == "chat":
        print(f"  {FAIL}  [{desc}]")
        print(f"       got chat response instead of command routing")
        failed += 1
        continue

    got_agent  = result.get("agent_id")
    got_action = result.get("pending_id") and orch.pending.get(result["pending_id"])

    # Grab intent from the pending action for inspection
    pending = orch.pending.get(result.get("pending_id", ""))
    got_action_name = pending.intent.action if pending else "?"
    got_params      = pending.intent.params if pending else {}

    ok = (got_agent == expected_agent and got_action_name == expected_action)

    if ok:
        print(f"  {PASS}  [{desc}]")
        print(f"       → {got_agent.upper():12}  action={got_action_name}  params={got_params}")
        passed += 1
    else:
        print(f"  {FAIL}  [{desc}]")
        print(f"       command : {command!r}")
        print(f"       expected: agent={expected_agent}, action={expected_action}")
        print(f"       got     : agent={got_agent}, action={got_action_name}")
        failed += 1

    # Cancel pending so it doesn't linger
    if result.get("pending_id"):
        orch.cancel(result["pending_id"])

print()
print("  " + "─" * 62)
print(f"  {passed}/{passed+failed} passed", end="")
if failed == 0:
    print("  \033[92m ALL CLEAR \033[0m")
else:
    print(f"  \033[91m{failed} failed\033[0m")
print()

# ── Double-confirmation flow test ──
print("  Double-confirmation flow")
print("  " + "─" * 62)

result  = orch.interpret("take a screenshot")
pid     = result["pending_id"]
step1   = orch.confirm(pid)
assert step1["status"] == "need_second_confirmation", "Expected second confirmation prompt"
print(f"  {PASS}  First confirm  → need_second_confirmation (correct)")

step2   = orch.confirm(pid)
assert step2["status"] == "executed", f"Expected executed, got {step2['status']}"
outcome = "success" if step2["success"] else f"failed ({step2['message']})"
print(f"  {PASS}  Second confirm → executed ({outcome})")

# ── Cancel flow test ──
result2 = orch.interpret("open Safari")
pid2    = result2["pending_id"]
orch.cancel(pid2)
step3   = orch.confirm(pid2)
assert step3["status"] == "unknown_pending", "Cancelled action should be gone"
print(f"  {PASS}  Cancel flow    → action removed, cannot be confirmed")

print()
sys.exit(0 if failed == 0 else 1)
