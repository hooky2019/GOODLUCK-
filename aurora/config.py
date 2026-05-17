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


# Groq is the LLM provider — free tier is generous (14,400 req/day for Llama 3.3).
# Get a key at https://console.groq.com/keys
GROQ_API_KEY = _secret("GROQ_API_KEY")
ALPHA_VANTAGE_KEY = _secret("ALPHA_VANTAGE_KEY", "UBM6M5L6O6H62O4K")

# Llama 3.3 70B Versatile — strongest free Groq model, solid tool use.
MODEL = "llama-3.3-70b-versatile"
MAX_AGENT_TURNS = 25
DEFAULT_ACCOUNT_SIZE = 100_000
