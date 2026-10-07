"""
core/orchestrator.py

Central dispatcher: loads enabled agents from config.yaml, uses the
brain (core/brain.py) to match incoming text to an agent+action, and
enforces the double-confirmation flow before anything executes.

Confirmation flow:
  1. interpret(text)   -> PendingAction with a plain-English plan
                           description. Nothing has happened yet.
  2. confirm(id)        -> first "yes". If double confirmation is
                           required (global default, or this specific
                           agent demands it — e.g. HERALD/job agent),
                           returns "need_second_confirmation" instead
                           of executing.
  3. confirm(id) again   -> only now does the agent's execute() run.
  cancel(id) can be called at any stage instead.

This means no agent ever takes action off a single "yes" for anything
irreversible — by config default, nothing does.
"""

import importlib
import uuid
from dataclasses import dataclass

from agents.base import Intent, ActionResult
from core.brain import build_brain


@dataclass
class PendingAction:
    id: str
    intent: Intent
    agent: object
    plan_description: str
    stage: str = "awaiting_first_confirmation"


class Orchestrator:
    def __init__(self, config: dict, speak_fn=None, log_fn=None):
        self.config = config
        self.speak = speak_fn or (lambda *a, **k: None)
        self.log = log_fn or (lambda *a, **k: None)
        self.agents = {}
        self.pending: dict[str, PendingAction] = {}
        self._load_agents()
        self.brain = build_brain(config, self.agents)

    def _load_agents(self):
        from agents.base import BUS
        for agent_cfg in self.config.get("agents", []):
            if not agent_cfg.get("enabled", True):
                continue
            try:
                module = importlib.import_module(agent_cfg["module"])
                cls = getattr(module, agent_cfg["class"])
                agent = cls(agent_cfg, self.config)
                self.agents[agent_cfg["id"]] = agent
                BUS.register(agent_cfg["id"], agent)   # publish to shared bus
            except Exception as exc:
                self.log(f"Failed to load agent '{agent_cfg.get('id')}': {exc}")

    def agent_roster(self) -> list[dict]:
        """For the HUD's agent panel."""
        return [
            {
                "id": a.id,
                "name": a.name,
                "color": a.color,
                "icon": a.icon,
                "description": a.description,
            }
            for a in self.agents.values()
        ]

    def interpret(self, text: str, lang: str = "en"):
        """Step 1: match text to an agent+action (or a conversational reply).

        Returns one of:
          None                          — nothing matched
          {"type": "chat", ...}         — conversational reply, speak it directly
          {"type": "command", ...}      — actionable, show confirmation modal
        """
        text = text.strip()
        if not text:
            return None

        result = self.brain.interpret(text, lang=lang)
        if result is None:
            return None

        kind = result[0]

        if kind == "chat":
            _, message = result
            return {"type": "chat", "message": message}

        # kind == "command"
        _, intent, agent = result

        # Agents that don't require confirmation (informational/read-only) execute immediately
        # and return their result as a chat message — no modal, no pending queue.
        if not getattr(agent, "requires_confirmation", True):
            try:
                action_result = agent.execute(intent)
                return {"type": "chat", "message": action_result.message}
            except Exception as exc:
                return {"type": "chat", "message": f"Error running {agent.name}: {exc}"}

        plan = agent.describe_plan(intent)
        pending = PendingAction(id=str(uuid.uuid4()), intent=intent, agent=agent, plan_description=plan)
        self.pending[pending.id] = pending
        return {
            "type": "command",
            "pending_id": pending.id,
            "agent_id": agent.id,
            "agent_name": agent.name,
            "agent_color": agent.color,
            "plan": plan,
        }

    def confirm(self, pending_id: str) -> dict:
        pending = self.pending.get(pending_id)
        if not pending:
            return {"status": "unknown_pending"}

        require_double = self.config["confirmation"]["require_double_confirmation"]
        agent_needs_double = getattr(pending.agent, "double_confirmation", False)

        if pending.stage == "awaiting_first_confirmation":
            if require_double or agent_needs_double:
                pending.stage = "awaiting_second_confirmation"
                msg = (
                    f"Confirmed. Final check — {pending.agent.name} is about to "
                    f"{pending.intent.action.replace('_', ' ')}. Confirm once more to proceed."
                )
                return {"status": "need_second_confirmation", "message": msg, "pending_id": pending_id}
            return self._execute(pending)

        if pending.stage == "awaiting_second_confirmation":
            return self._execute(pending)

        return {"status": "unknown_pending"}

    def cancel(self, pending_id: str) -> dict:
        self.pending.pop(pending_id, None)
        return {"status": "cancelled"}

    def _execute(self, pending: PendingAction) -> dict:
        del self.pending[pending.id]
        try:
            result: ActionResult = pending.agent.execute(pending.intent)
        except Exception as exc:  # an agent bug should never crash the whole app
            result = ActionResult(success=False, message=f"Error: {exc}")
        return {
            "status": "executed",
            "success": result.success,
            "message": result.message,
            "data": result.data,
            "agent_id": pending.agent.id,
            "agent_name": pending.agent.name,
        }
