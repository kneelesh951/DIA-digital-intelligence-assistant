"""
core/brain.py

Pluggable command-understanding layer, selected by config.yaml brain.engine.

  RuleBasedBrain (engine: "rule_based")
    Free, fully offline. Delegates matching to each agent's own
    `match()` regex/keyword patterns (agents/base.py).

  LLMBrain (engine: "llm")
    Uses Claude to understand natural language. Routes commands to
    agents AND handles conversational replies. Requires ANTHROPIC_API_KEY
    in the environment. Set brain.llm.api_key_env_var in config.yaml
    to use a different env var name.

Both brains return one of:
  ("command", Intent, Agent)  — route to an agent for confirmation + execution
  ("chat",    str)            — conversational reply, speak it directly
  None                        — nothing matched / brain couldn't decide
"""

import json
import os
from typing import Optional

from agents.base import Intent


class RuleBasedBrain:
    def __init__(self, agents: dict):
        self.agents = agents

    def interpret(self, text: str, lang: str = "en") -> Optional[tuple]:
        best = None
        for agent in self.agents.values():
            intent = agent.match(text)
            if intent and (best is None or intent.confidence > best[1].confidence):
                best = (agent, intent)
        if best is None:
            return None
        agent, intent = best
        return ("command", intent, agent)


class LLMBrain:
    _SYSTEM_PROMPT_TEMPLATE = """\
You are DIA (Digital Intelligence Assistant), a futuristic macOS desktop voice assistant. \
You are precise, friendly, and speak in a calm, confident tone. You have these agents:

{agent_list}

When the user sends a message, respond with ONLY a valid JSON object — no markdown, no explanation, no extra keys.

If the message is a task one of the agents can handle, respond:
{{"type": "command", "agent_id": "<id>", "action": "<action>", "params": {{<key>: "<value>"}}}}

If the message asks about weather, temperature, current time, or email/inbox, ALWAYS route to an agent (do NOT answer as chat — you don't have real-time data).

If the message is conversational (greeting, question about yourself, compliment, thanks, general knowledge chit-chat), respond:
{{"type": "chat", "message": "<your reply as DIA — warm, concise, futuristic tone, max 2 sentences>"}}

Parameter reference by action:
  open_app / quit_app      → {{"app": "<App Name>"}}
  set_volume               → {{"level": "<0-100>"}}
  take_screenshot          → {{}}
  lock_screen              → {{}}
  search_web               → {{"query": "<search terms>"}}
  open_url                 → {{"url": "<domain.tld or full url>"}}
  search_files             → {{"query": "<filename or pattern>"}}
  organize_folder          → {{"folder": "<downloads|desktop|documents>"}}
  move_file                → {{"source": "<full path>", "destination": "<full path>"}}
  add_reminder             → {{"task": "<full reminder text including time if mentioned>"}}
  add_event                → {{"title": "<event title>", "when": "<time or date if mentioned>"}}
  draft_application        → {{"job_title": "<role>", "company": "<company name>"}}
  fill_application         → {{"url": "<job application URL>"}}
  daily_brief              → {{}}
  get_weather              → {{}}
  get_time                 → {{}}
  check_inbox              → {{}}
  read_latest              → {{}}
  get_quote                → {{"symbol": "<ticker or company name, e.g. AAPL or Apple>"}}
  get_market               → {{}}
  get_movers               → {{}}
  get_news                 → {{"symbol": "<ticker or company name>"}}
  watch_stock              → {{"symbol": "<ticker or company name>"}}
  get_watchlist            → {{}}
  compare                  → {{"symbol1": "<first stock>", "symbol2": "<second stock>"}}
"""

    def __init__(self, agents: dict, llm_cfg: dict):
        self.agents = agents
        self.llm_cfg = llm_cfg
        self._client = None
        self._model = llm_cfg.get("model", "claude-haiku-4-5-20251001")
        self._fallback = RuleBasedBrain(agents)

    def _client_lazy(self):
        if self._client is None:
            import anthropic
            env_var = self.llm_cfg.get("api_key_env_var", "ANTHROPIC_API_KEY")
            key = os.environ.get(env_var)
            if not key:
                raise RuntimeError(
                    f"LLM brain is enabled but ${env_var} is not set. "
                    f"Export your Anthropic API key: export {env_var}=sk-ant-..."
                )
            self._client = anthropic.Anthropic(api_key=key)
        return self._client

    def _system_prompt(self) -> str:
        lines = []
        for a in self.agents.values():
            actions = ", ".join(a.allowed_actions)
            lines.append(f"  • {a.id} ({a.name}): {a.description} — actions: {actions}")
        return self._SYSTEM_PROMPT_TEMPLATE.format(agent_list="\n".join(lines))

    _LANG_NAMES = {"en": "English", "hi": "Hindi", "de": "German"}

    def interpret(self, text: str, lang: str = "en") -> Optional[tuple]:
        try:
            client = self._client_lazy()
        except RuntimeError:
            return self._fallback.interpret(text, lang)

        lang_name = self._LANG_NAMES.get(lang, lang)
        system = self._system_prompt()
        if lang != "en":
            system += (
                f"\n\nThe user is currently speaking {lang_name}. "
                f"For 'chat' replies, respond in {lang_name}. "
                f"For 'command' replies the JSON keys stay in English as shown above."
            )

        try:
            response = client.messages.create(
                model=self._model,
                max_tokens=256,
                system=system,
                messages=[{"role": "user", "content": text}],
            )
            raw = response.content[0].text.strip()
            # Strip accidental markdown fences
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            rb = self._fallback.interpret(text, lang)
            if rb:
                return rb
            return ("chat", "I understood you, but had trouble deciding what to do. Could you rephrase?")
        except Exception as exc:
            rb = self._fallback.interpret(text, lang)
            if rb:
                return rb
            return ("chat", f"My AI brain is unreachable ({exc}). Check your ANTHROPIC_API_KEY.")

        kind = parsed.get("type")

        if kind == "chat":
            return ("chat", parsed.get("message", "I'm not sure how to respond to that."))

        if kind == "command":
            agent_id = parsed.get("agent_id", "")
            action = parsed.get("action", "")
            params = {k: str(v) for k, v in parsed.get("params", {}).items()}

            agent = self.agents.get(agent_id)
            if not agent:
                return ("chat", f"I wanted to use agent '{agent_id}', but it isn't loaded.")
            if action not in agent.allowed_actions:
                return ("chat", f"'{action}' isn't an allowed action for {agent.name}.")

            intent = Intent(
                agent_id=agent_id,
                action=action,
                params=params,
                confidence=0.95,
                raw_text=text,
            )
            return ("command", intent, agent)

        return None


def build_brain(config: dict, agents: dict):
    engine = config.get("brain", {}).get("engine", "rule_based")
    if engine == "llm":
        return LLMBrain(agents, config.get("brain", {}).get("llm", {}))
    return RuleBasedBrain(agents)
