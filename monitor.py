"""Frame comparison: dHash + PSNR, rolling screenshot storage, CSV logging."""

import csv
from pathlib import Path

import imagehash
import numpy as np
from PIL import Image

TMP_DIR = Path(__file__).parent / "tmp"
SCREENSHOTS_DIR = TMP_DIR / "screenshots"
RECORD_CSV = TMP_DIR / "record.csv"
MAX_FRAMES = 300
_CURSOR_REGION = 300  # half-size of cursor crop in pixels
_CSV_FIELDS = ["current_name", "previous_name", "score", "cursor_score", "psnr", "cursor_x", "cursor_y"]


def _psnr(a: Image.Image, b: Image.Image) -> float:
    arr_a = np.array(a, dtype=np.float32)
    arr_b = np.array(b, dtype=np.float32)
    mse = np.mean((arr_a - arr_b) ** 2)
    if mse == 0:
        return float("inf")
    return 20 * np.log10(255.0 / np.sqrt(mse))


def _cursor_crop(img: Image.Image, cx: int, cy: int) -> Image.Image:
    r = _CURSOR_REGION
    x0, y0 = max(0, cx - r), max(0, cy - r)
    x1, y1 = min(img.width, cx + r), min(img.height, cy + r)
    return img.crop((x0, y0, x1, y1))


class FrameMonitor:
    def __init__(self):
        SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
        if not RECORD_CSV.exists():
            with open(RECORD_CSV, "w", newline="") as f:
                csv.DictWriter(f, fieldnames=_CSV_FIELDS).writeheader()
        self._prev_img: Image.Image | None = None
        self._prev_name: str | None = None
        self._frame_files: list[Path] = sorted(SCREENSHOTS_DIR.glob("*.png"))

    def save_frame(self, image_bytes: bytes, name: str) -> Path:
        """Save frame, enforce rolling window of MAX_FRAMES."""
        path = SCREENSHOTS_DIR / name
        path.write_bytes(image_bytes)
        self._frame_files.append(path)
        while len(self._frame_files) > MAX_FRAMES:
            oldest = self._frame_files.pop(0)
            oldest.unlink(missing_ok=True)
        return path

    def reset(self):
        """Clear previous frame so next update starts fresh (no re-trigger after overlay)."""
        self._prev_img = None
        self._prev_name = None

    def update(self, img: Image.Image, name: str, cx: int = 0, cy: int = 0) -> tuple[int, float]:
        """Compare img with previous frame. Returns (score, psnr) where score>0 means changed.
        score combines full-screen dHash and cursor-region dHash."""
        curr_hash = imagehash.dhash(img)
        curr_crop = _cursor_crop(img, cx, cy)
        score = 0
        psnr_val = float("inf")
        cursor_score = 0

        if self._prev_img is not None:
            score = curr_hash - imagehash.dhash(self._prev_img)
            prev_crop = _cursor_crop(self._prev_img, cx, cy)
            cursor_score = imagehash.dhash(curr_crop) - imagehash.dhash(prev_crop)
            psnr_val = _psnr(self._prev_img, img)
            with open(RECORD_CSV, "a", newline="") as f:
                csv.DictWriter(f, fieldnames=_CSV_FIELDS).writerow({
                    "current_name": name,
                    "previous_name": self._prev_name,
                    "score": score,
                    "cursor_score": cursor_score,
                    "psnr": f"{psnr_val:.2f}" if psnr_val != float("inf") else "inf",
                    "cursor_x": cx,
                    "cursor_y": cy,
                })

        self._prev_img = img
        self._prev_name = name
        # If full-screen is 0, consider cursor_score
        return (cursor_score if score == 0 else score), psnr_val
