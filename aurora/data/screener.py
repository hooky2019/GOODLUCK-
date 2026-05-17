"""Pre-filter the Nasdaq 100 down to ~15 candidates so the agent doesn't
tool-call all 100 names. Composite score on volume surge, RSI band, EMA position,
and momentum.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from ..universe import NASDAQ_100
from . import market
from .indicators import rsi, ema


def _score_one(symbol: str) -> dict | None:
    df = market.history(symbol)
    if df.empty or len(df) < 60:
        return None
    close = df["Close"]
    last = float(close.iloc[-1])
    e20 = float(ema(close, 20).iloc[-1])
    e50 = float(ema(close, 50).iloc[-1])
    vol = float(df["Volume"].iloc[-1])
    avg_vol = float(df["Volume"].tail(20).mean())
    vol_ratio = vol / avg_vol if avg_vol else 1.0
    r = float(rsi(close, 14).iloc[-1])
    ret_5d = float(close.iloc[-1] / close.iloc[-5] - 1) * 100 if len(close) >= 5 else 0.0
    ret_20d = float(close.iloc[-1] / close.iloc[-20] - 1) * 100 if len(close) >= 20 else 0.0

    # Composite — favor: volume surge, healthy RSI band, above EMA stack, fresh momentum
    score = 0.0
    if vol_ratio > 1.5:
        score += min((vol_ratio - 1.0) * 10, 25)
    if 50 <= r <= 70:
        score += 15
    elif 30 <= r < 50:
        score += 10  # potential mean-reversion / pullback
    elif r > 70:
        score += 5
    if last > e20 > e50:
        score += 20
    elif last < e20 < e50:
        score += 5  # short-side candidate; agent decides direction
    if 1 < ret_5d < 8:
        score += 10
    if -3 < ret_5d <= 1:
        score += 6  # pullback in a trend
    if abs(ret_20d) > 5:
        score += 5

    setup_hint = "neutral"
    if vol_ratio > 1.8 and last > e20 and ret_5d > 2:
        setup_hint = "breakout"
    elif last > e50 and -3 < ret_5d < 1 and r < 55:
        setup_hint = "pullback"
    elif r < 35 and last < e20:
        setup_hint = "mean-reversion"
    elif last > e20 > e50 and ret_5d > 1:
        setup_hint = "momentum continuation"

    return {
        "ticker": symbol,
        "score": round(score, 1),
        "setup_hint": setup_hint,
        "last_price": round(last, 2),
        "rsi14": round(r, 1),
        "vol_vs_avg": round(vol_ratio, 2),
        "ret_5d_pct": round(ret_5d, 2),
        "ret_20d_pct": round(ret_20d, 2),
        "ema_stack": "bullish" if last > e20 > e50 else "bearish" if last < e20 < e50 else "mixed",
    }


@st.cache_data(ttl=180, show_spinner=False)
def screen_nasdaq_100(limit: int = 15) -> list[dict]:
    """Return top-N candidates by composite score, both long-bias and short-bias."""
    results: list[dict] = []
    for symbol in NASDAQ_100:
        try:
            row = _score_one(symbol)
            if row is not None:
                results.append(row)
        except Exception:
            continue
    results.sort(key=lambda r: r["score"], reverse=True)
    return results[:limit]
