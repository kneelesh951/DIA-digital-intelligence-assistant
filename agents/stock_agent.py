"""
agents/stock_agent.py

QUANT — real-time stock market intelligence.

All data comes from Yahoo Finance (free, no API key).
Watchlist is persisted to ~/.dia_watchlist.json.

Actions:
  get_quote     — live price, change, day range for a stock or crypto
  get_market    — S&P 500 / NASDAQ / DOW overview
  get_movers    — top 5 day gainers + losers
  get_news      — latest headlines for a symbol
  watch_stock   — add a symbol to personal watchlist
  get_watchlist — check all watchlist stocks at once
  compare       — compare two stocks side-by-side
"""

import json
import urllib.request
from pathlib import Path

from agents.base import Agent, ActionResult, Intent

# ── constants ─────────────────────────────────────────────────────────────────

WATCHLIST_FILE = Path.home() / ".dia_watchlist.json"
_HDRS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
    "Accept": "application/json",
}
_INDICES = {
    "S&P 500": "^GSPC",
    "NASDAQ":  "^IXIC",
    "DOW":     "^DJI",
}

# Common company names → ticker symbols
_NAMES = {
    "apple": "AAPL", "microsoft": "MSFT", "google": "GOOGL", "alphabet": "GOOGL",
    "amazon": "AMZN", "tesla": "TSLA", "meta": "META", "facebook": "META",
    "nvidia": "NVDA", "netflix": "NFLX", "spotify": "SPOT", "uber": "UBER",
    "airbnb": "ABNB", "coinbase": "COIN", "intel": "INTC", "amd": "AMD",
    "salesforce": "CRM", "zoom": "ZM", "shopify": "SHOP", "palantir": "PLTR",
    "snowflake": "SNOW", "datadog": "DDOG", "mongodb": "MDB", "oracle": "ORCL",
    "adobe": "ADBE", "qualcomm": "QCOM", "broadcom": "AVGO", "arm": "ARM",
    "bitcoin": "BTC-USD", "btc": "BTC-USD", "ethereum": "ETH-USD", "eth": "ETH-USD",
    "solana": "SOL-USD", "dogecoin": "DOGE-USD", "ripple": "XRP-USD",
    "s&p": "^GSPC", "sp500": "^GSPC", "sp 500": "^GSPC",
    "nasdaq": "^IXIC", "dow": "^DJI", "dow jones": "^DJI",
}


# ── data helpers ──────────────────────────────────────────────────────────────

def _resolve(raw: str) -> str:
    """Map a company name or fuzzy string to a ticker symbol."""
    raw = raw.strip()
    low = raw.lower()
    for name, ticker in _NAMES.items():
        if name in low:
            return ticker
    # Strip filler words and uppercase what's left as a ticker guess
    for filler in ("stock", "share", "price", "crypto", "coin", "the", "of"):
        low = low.replace(filler, "")
    return low.strip().upper() or raw.upper()


def _fetch(url: str) -> dict:
    req = urllib.request.Request(url, headers=_HDRS)
    with urllib.request.urlopen(req, timeout=8) as r:
        return json.loads(r.read().decode())


