"""Agent driver. Wraps the Google Gemini API with a tool-use loop.

Uses google-genai (the unified SDK). Free-tier model: gemini-2.0-flash.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Iterator, Optional

from google import genai
from google.genai import types

from ..config import GEMINI_API_KEY, MODEL, MAX_AGENT_TURNS
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


# ───────────────────────── tool schema conversion ─────────────────────────

_TYPE_MAP = {
    "string": "STRING",
    "integer": "INTEGER",
    "number": "NUMBER",
    "boolean": "BOOLEAN",
    "object": "OBJECT",
    "array": "ARRAY",
}


def _convert_schema(schema: dict) -> types.Schema:
    """Convert JSON Schema dict to Gemini's types.Schema."""
    js_type = schema.get("type", "string").lower()
    kwargs: dict = {"type": _TYPE_MAP.get(js_type, "STRING")}
    if "description" in schema:
        kwargs["description"] = schema["description"]
    if "enum" in schema:
        kwargs["enum"] = schema["enum"]
    if js_type == "object":
        props = schema.get("properties", {})
        if props:
            kwargs["properties"] = {k: _convert_schema(v) for k, v in props.items()}
        if "required" in schema:
            kwargs["required"] = schema["required"]
    if js_type == "array" and "items" in schema:
        kwargs["items"] = _convert_schema(schema["items"])
    return types.Schema(**kwargs)


def _build_function_declarations() -> list[types.FunctionDeclaration]:
    decls = []
    for tool in TOOL_DEFINITIONS:
        params = _convert_schema(tool["input_schema"])
        decls.append(types.FunctionDeclaration(
            name=tool["name"],
            description=tool["description"],
            parameters=params,
        ))
    return decls


_FUNCTION_DECLS = _build_function_declarations()
_GEMINI_TOOL = types.Tool(function_declarations=_FUNCTION_DECLS)


# ───────────────────────── core loop ─────────────────────────

def _client() -> genai.Client:
    if not GEMINI_API_KEY:
        raise RuntimeError(
            "GEMINI_API_KEY is not set. Get one free at https://aistudio.google.com/apikey "
            "and add it to Streamlit secrets."
        )
    return genai.Client(api_key=GEMINI_API_KEY)


def _preview(value: Any, n: int = 240) -> str:
    try:
        s = json.dumps(value, default=str)
    except Exception:
        s = str(value)
    return s if len(s) <= n else s[: n - 1] + "…"


def run_agent(
    system_prompt: str,
    contents: list[types.Content],
    max_turns: int = MAX_AGENT_TURNS,
) -> Iterator[Event]:
    """Run a tool-use loop, yielding events as they happen.

    `contents` is the conversation so far (first user turn must already be in).
    Mutates `contents` in place so callers can persist the full transcript.
    """
    client = _client()
    config = types.GenerateContentConfig(
        system_instruction=system_prompt,
        tools=[_GEMINI_TOOL],
        temperature=0.4,
    )

    for _ in range(max_turns):
        try:
            response = client.models.generate_content(
                model=MODEL,
                contents=contents,
                config=config,
            )
        except Exception as exc:
            yield Event(kind="error", error=f"API error: {type(exc).__name__}: {exc}")
            return

        candidate = response.candidates[0] if response.candidates else None
        if candidate is None or candidate.content is None:
            yield Event(kind="error", error="Empty response from Gemini")
            return

        # Record assistant turn
        contents.append(candidate.content)

        function_responses: list[types.Part] = []
        for part in candidate.content.parts or []:
            if getattr(part, "text", None):
                yield Event(kind="text", text=part.text)
            fc = getattr(part, "function_call", None)
            if fc and fc.name:
                args = dict(fc.args or {})
                yield Event(kind="tool_use", tool_name=fc.name, tool_args=args)
                result = run_tool(fc.name, args)
                yield Event(
                    kind="tool_result",
                    tool_name=fc.name,
                    tool_result_preview=_preview(result),
                )
                # Gemini requires the function_response payload to be a dict
                response_payload = result if isinstance(result, dict) else {"result": result}
                function_responses.append(
                    types.Part.from_function_response(
                        name=fc.name,
                        response=response_payload,
                    )
                )

        if not function_responses:
            # No tool calls — model is done
            yield Event(kind="done")
            return

        # Send tool results back as a user turn
        contents.append(types.Content(role="user", parts=function_responses))

    yield Event(kind="error", error=f"agent did not finish within {max_turns} turns")


# ───────────────────────── high-level entry points ─────────────────────────

JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


def _extract_text_from_content(content: types.Content) -> str:
    text = ""
    for part in content.parts or []:
        if getattr(part, "text", None):
            text += part.text
    return text


def _extract_report(transcript: list[types.Content]) -> Optional[Report]:
    """Pull the final fenced JSON out of the last model turn and validate."""
    for content in reversed(transcript):
        if content.role != "model":
            continue
        text = _extract_text_from_content(content)
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
) -> tuple[Optional[Report], list[types.Content], str]:
    """Run the recommendation flow. Returns (report, transcript, narrative_text)."""
    contents: list[types.Content] = [
        types.Content(
            role="user",
            parts=[types.Part.from_text(text=recommendation_prompt(account_size))],
        )
    ]
    narrative_chunks: list[str] = []
    error_text = ""

    for event in run_agent(SYSTEM_PROMPT, contents):
        if event.kind == "text":
            narrative_chunks.append(event.text)
        elif event.kind == "error":
            error_text = event.error
        if on_event is not None:
            on_event(event)
        if event.kind in ("done", "error"):
            break

    report = _extract_report(contents)
    if report is not None:
        report.narrative = "".join(narrative_chunks).strip()
        return report, contents, report.narrative
    return None, contents, error_text or "".join(narrative_chunks).strip()


def chat_followup(
    user_message: str,
    history: list[types.Content],
    report_context: Optional[Report],
    on_event: Optional[Callable[[Event], None]] = None,
) -> tuple[str, list[types.Content]]:
    """Run a chat turn with full tool access. Updates and returns history."""
    if not history and report_context is not None:
        ctx = (
            "Here are today's picks (reference when answering follow-ups):\n"
            f"{report_context.model_dump_json(indent=2)}"
        )
        history.append(types.Content(role="user", parts=[types.Part.from_text(text=ctx)]))
        history.append(types.Content(
            role="model",
            parts=[types.Part.from_text(text="Got it — ready for questions.")],
        ))

    history.append(types.Content(role="user", parts=[types.Part.from_text(text=user_message)]))

    reply_chunks: list[str] = []
    for event in run_agent(CHAT_SYSTEM_PROMPT, history):
        if event.kind == "text":
            reply_chunks.append(event.text)
        if on_event is not None:
            on_event(event)
        if event.kind in ("done", "error"):
            break

    return "".join(reply_chunks).strip(), history
