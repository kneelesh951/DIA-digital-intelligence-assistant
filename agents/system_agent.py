"""
agents/system_agent.py

SENTRY — basic Mac system control: open/quit apps, volume, screenshots,
lock screen. Shells out to macOS's own `open`, `osascript`, and
`screencapture` — no special permissions beyond what those normally need.
"""

import subprocess
from pathlib import Path

from agents.base import Agent, Intent, ActionResult


class SystemAgent(Agent):
    PATTERNS = [
        ("open_app", r"\blaunch (?P<app>[\w\s]+)"),
        ("quit_app", r"\b(?:quit|close) (?:the )?(?:app(?:lication)? )?(?P<app>[\w\s]+)"),
        ("set_volume", r"\b(?:set )?volume (?:to )?(?P<level>\d{1,3})\b"),
        ("take_screenshot", r"\b(?:take a )?screenshot\b"),
        ("lock_screen", r"\block (?:the )?(?:screen|mac|computer)\b"),
        ("open_app", r"\bopen (?:the )?(?:app(?:lication)? )?(?P<app>[\w\s]+)"),
    ]

    def execute(self, intent: Intent) -> ActionResult:
        action = intent.action
        params = intent.params

        if action == "open_app":
            app = params.get("app", "").strip()
            if not app:
                return ActionResult(False, "No app name understood.")
            result = subprocess.run(["open", "-a", app], capture_output=True, text=True)
            if result.returncode == 0:
                return ActionResult(True, f"Opened {app}.")
            return ActionResult(False, f"Couldn't open '{app}': {result.stderr.strip()}")

        if action == "quit_app":
            app = params.get("app", "").strip()
            if not app:
                return ActionResult(False, "No app name understood.")
            script = f'tell application "{app}" to quit'
            result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
            if result.returncode == 0:
                return ActionResult(True, f"Quit {app}.")
            return ActionResult(False, f"Couldn't quit '{app}': {result.stderr.strip()}")

        if action == "set_volume":
            try:
                level = max(0, min(100, int(params.get("level", "50"))))
            except ValueError:
                return ActionResult(False, "Couldn't understand the volume level.")
            subprocess.run(["osascript", "-e", f"set volume output volume {level}"], capture_output=True, text=True)
            return ActionResult(True, f"Volume set to {level}.")

        if action == "take_screenshot":
            out_path = Path.home() / "Desktop" / "ARIA_screenshot.png"
            result = subprocess.run(["screencapture", str(out_path)], capture_output=True, text=True)
            if result.returncode == 0:
                return ActionResult(True, f"Screenshot saved to {out_path}.", {"path": str(out_path)})
            return ActionResult(False, f"Screenshot failed: {result.stderr.strip()}")

        if action == "lock_screen":
            subprocess.run(
                [
                    "osascript", "-e",
                    'tell application "System Events" to keystroke "q" using {control down, command down}',
                ],
                capture_output=True, text=True,
            )
            return ActionResult(True, "Locking the screen.")

        return ActionResult(False, f"SENTRY doesn't know how to '{action}'.")
