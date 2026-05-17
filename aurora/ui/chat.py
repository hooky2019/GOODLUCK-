"""Chat panel — full tool access, multi-turn, mobile-friendly."""
from __future__ import annotations

from typing import Optional

import streamlit as st

from ..agent import runner
from ..agent.schema import Report


def render(report: Optional[Report]) -> None:
    st.markdown("## 💬 Ask Aurora")
    st.caption("Ask follow-ups about any ticker. Aurora can pull fresh data live.")

    # Display history (stored as a list of {"role", "text"} for the UI only;
    # the full Anthropic transcript lives in session_state["chat_transcript"]).
    if "chat_display" not in st.session_state:
        st.session_state["chat_display"] = []
    if "chat_transcript" not in st.session_state:
        st.session_state["chat_transcript"] = []

    for entry in st.session_state["chat_display"]:
        with st.chat_message(entry["role"]):
            st.markdown(entry["text"])

    user_input = st.chat_input("Ask about a ticker, a setup, or anything else…")
    if not user_input:
        return

    st.session_state["chat_display"].append({"role": "user", "text": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    with st.chat_message("assistant"):
        with st.status("Thinking…", expanded=False) as status:
            tool_log: list[str] = []

            def on_event(event):
                if event.kind == "tool_use":
                    tool_log.append(f"🔧 `{event.tool_name}({_fmt_args(event.tool_args)})`")
                    status.update(label=f"Calling {event.tool_name}…", expanded=True)
                    st.markdown("\n".join(tool_log))
                elif event.kind == "error":
                    tool_log.append(f"❌ {event.error}")
                    st.markdown("\n".join(tool_log))

            reply, transcript = runner.chat_followup(
                user_input,
                st.session_state["chat_transcript"],
                report,
                on_event=on_event,
            )
            status.update(label="Done", state="complete", expanded=False)

        st.session_state["chat_transcript"] = transcript
        if reply:
            st.markdown(reply)
            st.session_state["chat_display"].append({"role": "assistant", "text": reply})


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
