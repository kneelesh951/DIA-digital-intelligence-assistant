"""
agents/briefing_agent.py

ORACLE — delivers a personalized daily briefing: time, weather, today's
calendar events, and top market mover. No confirmation required (read-only).

Triggers:
  - Voice: "morning briefing", "what's my day", "daily update", etc.
  - Button: the ☀ BRIEFING button in the HUD quick-actions bar.
  - Scheduled: bridge.py fires the trigger at the time set in config.yaml.
"""

import json
import subprocess
import urllib.request
from datetime import datetime

from agents.base import Agent, ActionResult, Intent


class BriefingAgent(Agent):
    PATTERNS = [
        ("daily_brief",
         r"(morning|daily|day|today'?s?)\s*(brief(ing)?|summary|update|report|rundown)"),
        ("daily_brief",
         r"what'?s?\s*(my\s*)?(day|schedule|agenda|plan)\s*(look|like|today)?"),
        ("daily_brief",
         r"(give|tell)\s+me\s+(my\s*)?(briefing|update|summary|day)"),
        ("daily_brief",
         r"(what'?s?|any)\s+(on\s+)?my\s+(calendar|schedule|agenda)\s*(today)?"),
        ("daily_brief",
         r"what\s+is\s+my\s+(schedule|day|agenda|calendar)\s*(today|like)?"),
        ("get_weather",
         r"(what'?s?|how'?s?|tell me)\s*(the\s*)?(weather|temperature|temp|conditions?|forecast)\s*(like|now|today|outside|currently)?"),
        ("get_weather",
         r"(how\s+)?(hot|cold|warm|cool)\s+(is\s+it|outside|today)"),
        ("get_weather",
         r"(is\s+it\s+)?(raining|snowing|sunny|cloudy)\s*(outside|today)?"),
        ("get_time",
         r"(what\s*(is|'s)\s*(the\s*)?(time|current\s+time))|(what\s+time\s+is\s+it)"),
        ("get_time",
         r"(tell\s+me\s+(the\s*)?time)|(current\s+time)"),
    ]

    # ── data helpers ──────────────────────────────────────────────────────────

    def _weather(self):
        ICONS = {
            113: "sunny", 116: "partly cloudy", 119: "cloudy", 122: "overcast",
            176: "light rain", 200: "thunderstorm", 293: "light rain",
            296: "drizzle", 299: "rain", 302: "heavy rain", 323: "light snow",
        }
        try:
            req = urllib.request.Request(
                "https://wttr.in/?format=j1",
                headers={"User-Agent": "curl/7.64"}
            )
            with urllib.request.urlopen(req, timeout=6) as r:
                d = json.loads(r.read())
            cur = d["current_condition"][0]
            code = int(cur["weatherCode"])
            desc = ICONS.get(code, cur["weatherDesc"][0]["value"].lower())
            city = d["nearest_area"][0]["areaName"][0]["value"]
            temp = cur["temp_C"]
            feels = cur["FeelsLikeC"]
            return f"In {city}, it's {temp} degrees and {desc}, feels like {feels}."
        except Exception:
            return ""

    def _calendar(self):
        script = (
            'tell application "Calendar"\n'
            '    set out to ""\n'
            '    set now_d to current date\n'
            '    set end_d to now_d + (24 * 60 * 60)\n'
            '    repeat with c in calendars\n'
            '        try\n'
            '            set evts to (every event of c whose start date >= now_d and start date <= end_d)\n'
            '            repeat with e in evts\n'
            '                set out to out & (summary of e as text) & "|" & (start date of e as text) & "\\n"\n'
            '            end repeat\n'
            '        end try\n'
            '    end repeat\n'
            '    return out\n'
            'end tell'
        )
        try:
            r = subprocess.run(["osascript", "-e", script],
                               capture_output=True, text=True, timeout=10)
            events = []
            for line in r.stdout.strip().split("\n"):
                if "|" in line:
                    title, date = line.split("|", 1)
                    title = title.strip()
                    # Extract just HH:MM from the date string
                    import re
                    m = re.search(r'(\d+:\d+:\d+\s*[AP]M)', date, re.IGNORECASE)
                    time_str = m.group(1).lstrip("0") if m else date.strip()[:11]
                    if title:
                        events.append(f"{title} at {time_str}")
            if not events:
                return "Your calendar is clear today."
            count = len(events)
            listed = ", ".join(events[:3])
            suffix = f" and {count - 3} more" if count > 3 else ""
            return f"You have {count} event{'s' if count > 1 else ''} today: {listed}{suffix}."
        except Exception:
            return "Calendar data unavailable."

    def _top_mover(self):
        try:
            url = ("https://query1.finance.yahoo.com/v1/finance/screener/predefined/saved"
                   "?scrIds=day_gainers&count=1&lang=en-US&region=US")
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0", "Accept": "application/json"
            })
            with urllib.request.urlopen(req, timeout=6) as r:
                d = json.loads(r.read())
            q = d["finance"]["result"][0]["quotes"][0]
            sym = q["symbol"]
            pct = round(float(q.get("regularMarketChangePercent", 0)), 1)
            return f"Today's top market mover is {sym}, up {pct} percent."
        except Exception:
            return ""

    # ── agent interface ───────────────────────────────────────────────────────

    def describe_plan(self, intent: Intent) -> str:
        return "Gathering weather, calendar, and market data for your briefing."

    def execute(self, intent: Intent) -> ActionResult:
        if intent.action == "get_weather":
            weather = self._weather()
            if weather:
                return ActionResult(success=True, message=weather)
            return ActionResult(success=False, message="Couldn't fetch weather right now. Check your connection.")

        if intent.action == "get_time":
            now = datetime.now()
            day_str  = now.strftime("%A, %B %-d")
            time_str = now.strftime("%-I:%M %p")
            return ActionResult(success=True, message=f"It's {time_str} on {day_str}.")

        # daily_brief
        now = datetime.now()
        hour = now.hour

        if hour < 12:
            greeting = "Good morning"
        elif hour < 17:
            greeting = "Good afternoon"
        else:
            greeting = "Good evening"

        day_str  = now.strftime("%A, %B %-d")
        time_str = now.strftime("%-I:%M %p")

        parts = [f"{greeting}. Today is {day_str}, {time_str}."]

        weather = self._weather()
        if weather:
            parts.append(weather)

        parts.append(self._calendar())

        mover = self._top_mover()
        if mover:
            parts.append(mover)

        parts.append("That's your briefing. Have a great day.")

        return ActionResult(success=True, message=" ".join(parts))
