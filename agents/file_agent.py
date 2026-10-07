"""
agents/file_agent.py

VAULT — finds, renames, moves, and organizes files. Hard-restricted to
the folders listed in config.yaml agents[files].allowed_paths — any
path outside that list is refused, no exceptions.

Voice patterns cover the two most common, low-risk actions (search,
organize). move_file/rename_file are still available in allowed_actions
for typed commands or a future UI form, since reliably parsing
"move X to Y" style source/destination pairs from speech is fragile.
"""

import shutil
from pathlib import Path

from agents.base import Agent, Intent, ActionResult


class FileAgent(Agent):
    PATTERNS = [
        ("organize_folder", r"\borganize (?:my )?(?P<folder>downloads|desktop|documents)\b"),
        ("search_files", r"\b(?:find|search for) files?\s*(?:named|called)?\s*(?P<query>.+)"),
    ]

    def __init__(self, agent_cfg, app_config):
        super().__init__(agent_cfg, app_config)
        self.allowed_paths = [Path(p).expanduser() for p in agent_cfg.get("allowed_paths", [])]

    def _is_allowed(self, path: Path) -> bool:
        path = path.expanduser().resolve()
        return any(str(path).startswith(str(root.expanduser().resolve())) for root in self.allowed_paths)

    def execute(self, intent: Intent) -> ActionResult:
        action = intent.action

        if action == "search_files":
            query = intent.params.get("query", "").strip()
            if not query:
                return ActionResult(False, "No search term understood.")
            matches = []
            for root in self.allowed_paths:
                if root.exists():
                    matches.extend(p for p in root.rglob(f"*{query}*") if p.is_file())
            if not matches:
                return ActionResult(True, f"No files matching '{query}' found in approved folders.")
            listing = "\n".join(str(p) for p in matches[:20])
            return ActionResult(
                True, f"Found {len(matches)} file(s) matching '{query}':\n{listing}",
                {"matches": [str(p) for p in matches]},
            )

        if action == "organize_folder":
            folder_name = intent.params.get("folder", "").strip().lower()
            root = Path.home() / folder_name.capitalize()
            if not root.exists() or not self._is_allowed(root):
                return ActionResult(False, f"'{folder_name}' isn't an approved/existing folder.")
            moved = 0
            for item in root.iterdir():
                if item.is_file() and item.suffix:
                    dest_dir = root / item.suffix.lstrip(".").upper()
                    dest_dir.mkdir(exist_ok=True)
                    shutil.move(str(item), str(dest_dir / item.name))
                    moved += 1
            return ActionResult(True, f"Organized {folder_name}: moved {moved} file(s) into type-based subfolders.")

        if action == "move_file":
            src = Path(intent.params.get("source", "")).expanduser()
            dest = Path(intent.params.get("destination", "")).expanduser()
            if not self._is_allowed(src) or not self._is_allowed(dest):
                return ActionResult(False, "Move refused: source or destination is outside approved folders.")
            if not src.exists():
                return ActionResult(False, f"Source file not found: {src}")
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dest))
            return ActionResult(True, f"Moved {src.name} to {dest}.")

        if action == "rename_file":
            src = Path(intent.params.get("source", "")).expanduser()
            new_name = intent.params.get("new_name", "")
            if not self._is_allowed(src):
                return ActionResult(False, "Rename refused: file is outside approved folders.")
            if not src.exists() or not new_name:
                return ActionResult(False, f"File not found or no new name given.")
            src.rename(src.with_name(new_name))
            return ActionResult(True, f"Renamed {src.name} to {new_name}.")

        return ActionResult(False, f"VAULT doesn't know how to '{action}'.")
