"""Earnings dates, ex-dividend dates, and event-window flags."""
from __future__ import annotations

from datetime import datetime, timedelta, date

import pandas as pd
import streamlit as st
import yfinance as yf


def _to_date(value) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    if isinstance(value, datetime):
        return value.date()
    try:
        return pd.to_datetime(value).date()
    except Exception:
        return None


@st.cache_data(ttl=21600, show_spinner=False)
def upcoming(symbol: str) -> dict:
    """Next earnings date, ex-div date, and 10-day event flag."""
    today = date.today()
    earnings_date: date | None = None
    ex_div_date: date | None = None
    try:
        t = yf.Ticker(symbol)
        cal = t.calendar
        if isinstance(cal, dict):
            ed = cal.get("Earnings Date")
            if isinstance(ed, list) and ed:
                earnings_date = _to_date(ed[0])
            else:
                earnings_date = _to_date(ed)
            ex_div_date = _to_date(cal.get("Ex-Dividend Date"))
        elif isinstance(cal, pd.DataFrame) and not cal.empty:
            try:
                earnings_date = _to_date(cal.loc["Earnings Date"].iloc[0])
            except Exception:
                pass
            try:
                ex_div_date = _to_date(cal.loc["Ex-Dividend Date"].iloc[0])
            except Exception:
                pass
    except Exception:
        pass

    def _days(d: date | None) -> int | None:
        if d is None:
            return None
        return (d - today).days

    earnings_in_days = _days(earnings_date)
    ex_div_in_days = _days(ex_div_date)

    has_event_10d = any(
        v is not None and 0 <= v <= 10
        for v in (earnings_in_days, ex_div_in_days)
    )

    return {
        "earnings_date": earnings_date.isoformat() if earnings_date else None,
        "earnings_in_days": earnings_in_days,
        "ex_div_date": ex_div_date.isoformat() if ex_div_date else None,
        "ex_div_in_days": ex_div_in_days,
        "has_event_in_10d": has_event_10d,
    }
