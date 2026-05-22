"""Debug hint prompt: pass a screenshot file directly to the LLM and print/save results."""
import sys
import os
import base64
import json
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from response import get_hint, _HINT_SYSTEM

# --- Config ---
SCREENSHOT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))) +
    "/stats/screenshots/20260522_100645_206982.png"
)
# Cursor position: pass as args or edit defaults here
CX = int(sys.argv[2]) if len(sys.argv) > 2 else 735
CY = int(sys.argv[3]) if len(sys.argv) > 3 else 482
IDLE_S = 5

OUTPUT_DIR = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))) / "stats" / "test_hints"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# --- Load image ---
img_bytes = SCREENSHOT.read_bytes()
b64 = base64.standard_b64encode(img_bytes).decode()

# Infer screen size from image
from PIL import Image as PILImage
import io
img = PILImage.open(io.BytesIO(img_bytes))
SW, SH = img.size

print(f"Image : {SCREENSHOT.name}  ({SW}x{SH})")
print(f"Cursor: ({CX}, {CY})")
print()
print("=== SYSTEM PROMPT ===")
print(_HINT_SYSTEM)

user_text = (
    f"Cursor is at ({CX}, {CY}) on a {SW}×{SH} screen. "
    f"The user has been idle for {IDLE_S} seconds. "
    f"What are they likely stuck on near the cursor? Give one specific, actionable hint."
    f"If there's highlighted text near the cursor, the hint should be about that text. "
    f"If there's not enough information to give a hint, say 'needs_hint: false' and give your best guess in the reason field."
)
print("=== USER MESSAGE ===")
print(user_text)
print()
print("Calling LLM...")

hint = get_hint(b64, CX, CY, SW, SH, IDLE_S)

result = {
    "screenshot": str(SCREENSHOT),
    "cursor_x": CX, "cursor_y": CY,
    "screen_w": SW, "screen_h": SH,
    "needs_hint": hint.needs_hint,
    "confidence": hint.confidence,
    "category": hint.category,
    "reason": hint.reason,
    "hint": hint.hint,
    "input_tokens": hint.input_tokens,
    "output_tokens": hint.output_tokens,
    "total_ms": round(hint.total_ms, 1),
}

print("=== RESULT ===")
for k, v in result.items():
    print(f"{k:<15}: {v}")

# Save to file
ts = datetime.now().strftime("%Y%m%d_%H%M%S")
out_file = OUTPUT_DIR / f"{ts}_{SCREENSHOT.stem}.json"
out_file.write_text(json.dumps(result, indent=2, ensure_ascii=False))
print(f"\nSaved → {out_file}")
