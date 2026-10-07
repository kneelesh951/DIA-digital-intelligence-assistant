"""
agents/job_agent.py

HERALD — drafts and fills job applications from your saved profile
(profile/job_profile.yaml + resume), using Playwright for browser
automation. This is deliberately the most conservative agent in the app:

  - draft_application never touches a browser. It only generates text
    (a cover letter from your template + profile) for you to review.
  - fill_application opens a REAL, VISIBLE browser window (never
    headless) and does a best-effort autofill of common fields (name,
    email, phone, location) by matching form field labels/placeholders.
    It always stops before clicking submit.
  - submit_application only runs after the orchestrator's double
    confirmation, AND only if config.yaml agents[jobs].auto_submit is
    explicitly set to true. It is false by default. Flip it only if you
    understand a bad field match means a bad application actually goes
    out with no human check, and some job boards' terms of service
    prohibit automated submission.

Job application forms vary a lot between employers/ATS platforms
(Greenhouse, Lever, Workday, custom forms). Field matching here is
heuristic — it works well on common ATS platforms and will sometimes
miss fields on unusual ones. Always glance at the open browser window
before confirming submit.
"""

import string
from pathlib import Path

import yaml

from agents.base import Agent, Intent, ActionResult

# Resolve profile/template paths relative to the project root, regardless
# of what directory the app happens to be launched from.
PROJECT_ROOT = Path(__file__).resolve().parent.parent

FIELD_MATCHERS = {
    "full_name": ["full name", "your name", "name"],
    "email": ["email"],
    "phone": ["phone", "mobile", "telephone"],
    "location": ["location", "city", "address"],
}


class JobApplicationAgent(Agent):
    PATTERNS = [
        ("draft_application", r"\bdraft (?:a |an )?(?:job )?application (?:for )?(?P<job_title>.+?)(?: at (?P<company>.+))?$"),
        ("fill_application", r"\bfill (?:out |in )?(?:the )?application (?:at |for )?(?P<url>\S+)"),
        ("submit_application", r"\bsubmit (?:the )?application\b"),
    ]

    def __init__(self, agent_cfg, app_config):
        super().__init__(agent_cfg, app_config)
        self.auto_submit = agent_cfg.get("auto_submit", False)
        profile_path = PROJECT_ROOT / agent_cfg.get("profile_file", "profile/job_profile.yaml")
        self.profile = self._load_profile(profile_path)
        self._last_page = None  # holds the open Playwright page between fill -> submit

    def _load_profile(self, path: Path) -> dict:
        if not path.exists():
            return {}
        with open(path, "r") as f:
            return yaml.safe_load(f) or {}

    def describe_plan(self, intent: Intent) -> str:
        base = super().describe_plan(intent)
        if intent.action == "submit_application":
            status = "auto_submit is ON — this will actually click submit." if self.auto_submit else \
                     "auto_submit is OFF in config.yaml, so this will stop short of sending."
            return f"{base} — THIS SUBMITS A REAL APPLICATION. {status}"
        return base

    def execute(self, intent: Intent) -> ActionResult:
        if intent.action == "draft_application":
            return self._draft(intent.params)
        if intent.action == "fill_application":
            return self._fill(intent.params)
        if intent.action == "submit_application":
            return self._submit()
        return ActionResult(False, f"HERALD doesn't know how to '{intent.action}'.")

    def _draft(self, params: dict) -> ActionResult:
        job_title = params.get("job_title", "this role").strip()
        company = params.get("company", "the company").strip()

        # Ask VAULT to locate the resume file automatically via the AgentBus
        resume_path_str = self.profile.get("resume_path", "")
        if not resume_path_str or not (PROJECT_ROOT / resume_path_str).exists():
            vault_result = self.bus.call("files", "search_files", {"query": "resume"})
            if vault_result.success and vault_result.data.get("matches"):
                resume_path_str = vault_result.data["matches"][0]

        template_path = PROJECT_ROOT / self.profile.get("cover_letter_template_path", "profile/cover_letter_template.txt")
        raw_template = template_path.read_text() if template_path.exists() else (
            "Dear Hiring Team,\n\nI'm excited to apply for {job_title} at {company}.\n\n{full_name}\n{email}"
        )
        letter = string.Template(raw_template.replace("{", "${").replace("}", "}")).safe_substitute(
            job_title=job_title,
            company=company,
            full_name=self.profile.get("full_name", ""),
            email=self.profile.get("email", ""),
        )
        resume_note = f" Resume found at: {resume_path_str}." if resume_path_str else ""
        return ActionResult(
            True,
            f"Draft ready for {job_title} at {company}.{resume_note} Review it in the HUD before using it anywhere.",
            {"draft": letter, "resume": resume_path_str},
        )

    def _fill(self, params: dict) -> ActionResult:
        url = params.get("url", "").strip()
        if not url:
            return ActionResult(False, "No application URL understood.")
        if not url.startswith("http"):
            url = "https://" + url

        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            return ActionResult(
                False,
                "Playwright isn't installed. Run: pip install -r requirements.txt && playwright install chromium",
            )

        pw = sync_playwright().start()
        browser = pw.chromium.launch(headless=False)
        page = browser.new_page()
        page.goto(url, wait_until="domcontentloaded")

        filled = []
        for field_key, labels in FIELD_MATCHERS.items():
            value = self.profile.get(field_key, "")
            if not value:
                continue
            for label in labels:
                try:
                    locator = page.get_by_label(label, exact=False)
                    if locator.count() > 0:
                        locator.first.fill(value)
                        filled.append(field_key)
                        break
                    placeholder_locator = page.get_by_placeholder(label, exact=False)
                    if placeholder_locator.count() > 0:
                        placeholder_locator.first.fill(value)
                        filled.append(field_key)
                        break
                except Exception:
                    continue

        self._last_page = {"page": page, "browser": browser, "pw": pw, "url": url}
        return ActionResult(
            True,
            f"Opened {url} and filled {len(filled)} field(s): {', '.join(filled) or 'none matched automatically'}. "
            f"Review the form in the browser window before confirming submit.",
            {"filled_fields": filled, "url": url},
        )

    def _submit(self) -> ActionResult:
        if not self.auto_submit:
            return ActionResult(
                False,
                "auto_submit is OFF in config.yaml (agents > jobs > auto_submit). The application was "
                "filled but NOT sent — submit it yourself in the open browser window, or set "
                "auto_submit: true if you deliberately want HERALD to click submit on your behalf.",
            )
        if not self._last_page:
            return ActionResult(False, "No application is currently open/filled. Use fill_application first.")

        page = self._last_page["page"]
        url = self._last_page["url"]
        try:
            submit_button = page.get_by_role("button", name="submit", exact=False)
            if submit_button.count() == 0:
                submit_button = page.get_by_text("submit application", exact=False)
            if submit_button.count() == 0:
                return ActionResult(False, "Couldn't find a submit button automatically — please submit it manually.")
            submit_button.first.click()
            return ActionResult(True, f"Submitted application at {url}.")
        finally:
            self._last_page["browser"].close()
            self._last_page["pw"].stop()
            self._last_page = None
