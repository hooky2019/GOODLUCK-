"""Render functions for the swing-trade report."""
from __future__ import annotations

import streamlit as st

from ..agent.schema import Report, Pick


_REGIME_STYLE = {
    "risk-on": ("🟢", "success"),
    "chop": ("🟡", "warning"),
    "risk-off": ("🔴", "error"),
}


def regime_banner(report: Report) -> None:
    r = report.regime
    emoji, kind = _REGIME_STYLE.get(r.label, ("⚪", "info"))
    text = f"### {emoji} Market regime: **{r.label.upper()}**\n\n{r.reasoning}"
    {
        "success": st.success,
        "warning": st.warning,
        "error": st.error,
        "info": st.info,
    }[kind](text)

    c1, c2 = st.columns(2)
    with c1:
        st.markdown(f"**Sizing today:** {r.sizing_advice}")
    with c2:
        st.markdown(f"**Avoiding:** {r.avoid_today}")


def _fmt_money(x: float) -> str:
    return f"${x:,.2f}"


def _setup_emoji(setup: str) -> str:
    return {
        "breakout": "🚀",
        "pullback": "↩️",
        "mean-reversion": "🔄",
        "momentum continuation": "📈",
    }.get(setup, "•")


def pick_card(idx: int, pick: Pick) -> None:
    with st.container(border=True):
        st.markdown(
            f"#### Pick {idx} / 3 — **{pick.ticker}** {_setup_emoji(pick.setup)} *{pick.setup}*"
        )
        st.markdown(f"**Thesis.** {pick.thesis}")

        c1, c2 = st.columns(2)
        with c1:
            st.metric(
                "Entry zone",
                f"{_fmt_money(pick.entry_zone[0])} – {_fmt_money(pick.entry_zone[1])}",
            )
            st.metric("Stop loss", _fmt_money(pick.stop), help=pick.stop_basis)
        with c2:
            st.metric("R / R", f"{pick.rr_ratio:.1f} : 1")
            st.metric(
                "Position size",
                f"{pick.position_size_pct:.1f}%",
                help=f"≈ ${pick.position_size_dollars:,.0f}",
            )

        targets_str = "  ·  ".join(
            f"T{i + 1} {_fmt_money(t)}" for i, t in enumerate(pick.targets)
        )
        st.markdown(f"**Targets.** {targets_str}")

        with st.expander("⚠️ Key risks — what would invalidate this trade"):
            for risk in pick.risks:
                st.markdown(f"- {risk}")

        if pick.options_play:
            op = pick.options_play
            with st.expander(f"💡 Defined-risk options play — {op.type}"):
                st.markdown(
                    f"**Strike:** {_fmt_money(op.strike)}  ·  "
                    f"**Expiry:** {op.expiry}\n\n"
                    f"{op.rationale}"
                )


def report(report: Report) -> None:
    regime_banner(report)
    st.markdown("---")
    if not report.picks:
        st.warning("Aurora returned no picks today — nothing met the quality bar.")
        return
    for i, pick in enumerate(report.picks, start=1):
        pick_card(i, pick)
        st.write("")
