import json
import os
import time
from openai import OpenAI
from collections.abc import Generator
from dataclasses import dataclass

_client: OpenAI | None = None

_MODEL = os.getenv("OPENAI_MODEL", "gpt-5-mini")
_RESPONSES_KWARGS = dict(model=_MODEL, max_output_tokens=1024)

_HINT_SYSTEM = """You are JARVIS, a sharp productivity assistant watching a user's screen.

The user has been idle. Your job is NOT to describe the screen — they can see it. Your job is to identify the specific thing near their cursor that they are likely stuck on, and suggest one precise action to unblock them.

## Adaptive tone
- If they appear stuck on a concept or error: explain it briefly and suggest the next step.
- If they appear to be reading/researching: point out the most actionable insight on screen.
- If they appear to be coding: suggest the specific fix, refactor, or next function to write.

## What makes a great hint
- Anchored to what is NEAR THE CURSOR — not the whole page
- Suggests a concrete next action, not "read more" or "scroll down"
- One sentence, like a smart colleague glancing at your screen
- References actual visible content (variable names, error text, article title, UI element)
- If the user has highlighted text, the hint should be about that text

## Examples of great hints
- "That TypeError on line 42 means `data` is None — add a null check before the loop."
- "The abstract says O(1) convergence — the key claim is in the proof at the bottom of page 3."
- "You've been on this config block a while — the missing field is likely `timeout_ms`."
- "That function is 80 lines — extract the inner loop into a helper before it gets harder."

## When NOT to hint
- Private/sensitive content (banking, medical, passwords) → needs_hint=false
- Video or media playing → needs_hint=false
- Screen is clearly idle/locked → needs_hint=false

Return JSON only — no prose, no markdown fences. Fields:
- needs_hint (boolean)
- hint (string): ≤ 300 chars, specific to what is near the cursor
- confidence ("low"|"medium"|"high")
- reason (string): one short phrase explaining your reasoning
- category (string): one of "coding", "reading", "writing", "browsing", "other"
"""


@dataclass
class HintResult:
    needs_hint: bool
    hint: str
    confidence: str   # "low" | "medium" | "high"
    reason: str
    category: str
    input_tokens: int
    output_tokens: int
    total_ms: float


_SELECTION_SYSTEM = """You are JARVIS, a sharp assistant. The user has selected some text and wants to understand it.

Classify the selected text as one of:
- "concept": a term, acronym, or noun phrase (e.g. "HPCC", "mutex", "gradient descent")
- "sentence": a full sentence or clause expressing an idea
- "code": source code, a command, or a code snippet

Then respond based on the type:
- concept → define it clearly and concisely; mention why it matters in context
- sentence → explain the key insight or how to understand it; what does it really mean?
- code → explain what the code does, step by step if needed

Return JSON only — no prose, no markdown fences. Fields:
- needs_hint (boolean): always true when text is selected
- hint (string): your explanation, ≤ 400 chars
- confidence ("low"|"medium"|"high"): always "high" for selections
- reason (string): the detected type — "concept", "sentence", or "code"
- category (string): one of "coding", "reading", "writing", "browsing", "other"
"""


def get_selection_hint(selected_text: str, image_b64: str | None = None) -> HintResult:
    """Explain selected text — concept, sentence, or code."""
    user_text = f'Selected text:\n"""\n{selected_text}\n"""'
    content = []
    if image_b64:
        content.append(_input_image(image_b64))
    content.append({"type": "input_text", "text": user_text})
    messages = [{"role": "user", "content": content}]
    start = time.monotonic()
    msg = _create_response(messages, instructions=_SELECTION_SYSTEM)
    total_ms = (time.monotonic() - start) * 1000
    text = _extract_text(msg).strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    try:
        data = json.loads(text)
    except Exception:
        data = {}
    return HintResult(
        needs_hint=True,
        hint=str(data.get("hint", text)).strip(),
        confidence="high",
        reason=str(data.get("reason", "selection")),
        category=str(data.get("category", "other")),
        input_tokens=_input_tokens(msg),
        output_tokens=_output_tokens(msg),
        total_ms=total_ms,
    )


def get_hint(image_b64: str, cx: int, cy: int, screen_w: int, screen_h: int, idle_s: int) -> HintResult:
    """Call the model with cursor context; return structured HintResult."""
    user_text = (
        f"Cursor is at ({cx}, {cy}) on a {screen_w}×{screen_h} screen. "
        f"The user has been idle for {idle_s} seconds. "
        "What are they likely stuck on near the cursor? Give one specific, actionable hint."
    )
    messages = [{"role": "user", "content": [
        _input_image(image_b64),
        {"type": "input_text", "text": user_text},
    ]}]
    start = time.monotonic()
    msg = _create_response(messages, instructions=_HINT_SYSTEM)
    total_ms = (time.monotonic() - start) * 1000
    text = _extract_text(msg).strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    try:
        data = json.loads(text)
    except Exception:
        data = {}
    return HintResult(
        needs_hint=bool(data.get("needs_hint", False)),
        hint=str(data.get("hint", "")).strip(),
        confidence=str(data.get("confidence", "low")),
        reason=str(data.get("reason", "")),
        category=str(data.get("category", "other")),
        input_tokens=_input_tokens(msg),
        output_tokens=_output_tokens(msg),
        total_ms=total_ms,
    )


