"""Centralized config + secrets access."""
from __future__ import annotations

import os

try:
    import streamlit as st
    _IN_STREAMLIT = True
except Exception:
    st = None
    _IN_STREAMLIT = False


def _secret(name: str, default: str = "") -> str:
    if _IN_STREAMLIT:
        try:
            val = st.secrets.get(name)
            if val:
                return str(val)
        except Exception:
            pass
    return os.environ.get(name, default)


# Gemini is the LLM provider — free tier covers normal use.
# Get a key at https://aistudio.google.com/apikey
GEMINI_API_KEY = _secret("GEMINI_API_KEY") or _secret("GOOGLE_API_KEY")
ALPHA_VANTAGE_KEY = _secret("ALPHA_VANTAGE_KEY", "UBM6M5L6O6H62O4K")

# gemini-2.5-flash-lite has the most generous free-tier daily quota
# (gemini-2.5-flash was only 20 req/day on a new project; lite is ~1000+).
# Bump to "gemini-2.5-flash" if you enable Google billing for better reasoning.
MODEL = "gemini-2.5-flash-lite"
MAX_AGENT_TURNS = 30
DEFAULT_ACCOUNT_SIZE = 100_000
