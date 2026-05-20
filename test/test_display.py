"""Quick display test — runs show_overlay with fake streaming."""
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from display import show_overlay

SAMPLE = """## Summary
You are reading a Python file in your editor.

**Tips:**
- Try running the tests with `pytest`
- Check the **TODO** comments in the file
- Consider refactoring the long function on line 42
"""

def fake_stream():
    for word in SAMPLE.split(" "):
        time.sleep(0.05)
        yield word + " "
    yield (100, 20, 800.0, 3200.0)  # fake stats tuple

def on_more():
    time.sleep(1)
    return "Here is more detailed advice about what you should do next."

def on_chat(msg):
    time.sleep(1)
    return f"You asked: '{msg}'\n\nHere is my response to your question."

if __name__ == "__main__":
    result = show_overlay(fake_stream(), on_more=on_more, on_chat=on_chat,
                          on_stream_done=lambda s: print(f"Stream done: {s}"))
    print(f"Closed with: {result}")