def _quote(symbol: str) -> dict | None:
    """Single stock/crypto/index quote from Yahoo Finance v8."""
    try:
        d = _fetch(f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=1d")
        m = d["chart"]["result"][0]["meta"]
        price = float(m.get("regularMarketPrice", 0))
        prev  = float(m.get("chartPreviousClose") or m.get("previousClose") or price)
        chg   = price - prev
        pct   = (chg / prev * 100) if prev else 0
        vol   = m.get("regularMarketVolume", 0)
        hi    = float(m.get("regularMarketDayHigh") or 0)
        lo    = float(m.get("regularMarketDayLow") or 0)
        sym   = m.get("symbol", symbol).upper()
        name  = m.get("longName") or m.get("shortName") or sym
        return {
            "symbol": sym, "name": name,
            "price": round(price, 2), "change": round(chg, 2),
            "pct": round(pct, 2), "high": round(hi, 2), "low": round(lo, 2),
            "volume": vol, "currency": m.get("currency", "USD"),
            "state": m.get("marketState", "UNKNOWN"),
        }
    except Exception:
        return None


def _screener(scrid: str, count: int = 5) -> list[dict]:
    """Yahoo Finance predefined screener (day_gainers / day_losers)."""
    try:
        d = _fetch(
            f"https://query1.finance.yahoo.com/v1/finance/screener/predefined/saved"
            f"?scrIds={scrid}&count={count}&lang=en-US&region=US"
        )
        qs = d["finance"]["result"][0]["quotes"]
        return [{"sym": q["symbol"],
                 "pct": round(float(q.get("regularMarketChangePercent", 0)), 2),
                 "px":  round(float(q.get("regularMarketPrice", 0)), 2)} for q in qs]
    except Exception:
        return []


def _news(symbol: str, count: int = 3) -> list[str]:
    """Latest headlines from Yahoo Finance search."""
    try:
        d = _fetch(
            f"https://query1.finance.yahoo.com/v1/finance/search"
            f"?q={symbol}&newsCount={count}&enableNavLinks=false"
        )
        return [n["title"] for n in d.get("news", [])[:count]]
    except Exception:
        return []


def _load_watchlist() -> list[str]:
    if WATCHLIST_FILE.exists():
        try:
            return json.loads(WATCHLIST_FILE.read_text())
        except Exception:
            return []
    return []


def _save_watchlist(symbols: list[str]) -> None:
    deduped = list(dict.fromkeys(s.upper() for s in symbols if s.strip()))
    WATCHLIST_FILE.write_text(json.dumps(deduped))


def _fmt_price(q: dict) -> str:
    """'Apple $313.33 (+0.29%)' — spoken-friendly."""
    arrow = "up" if q["pct"] >= 0 else "down"
    return f"{q['name']} at {q['currency']} {q['price']}, {arrow} {abs(q['pct'])} percent"


# ── agent ─────────────────────────────────────────────────────────────────────

class StockAgent(Agent):
    PATTERNS = [
        # ── Most-specific first so broad get_quote doesn't shadow them ──────

        # Market overview  (check BEFORE quote — "market" must not fall to quote)
        ("get_market",
         r"\b(?:how\s+is|what\s+is|check)\s+(?:the\s+)?markets?\b"),
        ("get_market",
         r"\bmarkets?\s+(?:today|now|overview|update|status|open|close|doing)\b"),

        # Movers
        ("get_movers",
         r"\b(?:top|best|biggest|worst)\s+(?:gainers?|losers?|movers?|winners?|fallers?)\b"),
        ("get_movers",
         r"\b(?:who|what)\s+(?:is|are)\s+(?:moving|gaining|losing)\s+(?:today|most)?\b"),

        # News  (contains symbol — check before quote)
        ("get_news",
         r"\b(?:news|headlines?|updates?)\s+(?:for|about|on)\s+(?P<symbol>[\w\s&\.\-]+?)\s*$"),
        ("get_news",
         r"\bwhat.s\s+(?:happening|new)\s+(?:with|for)\s+(?P<symbol>[\w\s&\.\-]+?)\s*$"),

        # Watchlist read  (check before watch_stock so "check my watchlist" doesn't become watch)
        ("get_watchlist",
         r"\b(?:my\s+)?(?:watchlist|portfolio|watched\s+stocks?)\b"),
        ("get_watchlist",
         r"\b(?:show|check|see)\s+(?:my\s+)?(?:stocks?|watchlist|portfolio)\b"),

        # Add to watchlist
        ("watch_stock",
         r"\b(?:watch|track|add|follow|monitor)\s+(?P<symbol>[\w\s&\.\-]+?)\s*(?:to\s+(?:my\s+)?watchlist)?\s*$"),

        # Compare
        ("compare",
         r"\bcompare\s+(?P<symbol1>[\w\s&\.\-]+?)\s+(?:and|vs\.?|versus|with)\s+(?P<symbol2>[\w\s&\.\-]+?)\s*$"),

        # Quote  (broadest — must be last)
        ("get_quote",
         r"\b(?:how\s+is|quote\s+for|price\s+of|what\s+is|look\s+up|stock\s+price\s+of)\s+(?P<symbol>[\w\s&\.\-]+?)(?:\s+(?:doing|stock|share|price|worth|trading))?\s*$"),
        ("get_quote",
         r"\bcheck\s+(?P<symbol>(?!my\s+watchlist|the\s+market)[\w\s&\.\-]+?)(?:\s+(?:stock|price|share))?\s*$"),
        ("get_quote",
         r"\b(?P<symbol>[A-Z]{2,6}(?:-[A-Z]+)?)\s+(?:stock|share|price|quote)\b"),
    ]

    def describe_plan(self, intent: Intent) -> str:
        a = intent.action
        if a == "get_quote":
            sym = _resolve(intent.params.get("symbol", "?"))
            return f"Fetching live quote for {sym} from Yahoo Finance."
        if a == "get_market":
            return "Fetching S&P 500, NASDAQ, and DOW Jones live data."
        if a == "get_movers":
            return "Fetching today's top gainers and losers."
        if a == "get_news":
            sym = _resolve(intent.params.get("symbol", "?"))
            return f"Fetching latest news headlines for {sym}."
        if a == "watch_stock":
            sym = _resolve(intent.params.get("symbol", "?"))
            return f"Adding {sym} to your watchlist."
        if a == "get_watchlist":
            return "Checking your watchlist for live prices."
        if a == "compare":
            s1 = _resolve(intent.params.get("symbol1", "?"))
            s2 = _resolve(intent.params.get("symbol2", "?"))
            return f"Comparing {s1} vs {s2} live."
        return super().describe_plan(intent)

    def execute(self, intent: Intent) -> ActionResult:
        a = intent.action
        if a == "get_quote":    return self._get_quote(intent.params)
        if a == "get_market":   return self._get_market()
        if a == "get_movers":   return self._get_movers()
        if a == "get_news":     return self._get_news(intent.params)
        if a == "watch_stock":  return self._watch(intent.params)
        if a == "get_watchlist":return self._get_watchlist()
        if a == "compare":      return self._compare(intent.params)
        return ActionResult(False, f"QUANT doesn't know how to '{a}'.")

    # ── actions ───────────────────────────────────────────────────────────────

    def _get_quote(self, params: dict) -> ActionResult:
        raw = params.get("symbol", "").strip()
        if not raw:
            return ActionResult(False, "No stock symbol understood.")
        sym = _resolve(raw)
        q = _quote(sym)
        if not q:
            return ActionResult(False, f"Couldn't fetch data for '{sym}'. Check the symbol and try again.")

        # Spoken response
        arrow = "up" if q["pct"] >= 0 else "down"
        state = "" if q["state"] == "REGULAR" else f" Markets are currently {q['state'].lower()}."
        msg = (
            f"{q['name']} is trading at {q['currency']} {q['price']}, "
            f"{arrow} {abs(q['pct'])} percent today."
            f" Day range: {q['low']} to {q['high']}.{state}"
        )
        return ActionResult(True, msg, {"quote": q})

    def _get_market(self) -> ActionResult:
        results = []
        for name, sym in _INDICES.items():
            q = _quote(sym)
            if q:
                arrow = "up" if q["pct"] >= 0 else "down"
                results.append(f"{name} is {arrow} {abs(q['pct'])} percent at {q['price']}")

        if not results:
            return ActionResult(False, "Couldn't fetch market data right now.")
        msg = "Market update: " + ". ".join(results) + "."
        return ActionResult(True, msg, {"indices": results})

    def _get_movers(self) -> ActionResult:
        gainers = _screener("day_gainers", 5)
        losers  = _screener("day_losers",  5)
        if not gainers and not losers:
            return ActionResult(False, "Couldn't fetch market movers. Market may be closed.")

        g_str = ", ".join(f"{s['sym']} plus {s['pct']} percent" for s in gainers[:3])
        l_str = ", ".join(f"{s['sym']} minus {abs(s['pct'])} percent" for s in losers[:3])
        msg = f"Top gainers today: {g_str}. Top losers: {l_str}."
        return ActionResult(True, msg, {"gainers": gainers, "losers": losers})

    def _get_news(self, params: dict) -> ActionResult:
        raw = params.get("symbol", "").strip()
        if not raw:
            return ActionResult(False, "No symbol understood for news lookup.")
        sym = _resolve(raw)
        headlines = _news(sym, 3)
        if not headlines:
            return ActionResult(False, f"No recent news found for {sym}.")
        numbered = " ".join(f"{i+1}: {h}." for i, h in enumerate(headlines))
        msg = f"Latest news for {sym}: {numbered}"
        return ActionResult(True, msg, {"headlines": headlines, "symbol": sym})

    def _watch(self, params: dict) -> ActionResult:
        raw = params.get("symbol", "").strip()
        if not raw:
            return ActionResult(False, "No symbol understood.")
        sym = _resolve(raw)
        # Verify it's a real symbol before adding
        q = _quote(sym)
        if not q:
            return ActionResult(False, f"'{sym}' doesn't look like a valid symbol — couldn't fetch a quote for it.")
        wl = _load_watchlist()
        if sym in wl:
            return ActionResult(True, f"{q['name']} is already in your watchlist.")
        wl.append(sym)
        _save_watchlist(wl)
        return ActionResult(True, f"Added {q['name']} ({sym}) to your watchlist. You now have {len(wl)} stock{'s' if len(wl)>1 else ''} tracked.")

    def _get_watchlist(self) -> ActionResult:
        wl = _load_watchlist()
        if not wl:
            return ActionResult(True, "Your watchlist is empty. Say 'watch Apple' or 'watch NVDA' to add stocks.")
        quotes = []
        for sym in wl:
            q = _quote(sym)
            if q:
                quotes.append(q)

        if not quotes:
            return ActionResult(False, "Couldn't fetch prices for your watchlist right now.")

        parts = []
        for q in quotes:
            arrow = "up" if q["pct"] >= 0 else "down"
            parts.append(f"{q['name']} {arrow} {abs(q['pct'])} percent at {q['price']}")

        msg = f"Your {len(quotes)} watched stocks: " + ", ".join(parts) + "."
        return ActionResult(True, msg, {"watchlist": quotes})

    def _compare(self, params: dict) -> ActionResult:
        s1 = _resolve(params.get("symbol1", ""))
        s2 = _resolve(params.get("symbol2", ""))
        if not s1 or not s2:
            return ActionResult(False, "Couldn't parse two symbols to compare.")
        q1, q2 = _quote(s1), _quote(s2)
        if not q1 or not q2:
            missing = s1 if not q1 else s2
            return ActionResult(False, f"Couldn't fetch data for '{missing}'.")

        def _side(q):
            arrow = "up" if q["pct"] >= 0 else "down"
            return f"{q['name']}: {q['currency']} {q['price']}, {arrow} {abs(q['pct'])} percent"

        winner = q1["name"] if q1["pct"] > q2["pct"] else q2["name"]
        msg = f"Comparison: {_side(q1)}. Versus: {_side(q2)}. {winner} is outperforming today."
        return ActionResult(True, msg, {"q1": q1, "q2": q2})
