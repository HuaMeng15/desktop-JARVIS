"""Statistics module: records screenshots, API calls, and user reactions."""

import csv
from datetime import datetime
from pathlib import Path

STATS_DIR = Path(__file__).parent / "stats"
SCREENSHOTS_DIR = STATS_DIR / "screenshots"
RESPONSES_DIR = STATS_DIR / "responses"
LOG_FILE = STATS_DIR / "log.csv"
LLM_LOG_FILE = STATS_DIR / "llm_calls.csv"

# claude-opus-4-6 pricing (per million tokens)
_INPUT_COST_PER_M = 15.0
_OUTPUT_COST_PER_M = 75.0

_LOG_FIELDS = [
    "timestamp", "screenshot_file",
    "api_time_ms", "reaction_time_ms", "user_reaction",
    "input_tokens", "output_tokens", "cost_usd",
    "response_file", "response_preview",
]

_LLM_FIELDS = [
    "timestamp", "trigger", "ttft_ms", "total_ms",
    "input_tokens", "output_tokens", "cost_usd",
    "cursor_x", "cursor_y",
    "selected_text",
    "screenshot_file", "response_file", "response_preview", "reaction",
]


ACTIVITY_LOG_FILE = STATS_DIR / "activity_calls.csv"

_ACTIVITY_FIELDS = ["timestamp", "task_id", "app", "summary", "screenshot_file", "total_ms", "input_tokens", "output_tokens", "cost_usd"]


def _migrate_csv(path: Path, fieldnames: list[str]):
    """Rewrite path with the given fieldnames if the header is out of date."""
    if not path.exists():
        return
    with open(path, "r", newline="") as f:
        rows = list(csv.DictReader(f))
    # Check whether the stored header already matches
    with open(path, "r", newline="") as f:
        stored_header = next(csv.reader(f), [])
    if stored_header == fieldnames:
        return
    # Rewrite: normalize each row (drop None overflow keys, fill missing fields)
    for row in rows:
        row.pop(None, None)
        for col in fieldnames:
            row.setdefault(col, "")
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    print(f"[stats] migrated {path.name} to new schema")


def _ensure_dirs():
    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    RESPONSES_DIR.mkdir(parents=True, exist_ok=True)
    if not LOG_FILE.exists():
        with open(LOG_FILE, "w", newline="") as f:
            csv.DictWriter(f, fieldnames=_LOG_FIELDS).writeheader()
    if not LLM_LOG_FILE.exists():
        with open(LLM_LOG_FILE, "w", newline="") as f:
            csv.DictWriter(f, fieldnames=_LLM_FIELDS).writeheader()
    else:
        _migrate_csv(LLM_LOG_FILE, _LLM_FIELDS)
    if not ACTIVITY_LOG_FILE.exists():
        with open(ACTIVITY_LOG_FILE, "w", newline="") as f:
            csv.DictWriter(f, fieldnames=_ACTIVITY_FIELDS).writeheader()
    else:
        _migrate_csv(ACTIVITY_LOG_FILE, _ACTIVITY_FIELDS)


def log_llm_call(
    trigger: str,
    ttft_ms: float,
    total_ms: float,
    input_tokens: int,
    output_tokens: int,
    response_text: str = "",
    image_bytes: bytes | None = None,
    cursor_x: int | None = None,
    cursor_y: int | None = None,
    selected_text: str | None = None,
):
    """Save screenshot + response file, append row to stats/llm_calls.csv."""
    _ensure_dirs()
    ts = datetime.now()
    cost = (input_tokens / 1_000_000 * _INPUT_COST_PER_M
            + output_tokens / 1_000_000 * _OUTPUT_COST_PER_M)

    screenshot_file = ""
    if image_bytes is not None:
        screenshot_file = ts.strftime("%Y%m%d_%H%M%S_%f") + ".png"
        img_path = SCREENSHOTS_DIR / screenshot_file
        if cursor_x is not None and cursor_y is not None:
            # Draw a red crosshair at the cursor position
            from PIL import Image as PILImage, ImageDraw
            img = PILImage.open(__import__("io").BytesIO(image_bytes)).convert("RGB")
            draw = ImageDraw.Draw(img)
            r = 10
            draw.line([(cursor_x - r, cursor_y), (cursor_x + r, cursor_y)], fill="red", width=2)
            draw.line([(cursor_x, cursor_y - r), (cursor_x, cursor_y + r)], fill="red", width=2)
            draw.ellipse([(cursor_x - r, cursor_y - r), (cursor_x + r, cursor_y + r)], outline="red", width=2)
            buf = __import__("io").BytesIO()
            img.save(buf, format="PNG")
            img_path.write_bytes(buf.getvalue())
        else:
            img_path.write_bytes(image_bytes)

    response_file = ts.strftime("%Y%m%d_%H%M%S_%f") + ".txt"
    (RESPONSES_DIR / response_file).write_text(response_text, encoding="utf-8")

    ts_key = ts.isoformat()
    row = {
        "timestamp": ts_key,
        "trigger": trigger,
        "ttft_ms": round(ttft_ms, 1),
        "total_ms": round(total_ms, 1),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_usd": f"{cost:.6f}",
        "cursor_x": cursor_x if cursor_x is not None else "",
        "cursor_y": cursor_y if cursor_y is not None else "",
        "selected_text": (selected_text or "")[:200],
        "screenshot_file": screenshot_file,
        "response_file": response_file,
        "response_preview": response_text[:100].replace("\n", " "),
        "reaction": "",
    }
    with open(LLM_LOG_FILE, "a", newline="") as f:
        csv.DictWriter(f, fieldnames=_LLM_FIELDS).writerow(row)
    print(f"[stats] {trigger}: ttft={ttft_ms:.0f}ms total={total_ms:.0f}ms cost=${cost:.4f}")
    return ts_key


def update_llm_reaction(ts_key: str, reaction: str):
    """Find the row with the given timestamp and update its reaction field."""
    if not LLM_LOG_FILE.exists() or not ts_key:
        return
    with open(LLM_LOG_FILE, "r", newline="") as f:
        rows = list(csv.DictReader(f))
    updated = False
    for row in rows:
        row.pop(None, None)          # drop overflow key from old-schema rows
        row.setdefault("reaction", "")  # fill missing reaction for old rows
        if row.get("timestamp") == ts_key:
            row["reaction"] = reaction
            updated = True
    if not updated:
        return
    with open(LLM_LOG_FILE, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=_LLM_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    print(f"[stats] reaction={reaction!r} logged for {ts_key}")


def log_activity_call(
    task_id: str,
    total_ms: float,
    input_tokens: int,
    output_tokens: int,
    app: str = "",
    summary: str = "",
    screenshot_file: str = "",
):
    """Append one row to stats/activity_calls.csv for a silent background LLM query."""
    _ensure_dirs()
    cost = (input_tokens / 1_000_000 * _INPUT_COST_PER_M
            + output_tokens / 1_000_000 * _OUTPUT_COST_PER_M)
    row = {
        "timestamp": datetime.now().isoformat(),
        "task_id": task_id,
        "app": app,
        "summary": summary,
        "screenshot_file": screenshot_file,
        "total_ms": round(total_ms, 1),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_usd": f"{cost:.6f}",
    }
    with open(ACTIVITY_LOG_FILE, "a", newline="") as f:
        csv.DictWriter(f, fieldnames=_ACTIVITY_FIELDS).writerow(row)
    print(f"[activity] task={task_id[:8]} app={app} total={total_ms:.0f}ms cost=${cost:.4f}")

