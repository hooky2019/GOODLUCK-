"""Options chain analytics: IV regime, unusual flow, put/call ratio, max pain."""
from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd
import streamlit as st
import yfinance as yf

from .market import history


@st.cache_data(ttl=300, show_spinner=False)
def _chain(symbol: str) -> Optional[dict]:
    try:
        t = yf.Ticker(symbol)
        exps = t.options
        if not exps:
            return None
        expiry = exps[0]
        chain = t.option_chain(expiry)
        return {
            "expiry": expiry,
            "calls": chain.calls.to_dict("records"),
            "puts": chain.puts.to_dict("records"),
        }
    except Exception:
        return None


def _max_pain(calls: pd.DataFrame, puts: pd.DataFrame) -> Optional[float]:
    """Strike where total dollar pain to option holders is maximized (where market makers profit most)."""
    if calls.empty and puts.empty:
        return None
    strikes = sorted(set(calls.get("strike", pd.Series()).tolist()) | set(puts.get("strike", pd.Series()).tolist()))
    if not strikes:
        return None
    pain = []
    for k in strikes:
        call_pain = ((np.maximum(calls["strike"] - k, 0) * calls.get("openInterest", 0)).sum()
                     if not calls.empty else 0)
        put_pain = ((np.maximum(k - puts["strike"], 0) * puts.get("openInterest", 0)).sum()
                    if not puts.empty else 0)
        pain.append((k, call_pain + put_pain))
    return float(min(pain, key=lambda x: x[1])[0])


@st.cache_data(ttl=300, show_spinner=False)
def snapshot(symbol: str) -> dict:
    """One-stop options view: ATM IV, IV regime, unusual flow, P/C ratio, max pain."""
    raw = _chain(symbol)
    if not raw:
        return {"error": "no options data"}

    calls = pd.DataFrame(raw["calls"])
    puts = pd.DataFrame(raw["puts"])

    hist = history(symbol)
    if hist.empty:
        return {"error": "no price history for IV comparison"}

    price = float(hist["Close"].iloc[-1])

    # ATM IV and regime
    iv_label = "unknown"
    atm_iv = None
    if not calls.empty and "impliedVolatility" in calls.columns:
        c = calls.dropna(subset=["impliedVolatility", "strike"])
        if not c.empty:
            idx = (c["strike"] - price).abs().idxmin()
            atm_iv = float(c.loc[idx, "impliedVolatility"])
            hv = float(hist["Close"].pct_change().tail(30).std() * np.sqrt(252))
            if hv > 0:
                ratio = atm_iv / hv
                if ratio > 1.3:
                    iv_label = "elevated (IV > realized vol)"
                elif ratio > 0.9:
                    iv_label = "stable (IV near realized)"
                else:
                    iv_label = "cheap (IV below realized)"

    # Unusual flow: vol/oi > 3
    unusual = []
    for side, df in [("call", calls), ("put", puts)]:
        if df.empty or "volume" not in df.columns or "openInterest" not in df.columns:
            continue
        d = df.dropna(subset=["volume", "openInterest"])
        d = d[d["openInterest"] > 0]
        d = d.assign(ratio=d["volume"] / d["openInterest"])
        for _, row in d[d["ratio"] > 3].head(5).iterrows():
            unusual.append({
                "side": side,
                "strike": float(row["strike"]),
                "volume": int(row["volume"]),
                "open_interest": int(row["openInterest"]),
                "ratio": round(float(row["ratio"]), 2),
            })

    # Put/Call ratio
    call_vol = int(calls["volume"].fillna(0).sum()) if "volume" in calls else 0
    put_vol = int(puts["volume"].fillna(0).sum()) if "volume" in puts else 0
    pc_ratio = round(put_vol / call_vol, 2) if call_vol else None

    return {
        "expiry": raw["expiry"],
        "atm_iv_pct": round(atm_iv * 100, 1) if atm_iv else None,
        "iv_label": iv_label,
        "unusual_flow": unusual,
        "unusual_count": len(unusual),
        "put_call_ratio": pc_ratio,
        "max_pain": _max_pain(calls, puts),
        "total_call_volume": call_vol,
        "total_put_volume": put_vol,
    }


@st.cache_data(ttl=300, show_spinner=False)
def chain_summary_for_strike(symbol: str, strike: float, side: str = "call") -> Optional[dict]:
    """Liquidity/bid-ask info for a specific strike to validate options play suggestions."""
    raw = _chain(symbol)
    if not raw:
        return None
    df = pd.DataFrame(raw["calls"] if side == "call" else raw["puts"])
    if df.empty:
        return None
    row = df.iloc[(df["strike"] - strike).abs().idxmin()]
    bid = float(row.get("bid", 0) or 0)
    ask = float(row.get("ask", 0) or 0)
    mid = (bid + ask) / 2 if (bid and ask) else None
    spread_pct = round((ask - bid) / mid * 100, 1) if mid else None
    return {
        "expiry": raw["expiry"],
        "strike": float(row["strike"]),
        "bid": bid,
        "ask": ask,
        "mid": round(mid, 2) if mid else None,
        "open_interest": int(row.get("openInterest", 0) or 0),
        "volume": int(row.get("volume", 0) or 0),
        "implied_volatility_pct": round(float(row.get("impliedVolatility", 0) or 0) * 100, 1),
        "bid_ask_spread_pct": spread_pct,
        "liquid_enough": (int(row.get("openInterest", 0) or 0) > 500 and (spread_pct or 999) < 10),
    }
