"""Tool definitions for Goodluck.

Each tool is a JSON schema (passed to Anthropic) plus a Python handler that
the runner invokes when Claude requests it. Handlers return JSON-serializable
dicts/lists which become the tool_result content.
"""
from __future__ import annotations

from typing import Any, Callable

from ..data import market, options, calendar as cal, news, reddit, screener
from ..data.indicators import compute_technicals


# ───────────────────────── tool handlers ─────────────────────────

def _t_screen_universe(_: dict) -> Any:
    return {
        "candidates": screener.screen_nasdaq_100(limit=15),
        "note": "Top 15 Nasdaq-100 names by composite score. Use these as your shortlist.",
    }


def _t_get_quote(args: dict) -> Any:
    return market.quote(args["ticker"].upper())


def _t_get_technicals(args: dict) -> Any:
    df = market.history(args["ticker"].upper())
    return compute_technicals(df)


def _t_get_options_snapshot(args: dict) -> Any:
    return options.snapshot(args["ticker"].upper())


def _t_validate_options_play(args: dict) -> Any:
    result = options.chain_summary_for_strike(
        args["ticker"].upper(),
        float(args["strike"]),
        side=args.get("side", "call"),
    )
    return result or {"error": "no chain data"}


def _t_get_catalysts(args: dict) -> Any:
    return cal.upcoming(args["ticker"].upper())


def _t_get_news(args: dict) -> Any:
    limit = int(args.get("limit", 10))
    items = news.combined(args["ticker"].upper(), limit=limit)
    return {"count": len(items), "items": items}


def _t_get_reddit_mentions(args: dict) -> Any:
    return reddit.mentions(args["ticker"].upper())


def _t_get_analyst_changes(args: dict) -> Any:
    rows = market.analyst_changes(args["ticker"].upper())
    return {"count": len(rows), "changes": rows}


def _t_get_market_context(_: dict) -> Any:
    return market.market_context()


# ───────────────────────── tool registry ─────────────────────────

TOOL_DEFINITIONS: list[dict] = [
    {
        "name": "get_market_context",
        "description": "Snapshot of SPY, QQQ, VIX, and the 11 SPDR sector ETFs. "
                       "Returns trend labels, % vs EMAs, VIX level, and a regime hint. "
                       "Call this FIRST every report.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "screen_universe",
        "description": "Pre-filtered top 15 Nasdaq-100 candidates by composite score "
                       "(volume surge + RSI band + EMA stack + short-term momentum). "
                       "Use this list as your shortlist — do NOT call other tools on "
                       "tickers outside this list.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_quote",
        "description": "Current price (15-min delayed), day % change, volume, 20-day "
                       "average volume, volume ratio, market cap, sector.",
        "input_schema": {
            "type": "object",
            "properties": {"ticker": {"type": "string", "description": "Stock ticker, e.g. NVDA"}},
            "required": ["ticker"],
        },
    },
    {
        "name": "get_technicals",
        "description": "20/50 EMA position, RSI(14), MACD line/signal/histogram, ATR(14), "
                       "ATR as % of price, 20- and 60-day support/resistance, trend strength label, "
                       "% from each EMA. Most important tool for the actual trade setup.",
        "input_schema": {
            "type": "object",
            "properties": {"ticker": {"type": "string"}},
            "required": ["ticker"],
        },
    },
    {
        "name": "get_options_snapshot",
        "description": "Nearest expiry options: ATM IV %, IV regime label, unusual flow "
                       "(volume/OI > 3) per strike and side, total put/call volume, put/call ratio, "
                       "max-pain strike.",
        "input_schema": {
            "type": "object",
            "properties": {"ticker": {"type": "string"}},
            "required": ["ticker"],
        },
    },
    {
        "name": "validate_options_play",
        "description": "Before suggesting an options play, validate it's liquid: bid/ask, "
                       "open interest, spread %, and a liquid_enough boolean (OI > 500 AND "
                       "spread < 10%).",
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string"},
                "strike": {"type": "number"},
                "side": {"type": "string", "enum": ["call", "put"], "default": "call"},
            },
            "required": ["ticker", "strike"],
        },
    },
    {
        "name": "get_catalysts",
        "description": "Next earnings date, days to earnings, ex-dividend date, and a "
                       "has_event_in_10d boolean.",
        "input_schema": {
            "type": "object",
            "properties": {"ticker": {"type": "string"}},
            "required": ["ticker"],
        },
    },
    {
        "name": "get_news",
        "description": "De-duplicated recent news from Yahoo Finance + Google News + Alpha Vantage. "
                       "Each item has title, url, source, published_at, sentiment.",
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string"},
                "limit": {"type": "integer", "default": 10},
            },
            "required": ["ticker"],
        },
    },
    {
        "name": "get_reddit_mentions",
        "description": "Hot Reddit posts (r/stocks, r/wallstreetbets, r/options) mentioning the "
                       "ticker in the last week. Returns counts, verdict, and individual posts "
                       "with score and sentiment.",
        "input_schema": {
            "type": "object",
            "properties": {"ticker": {"type": "string"}},
            "required": ["ticker"],
        },
    },
    {
        "name": "get_analyst_changes",
        "description": "Recent (last 30 days) analyst upgrades/downgrades and price target changes "
                       "from yfinance.",
        "input_schema": {
            "type": "object",
            "properties": {"ticker": {"type": "string"}},
            "required": ["ticker"],
        },
    },
]


TOOL_HANDLERS: dict[str, Callable[[dict], Any]] = {
    "get_market_context": _t_get_market_context,
    "screen_universe": _t_screen_universe,
    "get_quote": _t_get_quote,
    "get_technicals": _t_get_technicals,
    "get_options_snapshot": _t_get_options_snapshot,
    "validate_options_play": _t_validate_options_play,
    "get_catalysts": _t_get_catalysts,
    "get_news": _t_get_news,
    "get_reddit_mentions": _t_get_reddit_mentions,
    "get_analyst_changes": _t_get_analyst_changes,
}


def run_tool(name: str, args: dict) -> Any:
    """Invoke a tool by name. Returns a JSON-serializable result or an error dict."""
    handler = TOOL_HANDLERS.get(name)
    if handler is None:
        return {"error": f"unknown tool: {name}"}
    try:
        return handler(args or {})
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}
