"""
agents/reminder_agent.py

ECHO — creates reminders and calendar events using the native macOS
Reminders and Calendar apps via AppleScript, so they show up exactly
like ones you'd add yourself (and sync via iCloud if that's on).
"""

import re
import subprocess
from datetime import datetime, timedelta

from agents.base import Agent, Intent, ActionResult


def _parse_time(text: str) -> datetime | None:
    """Best-effort: extract a target datetime from reminder text."""
    now = datetime.now()
    t = text.lower()

    # Relative: "in 30 minutes", "in 2 hours"
    m = re.search(r'in\s+(\d+)\s+(minute|hour|day)s?', t)
    if m:
        n, unit = int(m.group(1)), m.group(2)
        delta = {"minute": timedelta(minutes=n), "hour": timedelta(hours=n), "day": timedelta(days=n)}[unit]
        return now + delta

    # Specific: "at 5pm", "at 14:30", "at 9 am"
    m = re.search(r'at\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?', t)
    if m:
        hour = int(m.group(1))
        minute = int(m.group(2)) if m.group(2) else 0
        meridiem = m.group(3)
        if meridiem == "pm" and hour < 12:
            hour += 12
        elif meridiem == "am" and hour == 12:
            hour = 0
        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if target < now:          # already passed today → schedule for tomorrow
            target += timedelta(days=1)
        return target

    # Named: "tomorrow", "tonight", "this evening"
    if "tomorrow" in t:
        return (now + timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)
    if "tonight" in t or "this evening" in t:
        return now.replace(hour=20, minute=0, second=0, microsecond=0)
    if "this morning" in t:
        return now.replace(hour=9, minute=0, second=0, microsecond=0)

    return None


def _strip_time_phrase(text: str) -> str:
    """Remove the time qualifier from the task description."""
    patterns = [
        r'\s*(in\s+\d+\s+(?:minute|hour|day)s?)',
        r'\s*(at\s+\d{1,2}(?::\d{2})?\s*(?:am|pm)?)',
        r'\s*(tomorrow|tonight|this evening|this morning)',
    ]
    for p in patterns:
        text = re.sub(p, '', text, flags=re.IGNORECASE)
    return text.strip()


class ReminderAgent(Agent):
    PATTERNS = [
        ("add_reminder", r"\bremind me to (?P<task>.+)"),
        ("add_reminder", r"\badd (?:a )?reminder (?:to )?(?P<task>.+)"),
        ("add_event", r"\b(?:add|create|schedule) (?:an? )?(?:event|meeting) (?P<title>.+)"),
    ]

    def execute(self, intent: Intent) -> ActionResult:
        if intent.action == "add_reminder":
            task = intent.params.get("task", "").strip()
            if not task:
                return ActionResult(False, "No reminder text understood.")

            due = _parse_time(task)
            clean_task = _strip_time_phrase(task) if due else task
            task_escaped = clean_task.replace('"', '\\"')

            if due:
                # AppleScript date format: "MM/DD/YYYY HH:MM:SS"
                due_str = due.strftime("%m/%d/%Y %H:%M:%S")
                script = (
                    f'tell application "Reminders"\n'
                    f'    make new reminder with properties {{name:"{task_escaped}", '
                    f'due date:date "{due_str}"}}\n'
                    f'end tell'
                )
                time_label = due.strftime("%-I:%M %p on %b %-d")
            else:
                script = f'tell application "Reminders" to make new reminder with properties {{name:"{task_escaped}"}}'
                time_label = None

            result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
            if result.returncode == 0:
                msg = f"Reminder set: '{clean_task}'" + (f" — due {time_label}." if time_label else ".")
                return ActionResult(True, msg)
            return ActionResult(False, f"Couldn't add reminder: {result.stderr.strip()}")

        if intent.action == "add_event":
            title = intent.params.get("title", "").strip()
            if not title:
                return ActionResult(False, "No event title understood.")
            title_escaped = title.replace('"', '\\"')
            script = (
                'tell application "Calendar"\n'
                '  tell calendar "Home"\n'
                f'    make new event with properties {{summary:"{title_escaped}", start date:(current date), '
                "end date:((current date) + 1 * hours)}\n"
                "  end tell\n"
                "end tell"
            )
            result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
            if result.returncode == 0:
                return ActionResult(True, f"Added event: {title} (defaults to now — edit the time in Calendar).")
            return ActionResult(False, f"Couldn't add event: {result.stderr.strip()}")

        return ActionResult(False, f"ECHO doesn't know how to '{intent.action}'.")
