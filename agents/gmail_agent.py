"""
agents/gmail_agent.py

HERMES — reads Gmail via IMAP. Read-only, no confirmation required.

Setup (one-time):
  1. Gmail settings → See all settings → Forwarding and POP/IMAP → Enable IMAP → Save
  2. Google Account → Security → 2-Step Verification → App passwords
     → Select app: Mail, Select device: Mac → Generate
  3. Add to .env:  GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx
     (your Gmail address is already in config.yaml → user_profile.email)

Triggers (rule-based fallback):
  "check my email", "any new emails", "what's in my inbox"  → check_inbox
  "read my latest email", "what does my last email say"     → read_latest
"""

import email as _email_lib
import imaplib
import os
import re
import textwrap
from email.header import decode_header
from email.utils import parseaddr, parsedate_to_datetime

from agents.base import Agent, ActionResult, Intent

_IMAP_HOST = "imap.gmail.com"
_IMAP_PORT = 993


def _decode_str(value: str | bytes, charset: str | None = None) -> str:
    if isinstance(value, bytes):
        return value.decode(charset or "utf-8", errors="replace")
    return value


def _decode_header_field(raw: str) -> str:
    parts = decode_header(raw)
    return "".join(_decode_str(part, enc) for part, enc in parts)


def _plain_body(msg) -> str:
    """Extract plain-text body from an email.Message, preferring text/plain."""
    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            cd = str(part.get("Content-Disposition", ""))
            if ct == "text/plain" and "attachment" not in cd:
                payload = part.get_payload(decode=True)
                charset = part.get_content_charset() or "utf-8"
                return _decode_str(payload, charset).strip()
        # Fall back to text/html, strip tags
        for part in msg.walk():
            if part.get_content_type() == "text/html":
                payload = part.get_payload(decode=True)
                charset = part.get_content_charset() or "utf-8"
                html = _decode_str(payload, charset)
                return re.sub(r"<[^>]+>", " ", html).strip()
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or "utf-8"
            return _decode_str(payload, charset).strip()
    return ""


def _connect(email_addr: str, app_password: str) -> imaplib.IMAP4_SSL:
    conn = imaplib.IMAP4_SSL(_IMAP_HOST, _IMAP_PORT)
    conn.login(email_addr, app_password)
    return conn


def _fetch_messages(conn: imaplib.IMAP4_SSL, count: int = 5, unread_only: bool = False):
    conn.select("INBOX", readonly=True)
    criterion = "UNSEEN" if unread_only else "ALL"
    _, data = conn.search(None, criterion)
    ids = data[0].split()
    if not ids:
        return []
    recent_ids = ids[-count:][::-1]  # newest first
    messages = []
    for uid in recent_ids:
        _, raw = conn.fetch(uid, "(RFC822)")
        msg = _email_lib.message_from_bytes(raw[0][1])
        subject = _decode_header_field(msg.get("Subject", "(no subject)"))
        _, sender = parseaddr(_decode_header_field(msg.get("From", "")))
        date_raw = msg.get("Date", "")
        try:
            dt = parsedate_to_datetime(date_raw)
            date_str = dt.strftime("%-d %b, %-I:%M %p")
        except Exception:
            date_str = date_raw[:16]
        messages.append({
            "subject": subject.strip(),
            "from": sender.strip(),
            "date": date_str,
            "body": _plain_body(msg),
        })
    return messages


class GmailAgent(Agent):
    PATTERNS = [
        ("check_inbox",
         r"(check|show|any|got|have\s+i\s+got)\s+(my\s+)?(new\s+)?(email|emails|mail|inbox|messages?)"),
        ("check_inbox",
         r"(what'?s?\s+in|look\s+at)\s+(my\s+)?(inbox|email|mail)"),
        ("check_inbox",
         r"(do\s+i\s+have|are\s+there)\s+(any\s+)?(new\s+)?(emails?|messages?)"),
        ("read_latest",
         r"(read|open|show\s+me|what\s+does?)\s+(my\s+)?(latest|last|most\s+recent|newest)\s+(email|message|mail)"),
        ("read_latest",
         r"(what\s+(is|does?)\s+(my\s+)?latest|read\s+latest)\s+(email|message|mail)"),
    ]

    def _creds(self):
        email_addr = self.app_config.get("user_profile", {}).get("email", "")
        app_password = os.environ.get("GMAIL_APP_PASSWORD", "").replace(" ", "")
        if not email_addr:
            raise RuntimeError("user_profile.email is not set in config.yaml.")
        if not app_password:
            raise RuntimeError(
                "GMAIL_APP_PASSWORD is not set in .env. "
                "Generate one at Google Account → Security → 2-Step Verification → App passwords."
            )
        return email_addr, app_password

    def describe_plan(self, intent: Intent) -> str:
        return "HERMES will connect to your Gmail inbox and fetch recent messages."

    def execute(self, intent: Intent) -> ActionResult:
        try:
            email_addr, app_password = self._creds()
        except RuntimeError as e:
            return ActionResult(False, str(e))

        try:
            conn = _connect(email_addr, app_password)
        except imaplib.IMAP4.error as e:
            return ActionResult(False,
                f"Could not log in to Gmail. Double-check your App Password. ({e})")
        except Exception as e:
            return ActionResult(False, f"Connection error: {e}")

        try:
            if intent.action == "check_inbox":
                msgs = _fetch_messages(conn, count=5)
                if not msgs:
                    return ActionResult(True, "Your inbox is empty.")
                lines = []
                for i, m in enumerate(msgs, 1):
                    lines.append(f"{i}. From {m['from']} — {m['subject']} ({m['date']})")
                summary = "Here are your latest emails: " + ". ".join(lines) + "."
                return ActionResult(True, summary, {"emails": msgs})

            if intent.action == "read_latest":
                msgs = _fetch_messages(conn, count=1)
                if not msgs:
                    return ActionResult(True, "Your inbox is empty.")
                m = msgs[0]
                body = m["body"]
                # Trim very long bodies to something speakable
                snippet = textwrap.shorten(body, width=400, placeholder="…") if body else "(no body)"
                reply = (
                    f"Latest email from {m['from']}, received {m['date']}. "
                    f"Subject: {m['subject']}. "
                    f"Message: {snippet}"
                )
                return ActionResult(True, reply, {"email": m})

        except Exception as e:
            return ActionResult(False, f"Error reading Gmail: {e}")
        finally:
            try:
                conn.logout()
            except Exception:
                pass

        return ActionResult(False, f"HERMES doesn't know how to '{intent.action}'.")
