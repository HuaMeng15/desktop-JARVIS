import base64
import io
import mss
from PIL import Image


def capture_screen(monitor_index: int = 1) -> tuple[str, bytes, int, int, int, int]:
    """Capture the screen and return (base64 PNG, raw bytes, cursor_x, cursor_y, screen_w, screen_h)."""
    from AppKit import NSEvent
    loc = NSEvent.mouseLocation()
    with mss.mss() as sct:
        monitor = sct.monitors[monitor_index]
        screenshot = sct.grab(monitor)
        img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")

    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    raw = buffer.getvalue()
    b64 = base64.standard_b64encode(raw).decode("utf-8")
    w, h = img.size
    # Quartz y is bottom-up; convert to top-down
    cx = int(loc.x)
    cy = h - int(loc.y)
    return b64, raw, cx, cy, w, h
