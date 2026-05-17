"""News aggregator: Yahoo Finance + Google News RSS + Alpha Vantage."""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import datetime
from email.utils import parsedate_to_datetime

import requests
import streamlit as st
import yfinance as yf

from ..config import ALPHA_VANTAGE_KEY


POSITIVE_WORDS = {
    "beats", "beat", "exceeds", "surges", "surge", "record", "strong", "growth",
    "rally", "upgrade", "bullish", "gains", "profit", "buyback", "positive",
    "raises", "raised", "outperform", "launch", "deal", "partnership", "approval",
}
NEGATIVE_WORDS = {
    "miss", "missed", "below", "weak", "decline", "downgrade", "bearish", "loss",
    "warns", "cut", "cuts", "layoffs", "investigation", "fall", "drops", "slumps",
    "disappoints", "penalty", "fine", "recall", "delisted", "fraud", "lawsuit",
}


def _sentiment(text: str) -> str:
    t = text.lower()
    pos = sum(1 for w in POSITIVE_WORDS if w in t)
    neg = sum(1 for w in NEGATIVE_WORDS if w in t)
    if pos > neg:
        return "positive"
    if neg > pos:
        return "negative"
    return "neutral"


def _strip_html(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&[a-z]+;", " ", text)
    return re.sub(r"\s+", " ", text).strip()


@st.cache_data(ttl=600, show_spinner=False)
def yahoo(symbol: str) -> list[dict]:
    try:
        items = yf.Ticker(symbol).news[:10] or []
    except Exception:
        return []
    out = []
    for it in items:
        title = it.get("title", "")
        ts = it.get("providerPublishTime", 0)
        out.append({
            "title": title,
            "url": it.get("link", ""),
            "source": it.get("publisher", "Yahoo Finance"),
            "published_at": datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M") if ts else "",
            "sentiment": _sentiment(title),
            "provider": "yahoo",
        })
    return out


@st.cache_data(ttl=600, show_spinner=False)
def google(symbol: str) -> list[dict]:
    try:
        url = f"https://news.google.com/rss/search?q={symbol}+stock+news&hl=en-US&gl=US&ceid=US:en"
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=8)
        if r.status_code != 200:
            return []
        root = ET.fromstring(r.content)
        channel = root.find("channel")
        if channel is None:
            return []
        out = []
        for item in channel.findall("item")[:12]:
            title = item.findtext("title", "")
            link = item.findtext("link", "")
            pub = item.findtext("pubDate", "")
            desc = _strip_html(item.findtext("description", ""))
            src_el = item.find("source")
            src = src_el.text if src_el is not None else "Google News"
            try:
                dt_str = parsedate_to_datetime(pub).strftime("%Y-%m-%d %H:%M")
            except Exception:
                dt_str = pub[:16]
            text = title + " " + desc
            out.append({
                "title": title,
                "url": link,
                "source": src,
                "published_at": dt_str,
                "summary": desc[:240] if desc else "",
                "sentiment": _sentiment(text),
                "provider": "google",
            })
        return out
    except Exception:
        return []


@st.cache_data(ttl=900, show_spinner=False)
def alpha_vantage(symbol: str) -> list[dict]:
    if not ALPHA_VANTAGE_KEY:
        return []
    try:
        url = (
            f"https://www.alphavantage.co/query"
            f"?function=NEWS_SENTIMENT&tickers={symbol}"
            f"&apikey={ALPHA_VANTAGE_KEY}&limit=15&sort=LATEST"
        )
        r = requests.get(url, timeout=10)
        if r.status_code != 200:
            return []
        feed = r.json().get("feed", [])
        out = []
        for it in feed[:12]:
            title = it.get("title", "")
            raw_t = it.get("time_published", "")
            try:
                dt_str = datetime.strptime(raw_t, "%Y%m%dT%H%M%S").strftime("%Y-%m-%d %H:%M")
            except Exception:
                dt_str = raw_t[:10]
            label = it.get("overall_sentiment_label", "Neutral")
            sent = "positive" if "Bullish" in label else "negative" if "Bearish" in label else "neutral"
            out.append({
                "title": title,
                "url": it.get("url", ""),
                "source": it.get("source", "Alpha Vantage"),
                "published_at": dt_str,
                "summary": it.get("summary", "")[:240],
                "sentiment": sent,
                "provider": "alphavantage",
            })
        return out
    except Exception:
        return []


@st.cache_data(ttl=600, show_spinner=False)
def combined(symbol: str, limit: int = 15) -> list[dict]:
    """De-duplicated headlines from all 3 sources, newest first."""
    out: list[dict] = []
    seen: set[str] = set()
    for source in (yahoo, google, alpha_vantage):
        for item in source(symbol):
            key = item["title"][:40].lower().strip()
            if key and key not in seen:
                seen.add(key)
                out.append(item)
    out.sort(key=lambda x: x.get("published_at", ""), reverse=True)
    return out[:limit]
