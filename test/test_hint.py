"""Debug hint prompt: test get_hint (screenshot) and get_selection_hint (selected text).

Usage:
  # Test screenshot-based hint (default):
  python test/test_hint.py [screenshot.png] [cx] [cy]

  # Test selection-based hint:
  python test/test_hint.py --select "HPCC"
  python test/test_hint.py --select "gradient descent is used to minimize the loss function"
  python test/test_hint.py --select "for i in range(len(arr)): arr[i] *= 2"
"""
import sys
import os
import base64
import json
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from response import get_hint, get_selection_hint, _HINT_SYSTEM, _SELECTION_SYSTEM
from stats import log_llm_call

ROOT = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUTPUT_DIR = ROOT / "stats" / "test_hints"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# --- Dispatch: --select mode vs screenshot mode ---
if len(sys.argv) > 1 and sys.argv[1] == "--select":
    selected_text = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else "HPCC"

    print(f"Selected text: {selected_text!r}")
    print()
    print("=== SYSTEM PROMPT ===")
    print(_SELECTION_SYSTEM)
    print("=== USER MESSAGE ===")
    print(f'Selected text:\n"""\n{selected_text}\n"""')
    print()
    print("Calling LLM...")

    hint = get_selection_hint(selected_text)

    result = {
        "mode": "selection",
        "selected_text": selected_text,
        "needs_hint": hint.needs_hint,
        "confidence": hint.confidence,
        "category": hint.category,
        "reason": hint.reason,
        "hint": hint.hint,
        "input_tokens": hint.input_tokens,
        "output_tokens": hint.output_tokens,
        "total_ms": round(hint.total_ms, 1),
    }
    stem = "selection_" + selected_text[:30].replace(" ", "_")
    log_llm_call("selection", hint.total_ms, hint.total_ms,
                 hint.input_tokens, hint.output_tokens,
                 response_text=hint.hint, selected_text=selected_text)

else:
    SCREENSHOT = Path(sys.argv[1]) if len(sys.argv) > 1 else (
        ROOT / "stats" / "screenshots" / "20260522_100645_206982.png"
    )
    CX = int(sys.argv[2]) if len(sys.argv) > 2 else 735
    CY = int(sys.argv[3]) if len(sys.argv) > 3 else 482
    IDLE_S = 5

    from PIL import Image as PILImage
    import io
    img_bytes = SCREENSHOT.read_bytes()
    b64 = base64.standard_b64encode(img_bytes).decode()
    img = PILImage.open(io.BytesIO(img_bytes))
    SW, SH = img.size

    print(f"Image : {SCREENSHOT.name}  ({SW}x{SH})")
    print(f"Cursor: ({CX}, {CY})")
    print()
    print("=== SYSTEM PROMPT ===")
    print(_HINT_SYSTEM)
    print("=== USER MESSAGE ===")
    print(
        f"Cursor is at ({CX}, {CY}) on a {SW}×{SH} screen. "
        f"The user has been idle for {IDLE_S} seconds. "
        "What are they likely stuck on near the cursor? Give one specific, actionable hint."
    )
    print()
    print("Calling LLM...")

    hint = get_hint(b64, CX, CY, SW, SH, IDLE_S)

    result = {
        "mode": "screenshot",
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
    stem = SCREENSHOT.stem

print("=== RESULT ===")
for k, v in result.items():
    print(f"{k:<15}: {v}")

ts = datetime.now().strftime("%Y%m%d_%H%M%S")
out_file = OUTPUT_DIR / f"{ts}_{stem}.json"
out_file.write_text(json.dumps(result, indent=2, ensure_ascii=False))
print(f"\nSaved → {out_file}")
