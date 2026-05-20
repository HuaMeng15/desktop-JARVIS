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
    "screenshot_file", "response_file", "response_preview",
]


ACTIVITY_LOG_FILE = STATS_DIR / "activity_calls.csv"

_ACTIVITY_FIELDS = ["timestamp", "task_id", "total_ms", "input_tokens", "output_tokens", "cost_usd"]


def _ensure_dirs():
    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    RESPONSES_DIR.mkdir(parents=True, exist_ok=True)
    if not LOG_FILE.exists():
        with open(LOG_FILE, "w", newline="") as f:
            csv.DictWriter(f, fieldnames=_LOG_FIELDS).writeheader()
    if not LLM_LOG_FILE.exists():
        with open(LLM_LOG_FILE, "w", newline="") as f:
            csv.DictWriter(f, fieldnames=_LLM_FIELDS).writeheader()
    if not ACTIVITY_LOG_FILE.exists():
        with open(ACTIVITY_LOG_FILE, "w", newline="") as f:
            csv.DictWriter(f, fieldnames=_ACTIVITY_FIELDS).writeheader()


def log_llm_call(
    trigger: str,
    ttft_ms: float,
    total_ms: float,
    input_tokens: int,
    output_tokens: int,
    response_text: str = "",
    image_bytes: bytes | None = None,
):
    """Save screenshot + response file, append row to stats/llm_calls.csv."""
    _ensure_dirs()
    ts = datetime.now()
    cost = (input_tokens / 1_000_000 * _INPUT_COST_PER_M
            + output_tokens / 1_000_000 * _OUTPUT_COST_PER_M)

    screenshot_file = ""
    if image_bytes is not None:
        screenshot_file = ts.strftime("%Y%m%d_%H%M%S_%f") + ".png"
        (SCREENSHOTS_DIR / screenshot_file).write_bytes(image_bytes)

    response_file = ts.strftime("%Y%m%d_%H%M%S_%f") + ".txt"
    (RESPONSES_DIR / response_file).write_text(response_text, encoding="utf-8")

    row = {
        "timestamp": ts.isoformat(),
        "trigger": trigger,
        "ttft_ms": round(ttft_ms, 1),
        "total_ms": round(total_ms, 1),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_usd": f"{cost:.6f}",
        "screenshot_file": screenshot_file,
        "response_file": response_file,
        "response_preview": response_text[:100].replace("\n", " "),
    }
    with open(LLM_LOG_FILE, "a", newline="") as f:
        csv.DictWriter(f, fieldnames=_LLM_FIELDS).writerow(row)
    print(f"[stats] {trigger}: ttft={ttft_ms:.0f}ms total={total_ms:.0f}ms cost=${cost:.4f}")


def log_activity_call(
    task_id: str,
    total_ms: float,
    input_tokens: int,
    output_tokens: int,
):
    """Append one row to stats/activity_calls.csv for a silent background LLM query."""
    _ensure_dirs()
    cost = (input_tokens / 1_000_000 * _INPUT_COST_PER_M
            + output_tokens / 1_000_000 * _OUTPUT_COST_PER_M)
    row = {
        "timestamp": datetime.now().isoformat(),
        "task_id": task_id,
        "total_ms": round(total_ms, 1),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_usd": f"{cost:.6f}",
    }
    with open(ACTIVITY_LOG_FILE, "a", newline="") as f:
        csv.DictWriter(f, fieldnames=_ACTIVITY_FIELDS).writerow(row)
    print(f"[activity] task={task_id[:8]} total={total_ms:.0f}ms cost=${cost:.4f}")

