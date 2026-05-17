"""Reddit mentions via the public search JSON endpoint — no auth needed.

Same method as nasdaq_dashboard/app.py.
"""
from __future__ import annotations

from datetime import datetime, timezone

import requests
import streamlit as st

from .news import POSITIVE_WORDS, NEGATIVE_WORDS


SUBS = ["stocks", "wallstreetbets", "options", "investing"]
HEADERS = {"User-Agent": "lucky-aurora/0.1 (swing-trade dashboard)"}


def _sentiment(text: str) -> str:
    t = text.lower()
    pos = sum(1 for w in POSITIVE_WORDS if w in t)
    neg = sum(1 for w in NEGATIVE_WORDS if w in t)
    if pos > neg:
        return "positive"
    if neg > pos:
        return "negative"
    return "neutral"


@st.cache_data(ttl=900, show_spinner=False)
def mentions(symbol: str, max_subs: int = 3) -> dict:
    """Hot posts mentioning the ticker across major sub-reddits."""
    posts: list[dict] = []
    now = datetime.now(timezone.utc)
    try:
        for sub in SUBS[:max_subs]:
            url = (
                f"https://www.reddit.com/r/{sub}/search.json"
                f"?q={symbol}&sort=hot&limit=5&t=week&restrict_sr=1"
            )
            r = requests.get(url, headers=HEADERS, timeout=6)
            if r.status_code != 200:
                continue
            for child in r.json().get("data", {}).get("children", []):
                p = child.get("data", {})
                title = p.get("title", "")
                ts = p.get("created_utc", 0)
                age_hours = round((now.timestamp() - ts) / 3600, 1) if ts else None
                posts.append({
                    "title": title[:140],
                    "subreddit": f"r/{p.get('subreddit', sub)}",
                    "score": int(p.get("score", 0) or 0),
                    "comments": int(p.get("num_comments", 0) or 0),
                    "age_hours": age_hours,
                    "url": f"https://reddit.com{p.get('permalink', '')}",
                    "sentiment": _sentiment(title),
                })
    except Exception:
        pass

    posts.sort(key=lambda x: x.get("score", 0), reverse=True)
    posts = posts[:8]

    pos = sum(1 for p in posts if p["sentiment"] == "positive")
    neg = sum(1 for p in posts if p["sentiment"] == "negative")
    total = len(posts)
    if total == 0:
        verdict = "no chatter"
    elif total > 5 and pos > neg * 2:
        verdict = "loud bullish chatter — crowded long, beware"
    elif total > 5 and neg > pos * 2:
        verdict = "loud bearish chatter"
    elif pos > neg:
        verdict = "leaning bullish"
    elif neg > pos:
        verdict = "leaning bearish"
    else:
        verdict = "mixed / neutral"

    return {
        "count": total,
        "positive": pos,
        "negative": neg,
        "verdict": verdict,
        "posts": posts,
    }
