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


def _ax_selected_text(pid: int) -> str | None:
    from ApplicationServices import (
        AXUIElementCreateApplication,
        AXUIElementCopyAttributeValue,
        kAXFocusedUIElementAttribute,
        kAXSelectedTextAttribute,
    )
    app_elem = AXUIElementCreateApplication(pid)
    err, focused = AXUIElementCopyAttributeValue(app_elem, kAXFocusedUIElementAttribute, None)
    if err or focused is None:
        return None
    err, text = AXUIElementCopyAttributeValue(focused, kAXSelectedTextAttribute, None)
    if err or not text:
        return None
    text = str(text).strip()
    return text if text else None


def get_clipboard_text() -> str | None:
    """Return current clipboard text, or None if empty/non-text."""
    try:
        from AppKit import NSPasteboard, NSStringPboardType
        pb = NSPasteboard.generalPasteboard()
        text = pb.stringForType_(NSStringPboardType)
        if text:
            text = str(text).strip()
            return text if text else None
        return None
    except Exception:
        return None


def get_clipboard_change_count() -> int:
    """Return the clipboard change count (increments on each copy)."""
    try:
        from AppKit import NSPasteboard
        return NSPasteboard.generalPasteboard().changeCount()
    except Exception:
        return 0
