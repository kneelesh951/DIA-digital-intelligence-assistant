# DIA — Digital Intelligence Assistant

> A voice-first, multi-agent AI operating layer for macOS.

DIA is not another chatbot. It's an **autonomous personal AI system** that sits between you and your Mac — understanding your intent, orchestrating specialist agents, and acting on your behalf with full transparency and human-in-the-loop control.

---

## What Makes DIA Different

| Capability | DIA | Traditional Assistants |
|---|---|---|
| **Multi-agent orchestration** | 8 specialist agents, LLM-routed | Single monolithic model |
| **Privacy-first** | Fully local execution, one API call for routing | Everything sent to the cloud |
| **Safety model** | Double-confirmation before every action | Fire-and-forget |
| **Offline STT/TTS** | Whisper + macOS `say` | Cloud-dependent |
| **Extensible** | Add a new agent in one Python file + one YAML block | Closed ecosystem |

---

## Architecture

```
Voice / Text Input
       │
       ▼
  STT (Whisper)           — offline, runs on-device
       │
       ▼
  LLM Brain (Claude)      — routes intent to the right agent
       │
       ▼
  Orchestrator            — enforces double-confirmation safety flow
       │
       ▼
  Specialist Agent        — executes the action
       │
       ▼
  TTS + HUD Output        — speaks result, updates the UI
```

The only cloud call is the routing decision (~$0.0003 per message, ~1s latency). Everything else runs locally.

---

## Agents

| Agent | Codename | Capability |
|---|---|---|
| System Control | SENTRY | Launch/quit apps, volume, screenshot, lock screen |
| Web | SCOUT | Search the web, open URLs |
| File Manager | VAULT | Find, move, rename files — sandboxed to allowed paths |
| Reminders | ECHO | Add reminders and calendar events via AppleScript |
| Job Assistant | HERALD | Draft cover letters, autofill job application forms |
| Stocks | QUANT | Live quotes, market overview, movers, personal watchlist |
| Daily Briefing | ORACLE | Morning voice briefing — weather, calendar, markets |
| Email | HERMES | Read and summarize Gmail inbox via IMAP |

---

## Safety Model

Every command goes through a **double-confirmation flow** before anything runs:

```
1. DIA shows you a plain-English summary of what it understood
2. You confirm once → DIA asks you to confirm again
3. Only on the second confirmation does the agent execute
```

Nothing irreversible happens off a single click. This is enforced at the orchestrator level and cannot be bypassed by any agent.

---

## Tech Stack

- **Claude (Haiku)** — LLM intent routing and conversational fallback
- **faster-whisper** — Offline speech recognition (int8 quantised, runs on CPU)
- **pywebview** — Native macOS window rendered with WKWebView (HTML/CSS/JS HUD)
- **macOS `say`** — Offline TTS using system voices (same engine as Siri)
- **Playwright** — Browser automation for HERALD (never headless by default)
- **osascript** — AppleScript bridge for Reminders, Calendar, System Events
- **Yahoo Finance** — Free real-time market data for QUANT (no API key needed)

---

## Quick Start

```bash
# 1. Clone the repo
git clone https://github.com/kneelesh951/DIA-digital-intelligence-assistant.git
cd DIA-digital-intelligence-assistant

# 2. Create a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Add your Anthropic API key
echo "ANTHROPIC_API_KEY=your_key_here" > .env

# 5. Run
python app.py
```

> **Optional:** Set `GMAIL_APP_PASSWORD` in `.env` to enable HERMES (Gmail agent).
> See `agents/gmail_agent.py` for IMAP setup instructions.

---

## Configuration

Everything user-facing lives in `config.yaml` — agent descriptions, allowed paths, voice settings, scheduled briefing time. No code changes needed for most customisation.

```yaml
brain:
  engine: llm          # or "rule_based" for offline/free routing

daily_briefing:
  enabled: true
  time: "08:00"        # 24-hour format

agents:
  - id: vault
    allowed_paths:
      - "~/Documents"
      - "~/Downloads"   # VAULT will refuse to touch anything outside these
```

---

## Adding a New Agent

1. Create `agents/your_agent.py` — extend `Agent`, define `PATTERNS` and `execute()`
2. Register it in `config.yaml` under `agents:`
3. Add an animated SVG viz in `ui/app.js`
4. Restart — the LLM discovers it automatically from the `description` field

No changes to orchestrator, brain, or any existing agent.

---

## Roadmap

- [ ] Clipboard Transformer — global hotkey to summarize, reformat, or translate clipboard content
- [ ] File Organizer AI — VAULT watches `~/Downloads`, auto-classifies new files using LLM
- [ ] Research Agent — multi-step web research with LLM synthesis
- [ ] Windows support
- [ ] Agent Marketplace

---

## License

MIT
