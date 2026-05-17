"""Technical indicators. Ported from nasdaq_dashboard/app.py."""
from __future__ import annotations

import numpy as np
import pandas as pd


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    d = series.diff()
    gain = d.where(d > 0, 0.0).rolling(period).mean()
    loss = (-d.where(d < 0, 0.0)).rolling(period).mean()
    return 100 - 100 / (1 + gain / loss.replace(0, np.nan))


def macd(series: pd.Series, fast: int = 12, slow: int = 26, sig: int = 9):
    ef = series.ewm(span=fast).mean()
    es = series.ewm(span=slow).mean()
    m = ef - es
    s = m.ewm(span=sig).mean()
    return m, s, m - s


def atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low - close.shift()).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(period).mean()


def ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span).mean()


def find_swing_levels(df: pd.DataFrame) -> dict:
    """Recent and medium-term support/resistance from highs/lows."""
    return {
        "support_l20": float(df.tail(20)["Low"].min()),
        "support_l60": float(df.tail(60)["Low"].min()),
        "resistance_h20": float(df.tail(20)["High"].max()),
        "resistance_h60": float(df.tail(60)["High"].max()),
    }


def trend_strength_label(close: pd.Series) -> str:
    """Plain-English trend strength: days closed above EMA20 in last 10 sessions."""
    if len(close) < 20:
        return "Unknown"
    e20 = close.ewm(span=20).mean()
    above = int((close.tail(10) > e20.tail(10)).sum())
    if above >= 9:
        return "Very Strong"
    if above >= 7:
        return "Strong"
    if above >= 4:
        return "Mixed"
    return "Weak"


def compute_technicals(df: pd.DataFrame) -> dict:
    """Bundle every indicator the agent cares about for one ticker."""
    if df is None or df.empty or len(df) < 60:
        return {"error": "insufficient history"}

    close = df["Close"]
    last = float(close.iloc[-1])

    ema20 = float(ema(close, 20).iloc[-1])
    ema50 = float(ema(close, 50).iloc[-1])
    rsi14 = float(rsi(close, 14).iloc[-1])
    macd_line, macd_sig, macd_hist = macd(close)
    atr14 = float(atr(df["High"], df["Low"], close, 14).iloc[-1])
    swings = find_swing_levels(df)

    if last > ema20 > ema50:
        ema_pos = "above both (bullish stack)"
    elif last > ema20 and ema20 < ema50:
        ema_pos = "above EMA20, below EMA50 (recovering)"
    elif last < ema20 < ema50:
        ema_pos = "below both (bearish stack)"
    else:
        ema_pos = "mixed"

    return {
        "last_price": round(last, 2),
        "ema20": round(ema20, 2),
        "ema50": round(ema50, 2),
        "ema_position": ema_pos,
        "rsi14": round(rsi14, 1),
        "macd_line": round(float(macd_line.iloc[-1]), 3),
        "macd_signal": round(float(macd_sig.iloc[-1]), 3),
        "macd_hist": round(float(macd_hist.iloc[-1]), 3),
        "macd_state": "bullish cross fresh" if (macd_hist.iloc[-1] > 0 and macd_hist.iloc[-2] <= 0)
                      else "bearish cross fresh" if (macd_hist.iloc[-1] < 0 and macd_hist.iloc[-2] >= 0)
                      else "bullish" if macd_hist.iloc[-1] > 0 else "bearish",
        "atr14": round(atr14, 2),
        "atr_pct": round(atr14 / last * 100, 2),
        "support_20d": round(swings["support_l20"], 2),
        "support_60d": round(swings["support_l60"], 2),
        "resistance_20d": round(swings["resistance_h20"], 2),
        "resistance_60d": round(swings["resistance_h60"], 2),
        "trend_strength": trend_strength_label(close),
        "pct_from_ema20": round((last / ema20 - 1) * 100, 2),
        "pct_from_ema50": round((last / ema50 - 1) * 100, 2),
    }
