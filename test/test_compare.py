import csv
import os
import sys
import time
from pathlib import Path

import imagehash
from PIL import Image

SCREENSHOTS_DIR = Path("/Users/menghua/Research/desktop-JARVIS/stats/screenshots")
OUTPUT_CSV = Path("/Users/menghua/Research/desktop-JARVIS/stats/compare.csv")


def dhash(img: Image.Image) -> imagehash.ImageHash:
    return imagehash.dhash(img, hash_size=8)


def main():
    files = sorted(SCREENSHOTS_DIR.glob("*.png"))
    if len(files) < 2:
        print("Need at least 2 screenshots to compare.")
        return

    print(f"Found {len(files)} screenshots. Comparing consecutive frames...")

    with open(OUTPUT_CSV, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["compare", "original", "result", "calculation_time"])

        prev_img = Image.open(files[0])
        prev_hash = dhash(prev_img)
        prev_name = files[0].name

        for curr_file in files[1:]:
            start = time.perf_counter()

            curr_img = Image.open(curr_file)
            curr_hash = dhash(curr_img)
            hamming = prev_hash - curr_hash

            elapsed = time.perf_counter() - start

            writer.writerow([curr_file.name, prev_name, hamming, f"{elapsed:.6f}"])
            print(f"{prev_name} -> {curr_file.name}: distance={hamming}, time={elapsed:.4f}s")

            prev_img = curr_img
            prev_hash = curr_hash
            prev_name = curr_file.name

    print(f"\nResults saved to {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
