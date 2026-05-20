"""Activity tracker: records what the user is doing across app contexts."""

import base64
import json
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

import imagehash
from PIL import Image

TASKS_DIR = Path(__file__).parent / "stats" / "tasks"
TASKS_FILE = TASKS_DIR / "tasks.json"
TASK_SCREENSHOTS_DIR = TASKS_DIR / "screenshots"
MATCH_THRESHOLD = 10
ACTIVITY_WINDOW_HOURS = 2


@dataclass
class TaskRecord:
    id: str
    app: str
    summary: str
    dhash: str
    screenshot_file: str
    first_seen: str
    last_seen: str


def _ensure_dirs():
    TASK_SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)


def _load() -> list[TaskRecord]:
    if not TASKS_FILE.exists():
        return []
    try:
        data = json.loads(TASKS_FILE.read_text(encoding="utf-8"))
        return [TaskRecord(**r) for r in data]
    except Exception:
        return []


def _save(records: list[TaskRecord]):
    TASKS_FILE.write_text(
        json.dumps([asdict(r) for r in records], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


class ActivityTracker:
    def __init__(self):
        _ensure_dirs()
        self._lock = threading.Lock()
        self._records: list[TaskRecord] = _load()

    def match(self, img: Image.Image) -> TaskRecord | None:
        """Return the stored record closest to img, if within MATCH_THRESHOLD."""
        curr = imagehash.dhash(img)
        best, best_dist = None, MATCH_THRESHOLD + 1
        with self._lock:
            for r in self._records:
                try:
                    dist = curr - imagehash.hex_to_hash(r.dhash)
                    if dist < best_dist:
                        best_dist = dist
                        best = r
                except Exception:
                    continue
        return best if best_dist <= MATCH_THRESHOLD else None

    def upsert(self, img: Image.Image, image_bytes: bytes, app: str, summary: str) -> TaskRecord:
        """Update existing matching record or create a new one."""
        _ensure_dirs()
        curr_hash = imagehash.dhash(img)
        now = datetime.now().isoformat()

        with self._lock:
            # Find closest match
            best, best_dist = None, MATCH_THRESHOLD + 1
            for r in self._records:
                try:
                    dist = curr_hash - imagehash.hex_to_hash(r.dhash)
                    if dist < best_dist:
                        best_dist = dist
                        best = r
                except Exception:
                    continue

            if best is not None and best_dist <= MATCH_THRESHOLD:
                # Update existing
                best.app = app
                best.summary = summary
                best.last_seen = now
                # Overwrite screenshot
                (TASK_SCREENSHOTS_DIR / best.screenshot_file).write_bytes(image_bytes)
                record = best
            else:
                # Create new
                filename = datetime.now().strftime("%Y%m%d_%H%M%S_%f") + ".png"
                (TASK_SCREENSHOTS_DIR / filename).write_bytes(image_bytes)
                record = TaskRecord(
                    id=str(uuid.uuid4()),
                    app=app,
                    summary=summary,
                    dhash=str(curr_hash),
                    screenshot_file=filename,
                    first_seen=now,
                    last_seen=now,
                )
                self._records.append(record)

            _save(self._records)
        return record

    def recent(self, hours: int = ACTIVITY_WINDOW_HOURS) -> list[TaskRecord]:
        """Return records seen within the last N hours, newest first."""
        cutoff = datetime.now() - timedelta(hours=hours)
        with self._lock:
            result = [
                r for r in self._records
                if datetime.fromisoformat(r.last_seen) >= cutoff
            ]
        return sorted(result, key=lambda r: r.last_seen, reverse=True)
