"""Cache controls for refresh button."""
import streamlit as st


def bust_all() -> None:
    """Clear every @st.cache_data and drop the last report from session state."""
    st.cache_data.clear()
    st.session_state.pop("last_report", None)
    st.session_state.pop("last_refresh_at", None)
    st.session_state.pop("chat_history", None)
