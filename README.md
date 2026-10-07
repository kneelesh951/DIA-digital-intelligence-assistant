<div align="center">

<img src="https://img.shields.io/badge/DIA-Digital%20Intelligence%20Assistant-blueviolet?style=for-the-badge&logo=anthropic&logoColor=white" alt="DIA"/>

# DIA — Digital Intelligence Assistant

### A voice-first, agentic AI operating layer for macOS

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![Claude](https://img.shields.io/badge/Powered%20by-Claude%20Haiku-blueviolet?style=flat-square&logo=anthropic&logoColor=white)](https://anthropic.com)
[![Whisper](https://img.shields.io/badge/STT-Faster%20Whisper-green?style=flat-square)](https://github.com/guillaumekln/faster-whisper)
[![License](https://img.shields.io/badge/License-MIT-yellow?style=flat-square)](LICENSE)
[![macOS](https://img.shields.io/badge/Platform-macOS-lightgrey?style=flat-square&logo=apple&logoColor=white)](https://apple.com/macos)

<br/>

> **DIA is not another chatbot.**
> It's an autonomous multi-agent AI system that sits between you and your Mac —
> understanding your intent, orchestrating specialist agents, and acting on your behalf
> with full transparency and human-in-the-loop control.

<br/>

</div>

---

## What is Agentic AI?

Traditional AI assistants respond. **Agentic AI acts.**

DIA uses a **multi-agent architecture** where a central LLM router understands your intent and delegates to specialist autonomous agents — each with its own domain expertise, safety boundaries, and execution capabilities. No single model tries to do everything; each agent is purpose-built, sandboxed, and accountable.

```
You speak → Intent is understood → The right agent is selected → Action is confirmed → Result is executed
```

This is the same architectural pattern behind frontier AI systems like AutoGPT, CrewAI, and enterprise agentic platforms — built for your personal Mac, running mostly offline.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        USER INPUT                           │
│              Voice (Whisper STT) · Text (HUD)               │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                      LLM BRAIN                              │
│         Claude Haiku — intent routing & NLU                 │
│    "What does the user want, and which agent handles it?"   │
└──────────────────────────┬──────────────────────────────────┘
                           │  structured intent
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                    ORCHESTRATOR                             │
│          Human-in-the-loop double-confirmation flow         │
│     Nothing executes without explicit user approval         │
└──────────────────────────┬──────────────────────────────────┘
                           │  confirmed intent
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                  SPECIALIST AGENTS                          │
│  SENTRY · SCOUT · VAULT · ECHO · HERALD · QUANT · ORACLE · HERMES  │
└──────────────────────────┬──────────────────────────────────┘
                           │  action result
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                       OUTPUT                                │
│            TTS (macOS say) · HUD (pywebview)                │
└─────────────────────────────────────────────────────────────┘
```

The only cloud call is the LLM routing step (~$0.0003/message, ~1s). Everything else — speech, TTS, agent execution — runs fully on-device.

---

## Agent Roster

| Codename | Domain | Capabilities |
|:---:|---|---|
| **SENTRY** | System Control | Launch/quit apps, adjust volume, take screenshots, lock screen |
| **SCOUT** | Web Intelligence | Search the web, open URLs, navigate browsers |
| **VAULT** | File Management | Find, move, rename files — sandboxed to approved paths only |
| **ECHO** | Reminders & Calendar | Create reminders and calendar events via AppleScript |
| **HERALD** | Job Applications | Draft cover letters, autofill job forms via Playwright |
| **QUANT** | Market Intelligence | Live stock quotes, market overview, movers, personal watchlist |
| **ORACLE** | Daily Briefing | Morning voice summary — weather, calendar, top market movers |
| **HERMES** | Email | Read and summarize Gmail inbox via IMAP (read-only) |

Each agent is independently scoped, sandboxed, and extensible. Adding a new agent requires no changes to the core orchestration layer.

---

## Human-in-the-Loop Safety Model

DIA enforces a **double-confirmation protocol** before any action executes:

```
Step 1 — UNDERSTAND   DIA shows a plain-English summary of what it interpreted
Step 2 — CONFIRM      You approve once → DIA asks you to confirm a second time  
Step 3 — EXECUTE      Only on the second approval does the agent run
```

This is enforced at the orchestrator level. No agent, no LLM output, and no shortcut can bypass it. Per-agent safety flags in `config.yaml` let you tune confirmation requirements per domain.

---

## Tech Stack

| Layer | Technology | Why |
|---|---|---|
| **LLM Routing** | Claude Haiku (Anthropic) | Fastest, cheapest frontier model for intent classification |
| **Speech Recognition** | faster-whisper (int8) | Fully offline, CPU-only, ~500MB model |
| **Text-to-Speech** | macOS `say` | Zero install, uses the same engine as Siri |
| **UI / HUD** | pywebview + HTML/CSS/JS | Native macOS window, no Electron overhead |
| **Browser Automation** | Playwright (Chromium) | Real browser, never headless — user sees every action |
| **System Integration** | osascript (AppleScript) | Controls Reminders, Calendar, System Events natively |
| **Market Data** | Yahoo Finance | Free real-time data, no API key required |

---

## Quick Start

```bash
# Clone
git clone https://github.com/kneelesh951/DIA-digital-intelligence-assistant.git
cd DIA-digital-intelligence-assistant

# Set up environment
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Configure
echo "ANTHROPIC_API_KEY=your_key_here" > .env

# Launch
python app.py
```

> First run downloads the Whisper model (~500MB, one-time only).
> macOS will prompt for microphone and automation permissions on first use.

**Optional:** Add `GMAIL_APP_PASSWORD=xxxx` to `.env` to enable HERMES.
See `agents/gmail_agent.py` for Gmail IMAP setup instructions.

---

## Configuration

All behaviour is controlled from a single `config.yaml` — no code changes needed for most customisation:

```yaml
brain:
  engine: llm              # "llm" (Claude) or "rule_based" (offline regex)

daily_briefing:
  enabled: true
  time: "08:00"

agents:
  - id: vault
    allowed_paths:
      - "~/Documents"
      - "~/Downloads"      # VAULT refuses to touch anything outside these folders
```

---

## Extending DIA

### Add a new agent in 4 steps

```
1. agents/your_agent.py      — extend Agent, define PATTERNS and execute()
2. config.yaml               — register under agents: with id, name, description
3. ui/app.js                 — add an animated SVG viz for the HUD
4. Restart                   — Claude discovers the new agent from its description
```

No changes to the orchestrator, brain, or any existing agent required.

### Switch to rule-based routing (free, offline)

```yaml
brain:
  engine: rule_based
```

Each agent's `PATTERNS` list (regex) handles routing — zero API calls, zero latency.

---

## Roadmap

- [ ] **Clipboard Transformer** — global hotkey to summarize, reformat, or translate clipboard content via LLM
- [ ] **File Organizer AI** — VAULT watches `~/Downloads`, auto-classifies new files using LLM
- [ ] **Research Agent** — multi-step web research with LLM synthesis and structured output
- [ ] **Windows support** — port STT/TTS/UI layer to run on Windows
- [ ] **Agent Marketplace** — publish and install community-built agents

---

## Project Structure

```
app.py                  Entry point
bridge.py               JS ↔ Python API surface (pywebview)
config.yaml             Single source of truth for all configuration
core/
  brain.py              LLM + rule-based intent routing
  orchestrator.py       Double-confirmation safety flow
  stt.py                Whisper speech-to-text
  tts.py                macOS TTS wrapper
  voices.py             Voice availability detection
agents/
  base.py               Agent base class (Intent, ActionResult)
  system_agent.py       SENTRY
  web_agent.py          SCOUT
  file_agent.py         VAULT
  reminder_agent.py     ECHO
  job_agent.py          HERALD
  stock_agent.py        QUANT
  briefing_agent.py     ORACLE
  gmail_agent.py        HERMES
ui/
  index.html            HUD shell
  style.css             Dark sci-fi design
  app.js                HUD state, JS↔Python calls, agent vizzes
profile/
  job_profile.yaml      Personal info for HERALD
  cover_letter_template.txt
tests/
  dry_run_check.py      No-mic sanity test
```

---

## License

MIT © 2026 Neel

---

<div align="center">

Built with [Claude](https://anthropic.com) · Runs on macOS · Fully open source

</div>
