"""
agents/base.py

Base class every agent inherits from. An agent's "duties" are defined
by three things, all editable without touching the orchestrator:

  1. `allowed_actions` (config.yaml) — the whitelist of action names
     this agent may perform. Anything not listed here is refused even
     if a pattern below matches it.
  2. `PATTERNS` (this file, per-agent subclass) — a list of
     (action_name, regex) pairs the agent recognizes in spoken/typed
     text. Named regex groups become `params`. Override `match()`
     entirely for custom logic.
  3. `execute()` — what actually happens once an action + params have
     cleared confirmation.

To add a brand-new custom agent:
  1. Create agents/my_agent.py with a class shaped like this one.
  2. Add a block for it under `agents:` in config.yaml (id, name,
     color, description, module, class, allowed_actions, ...).
  3. Restart the app — it now shows up in the HUD roster automatically.

See README.md > "Defining agent duties" for a full walkthrough.
"""

import re
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Intent:
    agent_id: str
    action: str
    params: dict
    confidence: float
    raw_text: str


@dataclass
class ActionResult:
    success: bool
    message: str
    data: dict = field(default_factory=dict)


class AgentBus:
    """
    Shared message bus injected into every agent at startup.
    Allows agents to delegate sub-tasks to other agents without
    going through the confirmation flow (bus calls are internal,
    programmatic, and already trusted).

    Usage inside any agent's execute():
        result = self.bus.call("web", "search_web", {"query": "AI news"})
        result = self.bus.call("reminders", "add_reminder", {"task": "Review notes at 5pm"})
    """

    def __init__(self):
        self._agents: dict = {}

    def register(self, agent_id: str, agent) -> None:
        self._agents[agent_id] = agent

    def call(self, agent_id: str, action: str, params: dict) -> ActionResult:
        agent = self._agents.get(agent_id)
        if not agent:
            return ActionResult(False, f"Agent '{agent_id}' not found on the bus.")
        if action not in agent.allowed_actions:
            return ActionResult(False, f"'{action}' is not an allowed action for {agent.name}.")
        intent = Intent(agent_id=agent_id, action=action, params=params,
                        confidence=1.0, raw_text="[bus-call]")
        try:
            return agent.execute(intent)
        except Exception as exc:
            return ActionResult(False, f"{agent.name} raised an error: {exc}")

    def available(self) -> list[str]:
        return list(self._agents.keys())


# Module-level singleton — shared by every agent instance.
BUS = AgentBus()


class Agent:
    # Subclasses override this: list of (action_name, regex_pattern).
    # Named groups in the regex (?P<name>...) become intent.params.
    PATTERNS: list[tuple[str, str]] = []

    def __init__(self, agent_cfg: dict, app_config: dict):
        self.id = agent_cfg["id"]
        self.name = agent_cfg["name"]
        self.color = agent_cfg.get("color", "#00e5ff")
        self.icon = agent_cfg.get("icon", "cpu")
        self.description = agent_cfg.get("description", "")
        self.allowed_actions = set(agent_cfg.get("allowed_actions", []))
        self.requires_confirmation = agent_cfg.get("requires_confirmation", True)
        self.double_confirmation = agent_cfg.get("double_confirmation", False)
        self.cfg = agent_cfg
        self.app_config = app_config
        self.bus = BUS          # every agent gets the shared bus
        self._compiled = [
            (action, re.compile(pattern, re.IGNORECASE)) for action, pattern in self.PATTERNS
        ]

    def match(self, text: str) -> Optional[Intent]:
        """Return an Intent if this agent recognizes the command text, else None."""
        for action, pattern in self._compiled:
            if action not in self.allowed_actions:
                continue
            m = pattern.search(text)
            if m:
                params = {k: v.strip() for k, v in m.groupdict().items() if v}
                return Intent(agent_id=self.id, action=action, params=params, confidence=0.8, raw_text=text)
        return None

    def describe_plan(self, intent: Intent) -> str:
        """Human-readable summary shown at confirmation step 1 ('here's what I'm about to do')."""
        detail = ", ".join(f"{k}: {v}" for k, v in intent.params.items()) or "no extra details"
        return f"{self.name} will {intent.action.replace('_', ' ')} ({detail})"

    def execute(self, intent: Intent) -> ActionResult:
        raise NotImplementedError(f"{self.__class__.__name__} must implement execute()")
