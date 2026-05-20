import base64
import io
import mss
from PIL import Image


def capture_screen(monitor_index: int = 1) -> tuple[str, bytes]:
    """Capture the screen and return (base64-encoded PNG string, raw PNG bytes)."""
    with mss.mss() as sct:
        monitor = sct.monitors[monitor_index]
        screenshot = sct.grab(monitor)
        img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")

    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    raw = buffer.getvalue()
    return base64.standard_b64encode(raw).decode("utf-8"), raw
