import json
import time
import anthropic
from collections.abc import Generator
from dataclasses import dataclass

_client = anthropic.Anthropic()

_MESSAGES_KWARGS = dict(model="claude-opus-4-6", max_tokens=1024)

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
- hint (string): one sentence ≤ 140 chars, specific to what is near the cursor
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


def get_hint(image_b64: str, cx: int, cy: int, screen_w: int, screen_h: int, idle_s: int) -> HintResult:
    """Call the model with cursor context; return structured HintResult."""
    user_text = (
        f"Cursor is at ({cx}, {cy}) on a {screen_w}×{screen_h} screen. "
        f"The user has been idle for {idle_s} seconds. "
        "What are they likely stuck on near the cursor? Give one specific, actionable hint."
    )
    messages = [{"role": "user", "content": [
        {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": image_b64}},
        {"type": "text", "text": user_text},
    ]}]
    start = time.monotonic()
    msg = _client.messages.create(**_MESSAGES_KWARGS, system=_HINT_SYSTEM, messages=messages)
    total_ms = (time.monotonic() - start) * 1000
    text = msg.content[0].text.strip()
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
        input_tokens=msg.usage.input_tokens,
        output_tokens=msg.usage.output_tokens,
        total_ms=total_ms,
    )


def _build_messages(image_b64: str, prompt: str) -> list:
    return [{"role": "user", "content": [
        {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": image_b64}},
        {"type": "text", "text": prompt},
    ]}]


def get_response(image_b64: str, prompt: str = "What do you see on this screen? Be concise.") -> tuple[str, int, int, float, float]:
    """Returns (response_text, input_tokens, output_tokens, ttft_ms, total_ms)."""
    ttft_ms = None
    start = time.monotonic()
    chunks = []

    with _client.messages.stream(**_MESSAGES_KWARGS, messages=_build_messages(image_b64, prompt)) as stream:
        for text in stream.text_stream:
            if ttft_ms is None:
                ttft_ms = (time.monotonic() - start) * 1000
            chunks.append(text)
        msg = stream.get_final_message()

    total_ms = (time.monotonic() - start) * 1000
    return "".join(chunks), msg.usage.input_tokens, msg.usage.output_tokens, ttft_ms or total_ms, total_ms


def stream_response(image_b64: str, prompt: str) -> Generator[str | tuple, None, None]:
    """Yield text chunks, then finally yield (input_tokens, output_tokens, ttft_ms, total_ms)."""
    ttft_ms = None
    start = time.monotonic()

    with _client.messages.stream(**_MESSAGES_KWARGS, messages=_build_messages(image_b64, prompt)) as stream:
        for text in stream.text_stream:
            if ttft_ms is None:
                ttft_ms = (time.monotonic() - start) * 1000
            yield text
        msg = stream.get_final_message()

    total_ms = (time.monotonic() - start) * 1000
    yield (msg.usage.input_tokens, msg.usage.output_tokens, ttft_ms or total_ms, total_ms)