def _input_image(image_b64: str) -> dict:
    return {
        "type": "input_image",
        "image_url": f"data:image/png;base64,{image_b64}",
        "detail": "auto",
    }


def _normalize_content(content):
    """Accept current OpenAI blocks and legacy Anthropic-style history blocks."""
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return str(content)

    normalized = []
    for block in content:
        if not isinstance(block, dict):
            normalized.append({"type": "input_text", "text": str(block)})
            continue

        block_type = block.get("type")
        if block_type in {"input_text", "input_image"}:
            normalized.append(block)
        elif block_type == "text":
            normalized.append({"type": "input_text", "text": block.get("text", "")})
        elif block_type == "image":
            source = block.get("source", {})
            data = source.get("data", "")
            media_type = source.get("media_type", "image/png")
            normalized.append({
                "type": "input_image",
                "image_url": f"data:{media_type};base64,{data}",
                "detail": "auto",
            })
        else:
            normalized.append(block)
    return normalized


def _normalize_input(messages: list) -> list:
    return [
        {
            "role": message.get("role", "user"),
            "content": _normalize_content(message.get("content", "")),
        }
        for message in messages
    ]


def _build_input(image_b64: str | None, prompt: str, history: list | None = None) -> list:
    if not history:
        # First turn: include image
        content = []
        if image_b64:
            content.append(_input_image(image_b64))
        content.append({"type": "input_text", "text": prompt})
        return [{"role": "user", "content": content}]
    # Follow-up: history already contains the full prior conversation; just append new user message
    return _normalize_input(history + [{"role": "user", "content": prompt}])


def _create_response(input_items: list, instructions: str | None = None, stream: bool = False):
    kwargs = {**_RESPONSES_KWARGS, "input": _normalize_input(input_items)}
    if instructions:
        kwargs["instructions"] = instructions
    if stream:
        kwargs["stream"] = True
    return _get_client().responses.create(**kwargs)


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI()
    return _client


def _extract_text(msg) -> str:
    text = getattr(msg, "output_text", None)
    if isinstance(text, str):
        return text

    # Test/backward-compatibility fallback for message-like objects.
    content = getattr(msg, "content", None)
    if content:
        return "".join(str(getattr(part, "text", "")) for part in content)

    parts = []
    for item in getattr(msg, "output", []) or []:
        for part in getattr(item, "content", []) or []:
            text = getattr(part, "text", None)
            if text:
                parts.append(text)
    return "".join(parts)


def _input_tokens(msg) -> int:
    usage = getattr(msg, "usage", None)
    return int(getattr(usage, "input_tokens", 0) or 0)


def _output_tokens(msg) -> int:
    usage = getattr(msg, "usage", None)
    return int(getattr(usage, "output_tokens", 0) or 0)


def get_response(image_b64: str | None, prompt: str = "What do you see on this screen? Be concise.",
                 history: list | None = None) -> tuple[str, int, int, float, float]:
    """Returns (response_text, input_tokens, output_tokens, ttft_ms, total_ms)."""
    ttft_ms = None
    start = time.monotonic()
    chunks = []
    final_msg = None

    stream = _create_response(_build_input(image_b64, prompt, history), stream=True)
    for event in stream:
        event_type = getattr(event, "type", "")
        if event_type == "response.output_text.delta":
            text = getattr(event, "delta", "")
            if ttft_ms is None:
                ttft_ms = (time.monotonic() - start) * 1000
            chunks.append(text)
        elif event_type == "response.completed":
            final_msg = getattr(event, "response", None)
        elif event_type == "error":
            raise RuntimeError(str(getattr(event, "message", event)))

    total_ms = (time.monotonic() - start) * 1000
    text = "".join(chunks) or (_extract_text(final_msg) if final_msg else "")
    return text, _input_tokens(final_msg), _output_tokens(final_msg), ttft_ms or total_ms, total_ms


def stream_response(image_b64: str, prompt: str, history: list | None = None) -> Generator[str | tuple, None, None]:
    """Yield text chunks, then finally yield (input_tokens, output_tokens, ttft_ms, total_ms)."""
    ttft_ms = None
    start = time.monotonic()
    final_msg = None

    stream = _create_response(_build_input(image_b64, prompt, history), stream=True)
    for event in stream:
        event_type = getattr(event, "type", "")
        if event_type == "response.output_text.delta":
            text = getattr(event, "delta", "")
            if ttft_ms is None:
                ttft_ms = (time.monotonic() - start) * 1000
            yield text
        elif event_type == "response.completed":
            final_msg = getattr(event, "response", None)
        elif event_type == "error":
            raise RuntimeError(str(getattr(event, "message", event)))

    total_ms = (time.monotonic() - start) * 1000
    yield (_input_tokens(final_msg), _output_tokens(final_msg), ttft_ms or total_ms, total_ms)
