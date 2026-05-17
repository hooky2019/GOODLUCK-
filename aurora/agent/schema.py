"""Pydantic models for the structured Report that Claude must emit."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


SetupType = Literal["breakout", "pullback", "mean-reversion", "momentum continuation"]
RegimeLabel = Literal["risk-on", "risk-off", "chop"]


class RegimeRead(BaseModel):
    label: RegimeLabel
    reasoning: str
    sizing_advice: str
    avoid_today: str


class OptionsPlay(BaseModel):
    type: str = Field(..., description="long call, debit spread, put credit spread, etc.")
    strike: float
    expiry: str
    rationale: str


class Pick(BaseModel):
    ticker: str
    setup: SetupType
    thesis: str
    entry_zone: list[float] = Field(..., min_length=2, max_length=2)
    stop: float
    stop_basis: str
    targets: list[float] = Field(..., min_length=1, max_length=3)
    rr_ratio: float
    position_size_pct: float
    position_size_dollars: float
    risks: list[str]
    options_play: Optional[OptionsPlay] = None


class Report(BaseModel):
    regime: RegimeRead
    picks: list[Pick] = Field(..., max_length=3)
    narrative: str = ""
