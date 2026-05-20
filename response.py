import time
import anthropic
from collections.abc import Generator

_client = anthropic.Anthropic()

_MESSAGES_KWARGS = dict(model="claude-opus-4-6", max_tokens=1024)


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
