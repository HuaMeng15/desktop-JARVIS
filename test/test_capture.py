import time
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from capture import capture_screen

STATS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "stats")
FPS = 1


def main():
    os.makedirs(STATS_DIR, exist_ok=True)
    print(f"Saving screenshots to {STATS_DIR} at {FPS} fps. Press Ctrl+C to stop.")

    while True:
        start = time.monotonic()

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        _, raw = capture_screen()
        path = os.path.join(STATS_DIR, f"screen_{timestamp}.png")
        with open(path, "wb") as f:
            f.write(raw)
        print(f"Saved {path}")

        elapsed = time.monotonic() - start
        sleep_time = (1.0 / FPS) - elapsed
        if sleep_time > 0:
            time.sleep(sleep_time)
        if sleep_time < 0:
            print(f"Warning: Capture took {elapsed:.2f}s, which is longer than the frame interval.")


if __name__ == "__main__":
    main()
