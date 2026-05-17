"""Price, OHLCV, and broad-market context fetchers."""
from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd
import streamlit as st
import yfinance as yf
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from . import indicators


_RETRY = dict(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    retry=retry_if_exception_type(Exception),
    reraise=False,
)


@retry(**_RETRY)
def _ticker_history(symbol: str, period: str, interval: str = "1d") -> pd.DataFrame:
    return yf.Ticker(symbol).history(period=period, interval=interval, auto_adjust=True)


@st.cache_data(ttl=300, show_spinner=False)
def history(symbol: str, period: str = "6mo") -> pd.DataFrame:
    """Daily OHLCV. 5-minute TTL."""
    try:
        df = _ticker_history(symbol, period)
        return df if df is not None and not df.empty else pd.DataFrame()
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=60, show_spinner=False)
def quote(symbol: str) -> dict:
    """Last price, % change, volume vs 20-day average, market cap."""
    df = history(symbol)
    if df.empty:
        return {"error": f"no data for {symbol}"}
    last = float(df["Close"].iloc[-1])
    prev = float(df["Close"].iloc[-2]) if len(df) > 1 else last
    vol = float(df["Volume"].iloc[-1])
    avg_vol = float(df["Volume"].tail(20).mean()) if len(df) >= 20 else vol
    info = _safe_info(symbol)
    return {
        "symbol": symbol,
        "last_price": round(last, 2),
        "prev_close": round(prev, 2),
        "day_change_pct": round((last / prev - 1) * 100, 2) if prev else 0.0,
        "volume": int(vol),
        "avg_vol_20d": int(avg_vol),
        "volume_vs_avg": round(vol / avg_vol, 2) if avg_vol else 1.0,
        "market_cap": info.get("marketCap"),
        "sector": info.get("sector"),
        "industry": info.get("industry"),
        "short_name": info.get("shortName", symbol),
    }


@st.cache_data(ttl=600, show_spinner=False)
def _safe_info(symbol: str) -> dict:
    try:
        return yf.Ticker(symbol).info or {}
    except Exception:
        return {}


_SECTOR_ETFS = {
    "XLK": "Technology",
    "XLF": "Financials",
    "XLE": "Energy",
    "XLV": "Healthcare",
    "XLY": "Consumer Discretionary",
    "XLP": "Consumer Staples",
    "XLI": "Industrials",
    "XLU": "Utilities",
    "XLB": "Materials",
    "XLRE": "Real Estate",
    "XLC": "Communication Services",
}


def _trend_summary(df: pd.DataFrame) -> dict:
    if df.empty or len(df) < 50:
        return {"price": None, "vs_ema50_pct": None, "vs_ema20_pct": None, "label": "unknown"}
    close = df["Close"]
    last = float(close.iloc[-1])
    e20 = float(close.ewm(span=20).mean().iloc[-1])
    e50 = float(close.ewm(span=50).mean().iloc[-1])
    if last > e20 > e50:
        label = "uptrend"
    elif last < e20 < e50:
        label = "downtrend"
    else:
        label = "choppy"
    return {
        "price": round(last, 2),
        "vs_ema20_pct": round((last / e20 - 1) * 100, 2),
        "vs_ema50_pct": round((last / e50 - 1) * 100, 2),
        "label": label,
    }


@st.cache_data(ttl=120, show_spinner=False)
def market_context() -> dict:
    """SPY/QQQ trend, VIX, sector ETF performance, regime hint."""
    spy = _trend_summary(history("SPY", period="3mo"))
    qqq = _trend_summary(history("QQQ", period="3mo"))

    vix_df = history("^VIX", period="1mo")
    if not vix_df.empty:
        vix = float(vix_df["Close"].iloc[-1])
        vix_prev = float(vix_df["Close"].iloc[-2]) if len(vix_df) > 1 else vix
        vix_chg = round((vix / vix_prev - 1) * 100, 2) if vix_prev else 0.0
    else:
        vix = None
        vix_chg = None

    sector_perf = {}
    for etf, name in _SECTOR_ETFS.items():
        df = history(etf, period="1mo")
        if df.empty or len(df) < 5:
            continue
        last = float(df["Close"].iloc[-1])
        five = float(df["Close"].iloc[-5])
        twenty = float(df["Close"].iloc[0])
        sector_perf[etf] = {
            "name": name,
            "pct_5d": round((last / five - 1) * 100, 2),
            "pct_1m": round((last / twenty - 1) * 100, 2),
        }

    if vix is not None:
        if vix > 25 or (spy["label"] == "downtrend" and qqq["label"] == "downtrend"):
            regime = "risk-off"
        elif vix < 18 and qqq["label"] == "uptrend":
            regime = "risk-on"
        else:
            regime = "chop"
    else:
        regime = "unknown"

    return {
        "spy": spy,
        "qqq": qqq,
        "vix": round(vix, 2) if vix is not None else None,
        "vix_pct_change": vix_chg,
        "sector_perf": sector_perf,
        "regime_hint": regime,
    }


@st.cache_data(ttl=21600, show_spinner=False)
def analyst_changes(symbol: str) -> list[dict]:
    """Recent upgrades/downgrades from yfinance (last 30 days)."""
    try:
        t = yf.Ticker(symbol)
        df = t.upgrades_downgrades
        if df is None or df.empty:
            return []
        df = df.reset_index()
        cutoff = pd.Timestamp.now(tz=df["GradeDate"].dt.tz) - pd.Timedelta(days=30)
        df = df[df["GradeDate"] >= cutoff]
        rows = []
        for _, r in df.head(8).iterrows():
            rows.append({
                "firm": r.get("Firm", ""),
                "action": r.get("Action", ""),
                "from_grade": r.get("FromGrade", ""),
                "to_grade": r.get("ToGrade", ""),
                "date": r["GradeDate"].strftime("%Y-%m-%d") if pd.notna(r.get("GradeDate")) else "",
            })
        return rows
    except Exception:
        return []
