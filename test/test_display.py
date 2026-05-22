"""Quick display test — runs show_overlay with a static hint string."""
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from display import show_overlay

HINT = "*(coding)* That `TypeError` on line 42 means `data` is None — add a null check before the loop."

def on_more():
    time.sleep(1)
    return "**More detail:**\n\nThe variable `data` comes from `fetch_records()` which returns `None` on an empty result set. Add `if data is None: return []` at the top of the function."

def on_chat(msg):
    time.sleep(1)
    return f"You asked: '{msg}'\n\nHere is my response."

if __name__ == "__main__":
    result = show_overlay(HINT, on_more=on_more, on_chat=on_chat)
    print(f"Closed with: {result}")
