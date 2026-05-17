"""GOODLUCK $ — Streamlit entry point. Mobile-first layout."""
from __future__ import annotations

from datetime import datetime, timezone

import streamlit as st

st.set_page_config(
    page_title="GOODLUCK $",
    page_icon="🍀",
    layout="centered",
    initial_sidebar_state="collapsed",
)

from aurora.agent import runner
from aurora.agent.schema import Report
from aurora.config import GEMINI_API_KEY, DEFAULT_ACCOUNT_SIZE
from aurora.data import cache as data_cache
from aurora.ui import chat as chat_ui
from aurora.ui import render as render_ui


# ───────────────────────── header ─────────────────────────

st.title("🍀 GOODLUCK $")
st.caption("Swing-trade picks for the Nasdaq 100 — refreshed on demand, with a live AI analyst.")

if not GEMINI_API_KEY:
    st.error(
        "GEMINI_API_KEY is not set. Get a free key at https://aistudio.google.com/apikey "
        "and add it to `.streamlit/secrets.toml` locally, or in Streamlit Cloud → Settings → Secrets."
    )
    st.stop()


# ───────────────────────── controls ─────────────────────────

c_size, c_refresh = st.columns([2, 1])

with c_size:
    account_size = st.number_input(
        "Account size ($)",
        min_value=1_000,
        max_value=10_000_000,
        value=int(st.session_state.get("account_size", DEFAULT_ACCOUNT_SIZE)),
        step=5_000,
        help="Used to convert position-size % into dollars. Risk per trade = 1% of this.",
    )
    st.session_state["account_size"] = account_size

with c_refresh:
    st.write("")
    refresh = st.button("🔄 Refresh picks", type="primary", use_container_width=True)

last_refresh_at = st.session_state.get("last_refresh_at")
if last_refresh_at:
    st.caption(f"Last updated: {last_refresh_at}  ·  quotes are 15 minutes delayed")
else:
    st.caption("Tap **Refresh picks** to start. First run takes ~30–90 s while Goodluck pulls live data.")


# ───────────────────────── generate report ─────────────────────────

def _run_report(account_size: float) -> None:
    data_cache.bust_all()
    st.session_state["account_size"] = account_size  # bust_all clears session_state["last_report"] but keeps the rest

    tool_log: list[str] = []
    with st.status("Goodluck is working…", expanded=True) as status:
        log_box = st.empty()

        def on_event(event):
            if event.kind == "tool_use":
                args_str = _fmt_args(event.tool_args)
                tool_log.append(f"🔧 `{event.tool_name}({args_str})`")
                status.update(label=f"Goodluck is calling {event.tool_name}…")
                log_box.markdown("\n\n".join(tool_log))
            elif event.kind == "tool_result":
                pass  # avoid double-logging; result preview not shown
            elif event.kind == "error":
                tool_log.append(f"❌ {event.error}")
                log_box.markdown("\n\n".join(tool_log))

        report_obj, transcript, narrative = runner.generate_report(
            account_size=account_size, on_event=on_event
        )

        if report_obj is None:
            status.update(label="Could not generate a valid report", state="error", expanded=True)
            st.error("Goodluck's response did not parse into a valid report.")
            with st.expander("Show what Goodluck said"):
                st.markdown(narrative or "_(no narrative captured)_")
            return

        status.update(label="Done", state="complete", expanded=False)

    st.session_state["last_report"] = report_obj
    st.session_state["last_refresh_at"] = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M %Z")
    st.session_state["last_narrative"] = report_obj.narrative
    st.session_state["chat_display"] = []
    st.session_state["chat_transcript"] = []


def _fmt_args(args: dict) -> str:
    if not args:
        return ""
    parts = []
    for k, v in args.items():
        s = str(v)
        if len(s) > 24:
            s = s[:21] + "…"
        parts.append(f"{k}={s}")
    return ", ".join(parts)


if refresh:
    _run_report(account_size)


# ───────────────────────── render ─────────────────────────

report_obj: Report | None = st.session_state.get("last_report")

if report_obj is not None:
    with st.expander("📝 How Goodluck got here (reasoning)"):
        st.markdown(st.session_state.get("last_narrative", "") or "_(no narrative)_")
    st.write("")
    render_ui.report(report_obj)
    st.markdown("---")
    chat_ui.render(report_obj)
else:
    st.info(
        "No picks yet for this session. Tap **🔄 Refresh picks** above.\n\n"
        "Goodluck will:\n"
        "1. Read the market regime (SPY/QQQ/VIX/sectors)\n"
        "2. Screen the Nasdaq 100 for the top ~15 setups\n"
        "3. Drill into the strongest 6–10 names (technicals, options, catalysts, news, Reddit)\n"
        "4. Return the top 3 with full trade plans"
    )
    st.markdown("---")
    st.caption("**Disclaimer.** Educational tool. Not investment advice. Paper-trade first.")
