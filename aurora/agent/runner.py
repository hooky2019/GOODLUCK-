"""Agent driver. Wraps the Groq Chat Completions API with a tool-use loop.

Groq's API is OpenAI-compatible. Free tier: Llama 3.3 70B Versatile,
~14,400 req/day, solid tool calling.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Iterator, Optional

from groq import Groq

from ..config import GROQ_API_KEY, MODEL, MAX_AGENT_TURNS
from .prompts import SYSTEM_PROMPT, CHAT_SYSTEM_PROMPT, recommendation_prompt
from .schema import Report
from .tools import TOOL_DEFINITIONS, run_tool


# ───────────────────────── streaming events ─────────────────────────

@dataclass
class Event:
    kind: str  # "text" | "tool_use" | "tool_result" | "done" | "error"
    text: str = ""
    tool_name: str = ""
    tool_args: dict = field(default_factory=dict)
    tool_result_preview: str = ""
    error: str = ""


# ───────────────────────── tool schema ─────────────────────────

def _build_groq_tools() -> list[dict]:
    """Wrap our JSON-Schema tool defs in OpenAI/Groq's `tools` envelope."""
    return [
        {
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool["description"],
                "parameters": tool["input_schema"],
            },
        }
        for tool in TOOL_DEFINITIONS
    ]


_GROQ_TOOLS = _build_groq_tools()


# ───────────────────────── core loop ─────────────────────────

def _client() -> Groq:
    if not GROQ_API_KEY:
        raise RuntimeError(
            "GROQ_API_KEY is not set. Get a free key at https://console.groq.com/keys "
            "and add it to Streamlit secrets."
        )
    return Groq(api_key=GROQ_API_KEY)


def _preview(value: Any, n: int = 240) -> str:
    try:
        s = json.dumps(value, default=str)
    except Exception:
        s = str(value)
    return s if len(s) <= n else s[: n - 1] + "…"


def _safe_args(raw: str | dict | None) -> dict:
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw)
    except Exception:
        return {}


def run_agent(
    system_prompt: str,
    messages: list[dict],
    max_turns: int = MAX_AGENT_TURNS,
) -> Iterator[Event]:
    """Run a tool-use loop, yielding events as they happen.

    `messages` is the conversation so far. The first call should include
    a system message. Mutates `messages` in place.
    """
    client = _client()

    # Ensure a system message is present
    if not messages or messages[0].get("role") != "system":
        messages.insert(0, {"role": "system", "content": system_prompt})

    for _ in range(max_turns):
        try:
            response = client.chat.completions.create(
                model=MODEL,
                messages=messages,
                tools=_GROQ_TOOLS,
                tool_choice="auto",
                temperature=0.4,
                max_tokens=4096,
            )
        except Exception as exc:
            yield Event(kind="error", error=f"API error: {type(exc).__name__}: {exc}")
            return

        choice = response.choices[0]
        msg = choice.message
        text = msg.content or ""
        tool_calls = msg.tool_calls or []

        # Build the assistant message to record in history
        assistant_record: dict[str, Any] = {"role": "assistant", "content": text}
        if tool_calls:
            assistant_record["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in tool_calls
            ]
        messages.append(assistant_record)

        if text:
            yield Event(kind="text", text=text)

        if not tool_calls or choice.finish_reason in ("stop", "length"):
            yield Event(kind="done")
            return

        # Execute each requested tool and append a tool message per call
        for tc in tool_calls:
            name = tc.function.name
            args = _safe_args(tc.function.arguments)
            yield Event(kind="tool_use", tool_name=name, tool_args=args)
            result = run_tool(name, args)
            yield Event(
                kind="tool_result",
                tool_name=name,
                tool_result_preview=_preview(result),
            )
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "name": name,
                "content": json.dumps(result, default=str),
            })

    yield Event(kind="error", error=f"agent did not finish within {max_turns} turns")


# ───────────────────────── high-level entry points ─────────────────────────

JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


def _extract_report(transcript: list[dict]) -> Optional[Report]:
    """Pull the final fenced JSON out of the last assistant turn and validate."""
    for msg in reversed(transcript):
        if msg.get("role") != "assistant":
            continue
        text = msg.get("content") or ""
        if not text:
            continue

        match = JSON_BLOCK_RE.search(text)
        if match:
            raw = match.group(1)
        else:
            brace = text.find("{")
            if brace == -1:
                continue
            raw = text[brace:]

        try:
            data = json.loads(raw)
            return Report(**data)
        except Exception:
            continue
    return None


def generate_report(
    account_size: float,
    on_event: Optional[Callable[[Event], None]] = None,
) -> tuple[Optional[Report], list[dict], str]:
    """Run the recommendation flow. Returns (report, transcript, narrative_text)."""
    messages: list[dict] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": recommendation_prompt(account_size)},
    ]
    narrative_chunks: list[str] = []
    error_text = ""

    for event in run_agent(SYSTEM_PROMPT, messages):
        if event.kind == "text":
            narrative_chunks.append(event.text)
        elif event.kind == "error":
            error_text = event.error
        if on_event is not None:
            on_event(event)
        if event.kind in ("done", "error"):
            break

    report = _extract_report(messages)
    if report is not None:
        report.narrative = "".join(narrative_chunks).strip()
        return report, messages, report.narrative
    return None, messages, error_text or "".join(narrative_chunks).strip()


def chat_followup(
    user_message: str,
    history: list[dict],
    report_context: Optional[Report],
    on_event: Optional[Callable[[Event], None]] = None,
) -> tuple[str, list[dict]]:
    """Run a chat turn with full tool access. Updates and returns history."""
    if not history:
        history.append({"role": "system", "content": CHAT_SYSTEM_PROMPT})
        if report_context is not None:
            ctx = (
                "Here are today's picks (reference when answering follow-ups):\n"
                f"{report_context.model_dump_json(indent=2)}"
            )
            history.append({"role": "user", "content": ctx})
            history.append({"role": "assistant", "content": "Got it — ready for questions."})

    history.append({"role": "user", "content": user_message})

    reply_chunks: list[str] = []
    for event in run_agent(CHAT_SYSTEM_PROMPT, history):
        if event.kind == "text":
            reply_chunks.append(event.text)
        if on_event is not None:
            on_event(event)
        if event.kind in ("done", "error"):
            break

    return "".join(reply_chunks).strip(), history
