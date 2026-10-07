"""
agents/web_agent.py

SCOUT — web search, URL opening, and quick-answer lookups.
  search_web     opens a browser search (and returns a text summary if
                 called via the AgentBus from another agent).
  open_url       opens a URL in the default browser.
  quick_search   returns top-3 DuckDuckGo results as text (used by other
                 agents that need facts without opening a browser).
"""

import json
import urllib.parse
import urllib.request
import webbrowser
from urllib.parse import quote_plus

from agents.base import Agent, Intent, ActionResult


def _ddg_results(query: str, max_results: int = 3) -> list[dict]:
    """Fetch top results from DuckDuckGo Instant Answer API (no key needed)."""
    url = ("https://api.duckduckgo.com/?q=" + quote_plus(query)
           + "&format=json&no_redirect=1&no_html=1&skip_disambig=1")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=6) as r:
            data = json.loads(r.read().decode())
        results = []
        # Instant answer
        if data.get("AbstractText"):
            results.append({"title": data.get("Heading", query),
                             "snippet": data["AbstractText"][:200],
                             "url": data.get("AbstractURL", "")})
        # Related topics
        for topic in data.get("RelatedTopics", []):
            if isinstance(topic, dict) and topic.get("Text"):
                results.append({"title": topic.get("Text", "")[:60],
                                 "snippet": topic.get("Text", "")[:200],
                                 "url": topic.get("FirstURL", "")})
            if len(results) >= max_results:
                break
        return results
    except Exception:
        return []


class WebAgent(Agent):
    PATTERNS = [
        ("open_url",      r"\bopen (?:the )?(?:website|site|page)?\s*(?P<url>[\w\-]+\.\w{2,}(?:/\S*)?)"),
        ("search_web",    r"\bgoogle (?P<query>.+)"),
        ("search_web",    r"\bsearch (?:the web )?(?:for )?(?P<query>.+)"),
        ("quick_search",  r"\b(?:look up|lookup|find out|what is|who is|define)\s+(?P<query>.+)"),
    ]

    def execute(self, intent: Intent) -> ActionResult:
        if intent.action == "open_url":
            url = intent.params.get("url", "").strip()
            if not url:
                return ActionResult(False, "No URL understood.")
            if not url.startswith("http"):
                url = "https://" + url
            webbrowser.open(url)
            return ActionResult(True, f"Opened {url}.")

        if intent.action == "search_web":
            query = intent.params.get("query", "").strip()
            if not query:
                return ActionResult(False, "No search query understood.")
            # If called from the bus (another agent), return text results instead of opening browser
            if intent.raw_text == "[bus-call]":
                results = _ddg_results(query)
                if results:
                    summary = " | ".join(r["snippet"] for r in results)
                    return ActionResult(True, summary, {"results": results})
                return ActionResult(False, f"No results found for '{query}'.")
            url = f"https://www.google.com/search?q={quote_plus(query)}"
            webbrowser.open(url)
            return ActionResult(True, f"Searching the web for '{query}'.")

        if intent.action == "quick_search":
            query = intent.params.get("query", "").strip()
            if not query:
                return ActionResult(False, "No search query understood.")
            results = _ddg_results(query)
            if results:
                answer = results[0]["snippet"]
                return ActionResult(True, f"Here's what I found about {query}: {answer}",
                                    {"results": results})
            # Fall back to opening browser
            webbrowser.open(f"https://www.google.com/search?q={quote_plus(query)}")
            return ActionResult(True, f"Couldn't get a quick answer — opened a browser search for '{query}'.")

        return ActionResult(False, f"SCOUT doesn't know how to '{intent.action}'.")
