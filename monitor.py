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
_CSV_FIELDS = ["current_name", "previous_name", "score", "psnr"]


def _psnr(a: Image.Image, b: Image.Image) -> float:
    arr_a = np.array(a, dtype=np.float32)
    arr_b = np.array(b, dtype=np.float32)
    mse = np.mean((arr_a - arr_b) ** 2)
    if mse == 0:
        return float("inf")
    return 20 * np.log10(255.0 / np.sqrt(mse))


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

    def update(self, img: Image.Image, name: str) -> tuple[int, float]:
        """Compare img with previous frame. Returns (dhash_distance, psnr)."""
        curr_hash = imagehash.dhash(img)
        score = 0
        psnr_val = float("inf")

        if self._prev_img is not None:
            score = curr_hash - imagehash.dhash(self._prev_img)
            psnr_val = _psnr(self._prev_img, img)
            with open(RECORD_CSV, "a", newline="") as f:
                csv.DictWriter(f, fieldnames=_CSV_FIELDS).writerow({
                    "current_name": name,
                    "previous_name": self._prev_name,
                    "score": score,
                    "psnr": f"{psnr_val:.2f}" if psnr_val != float("inf") else "inf",
                })

        self._prev_img = img
        self._prev_name = name
        return score, psnr_val
