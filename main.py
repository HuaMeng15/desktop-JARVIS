"""JARVIS daemon: continuous screen monitoring with AI assistance."""

import base64
import io
import json
import threading
import time
from datetime import datetime
from enum import Enum, auto

from PIL import Image

from activity import ActivityTracker
from capture import capture_screen
from display import show_overlay
from monitor import FrameMonitor
from response import get_response, stream_response
from stats import log_activity_call, log_llm_call

MONITOR_INDEX = 1
STATIC_THRESHOLD = 5       # seconds of dHash==0 before stuck-screen trigger
SWITCH_THRESHOLD = 20      # dHash score above this = context switch

STUCK_PROMPT = (
    "I have been on this screen without any activity for over 5 seconds. "
    "First, in one sentence, summarize what I appear to be doing or working on. "
    "Then provide 2-3 concise, specific, actionable tips for what I might do next. "
    "Be specific to what you see — avoid generic advice."
)

MORE_PROMPT = (
    "Give more detailed advice about what I should do on this screen. "
    "Expand on your previous suggestions with concrete next steps."
)

ACTIVITY_PROMPT = (
    'Look at this screenshot. Reply with a JSON object only, no other text:\n'
    '{"app": "<application name>", "summary": "<one sentence: what the user is doing>"}\n'
    'Example: {"app": "VS Code", "summary": "writing a socket codec in Python"}'
)


class State(Enum):
    CAPTURING = auto()
    OVERLAY = auto()
    LOCKED = auto()
    DISPLAY_SLEEP = auto()


def _start_lock_listener(state_ref: list):
    try:
        from Foundation import NSDistributedNotificationCenter, NSRunLoop, NSDate
        center = NSDistributedNotificationCenter.defaultCenter()

        def on_lock(_):
            print("Screen locked — pausing capture.")
            state_ref[0] = State.LOCKED

        def on_unlock(_):
            print("Screen unlocked — resuming capture.")
            if state_ref[0] == State.LOCKED:
                state_ref[0] = State.CAPTURING

        center.addObserverForName_object_queue_usingBlock_(
            "com.apple.screenIsLocked", None, None, on_lock)
        center.addObserverForName_object_queue_usingBlock_(
            "com.apple.screenIsUnlocked", None, None, on_unlock)

        loop = NSRunLoop.currentRunLoop()
        while True:
            loop.runUntilDate_(NSDate.dateWithTimeIntervalSinceNow_(1.0))
    except Exception as e:
        print(f"Lock listener unavailable: {e}")


def _query_activity_background(image_bytes: bytes, tracker: ActivityTracker):
    """Silently summarize a screenshot and upsert into activity tracker."""
    def worker():
        try:
            image_b64 = base64.standard_b64encode(image_bytes).decode()
            img = Image.open(io.BytesIO(image_bytes))
            start = time.monotonic()
            text, in_tok, out_tok, _, total = get_response(image_b64, prompt=ACTIVITY_PROMPT)
            total_ms = (time.monotonic() - start) * 1000
            data = json.loads(text.strip())
            app = data.get("app", "Unknown")
            summary = data.get("summary", text[:100])
            record = tracker.upsert(img, image_bytes, app, summary)
            log_activity_call(record.id, total_ms, in_tok, out_tok)
            print(f"[activity] {app}: {summary}")
        except Exception as e:
            print(f"[activity] query failed: {e}")
    threading.Thread(target=worker, daemon=True).start()


def _format_previous_work(record) -> str:
    return (
        f"**Your previous work:** {record.app}\n\n"
        f"{record.summary}\n\n"
        f"*Last seen: {record.last_seen[:16].replace('T', ' ')}*"
    )


def _format_recap(records) -> str:
    lines = ["**Recent activity recap:**\n"]
    for r in records:
        ts = r.last_seen[:16].replace("T", " ")
        lines.append(f"- **{r.app}** ({ts}): {r.summary}")
    return "\n".join(lines)


def main():
    state = [State.CAPTURING]
    frame_monitor = FrameMonitor()
    activity_tracker = ActivityTracker()
    static_count = 0
    triggered_b64 = [None]

    # Context-switch tracking
    prev_image_bytes = [None]
    in_post_switch = [False]
    post_switch_scores = []
    pending_activity_bytes = [None]
    pending_overlay = [None]  # ("previous_work", record) | ("recap", records)

    lock_thread = threading.Thread(target=_start_lock_listener, args=(state,), daemon=True)
    lock_thread.start()

    print("JARVIS daemon started. Press Ctrl+C to stop.")

    while True:
        loop_start = time.monotonic()

        # Check for pending overlay (from activity tracking)
        if pending_overlay[0] is not None and state[0] == State.CAPTURING:
            kind, data = pending_overlay[0]
            pending_overlay[0] = None
            state[0] = State.OVERLAY
            if kind == "previous_work":
                overlay_text = _format_previous_work(data)
                snap_b64 = base64.standard_b64encode(data.screenshot_file.encode()).decode() if False else triggered_b64[0]
            else:
                overlay_text = _format_recap(data)
                snap_b64 = None

            def _make_more(b64=snap_b64):
                def on_more():
                    if not b64:
                        return "No screenshot available for follow-up."
                    try:
                        text, in_tok, out_tok, ttft, total = get_response(b64, prompt=MORE_PROMPT)
                        log_llm_call("more", ttft, total, in_tok, out_tok, response_text=text)
                    except Exception as e:
                        text = f"Error: {e}"
                    return text
                return on_more

            def _make_chat(b64=snap_b64):
                def on_chat(msg: str):
                    if not b64:
                        return "No screenshot available for follow-up."
                    try:
                        text, in_tok, out_tok, ttft, total = get_response(b64, prompt=msg)
                        log_llm_call("chat", ttft, total, in_tok, out_tok, response_text=text)
                    except Exception as e:
                        text = f"Error: {e}"
                    return text
                return on_chat

            show_overlay(overlay_text, on_more=_make_more(), on_chat=_make_chat())
            frame_monitor.reset()
            state[0] = State.CAPTURING

        if state[0] == State.OVERLAY:
            time.sleep(1)
            continue

        if state[0] == State.LOCKED:
            time.sleep(1)
            continue

        if state[0] == State.DISPLAY_SLEEP:
            try:
                capture_screen(monitor_index=MONITOR_INDEX)
                print("Display woke — resuming capture.")
                state[0] = State.CAPTURING
                frame_monitor.reset()
            except Exception:
                pass
            time.sleep(2)
            continue

        # Capture
        try:
            image_b64, image_bytes = capture_screen(monitor_index=MONITOR_INDEX)
        except IndexError:
            print("Display slept — pausing capture.")
            state[0] = State.DISPLAY_SLEEP
            time.sleep(2)
            continue
        except Exception as e:
            print(f"Capture error: {e}")
            time.sleep(1)
            continue

        ts = datetime.now()
        name = ts.strftime("%Y%m%d_%H%M%S_%f") + ".png"
        img = Image.open(io.BytesIO(image_bytes))

        frame_monitor.save_frame(image_bytes, name)
        score, psnr = frame_monitor.update(img, name)

        if score == 0:
            static_count += 1
        else:
            static_count = 0

        psnr_str = "inf" if psnr == float("inf") else f"{psnr:.1f}"
        print(f"[{ts.strftime('%H:%M:%S')}] dHash={score} PSNR={psnr_str} static={static_count}s")

        # --- Context-switch detection ---
        if score > SWITCH_THRESHOLD and not in_post_switch[0]:
            in_post_switch[0] = True
            post_switch_scores.clear()
            pending_activity_bytes[0] = prev_image_bytes[0]  # "from" screenshot
            print(f"[activity] Context switch detected (dHash={score})")

        elif in_post_switch[0]:
            post_switch_scores.append(score)
            if len(post_switch_scores) >= 2:
                in_post_switch[0] = False
                settled = all(s < 10 for s in post_switch_scores)

                if settled:
                    # Fire ONE background summary of the "from" page
                    if pending_activity_bytes[0] is not None:
                        _query_activity_background(pending_activity_bytes[0], activity_tracker)
                        pending_activity_bytes[0] = None
                    # Check if current page matches a known task
                    match = activity_tracker.match(img)
                    if match:
                        print(f"[activity] Matched previous task: {match.app}")
                        pending_overlay[0] = ("previous_work", match)
                else:
                    # Still wandering — show recap, skip summary query
                    pending_activity_bytes[0] = None
                    recent = activity_tracker.recent(hours=2)
                    if recent:
                        print(f"[activity] Wandering — showing recap of {len(recent)} tasks")
                        pending_overlay[0] = ("recap", recent)

        prev_image_bytes[0] = image_bytes

        # --- Stuck-screen detection ---
        if static_count >= STATIC_THRESHOLD and state[0] == State.CAPTURING:
            state[0] = State.OVERLAY
            static_count = 0
            triggered_b64[0] = image_b64
            triggered_bytes = image_bytes

            print("Static screen detected — streaming to overlay...")
            try:
                stream = stream_response(image_b64, prompt=STUCK_PROMPT)
            except Exception as e:
                state[0] = State.CAPTURING
                print(f"Stream error: {e}")
                continue

            def on_stream_done(stats, text):
                in_tok, out_tok, ttft, total = stats
                log_llm_call("stuck", ttft, total, in_tok, out_tok,
                             response_text=text, image_bytes=triggered_bytes)

            def on_more():
                try:
                    text, in_tok, out_tok, ttft, total = get_response(triggered_b64[0], prompt=MORE_PROMPT)
                    log_llm_call("more", ttft, total, in_tok, out_tok, response_text=text)
                except Exception as e:
                    text = f"Error: {e}"
                return text

            def on_chat(msg: str):
                try:
                    text, in_tok, out_tok, ttft, total = get_response(triggered_b64[0], prompt=msg)
                    log_llm_call("chat", ttft, total, in_tok, out_tok, response_text=text)
                except Exception as e:
                    text = f"Error: {e}"
                return text

            show_overlay(stream, on_more=on_more, on_chat=on_chat, on_stream_done=on_stream_done)
            frame_monitor.reset()
            state[0] = State.CAPTURING

        elapsed = time.monotonic() - loop_start
        sleep_time = 1.0 - elapsed
        if sleep_time > 0:
            time.sleep(sleep_time)


if __name__ == "__main__":
    main()


MONITOR_INDEX = 1
STATIC_THRESHOLD = 5  # seconds of dHash==0 before triggering LLM

STUCK_PROMPT = (
    "I have been on this screen without any activity for over 5 seconds. "
    "First, in one sentence, summarize what I appear to be doing or working on. "
    "Then provide 2-3 concise, specific, actionable tips for what I might do next. "
    "Be specific to what you see — avoid generic advice."
)

MORE_PROMPT = (
    "Give more detailed advice about what I should do on this screen. "
    "Expand on your previous suggestions with concrete next steps."
)


class State(Enum):
    CAPTURING = auto()
    OVERLAY = auto()
    LOCKED = auto()       # screen locked — wait for screenIsUnlocked notification
    DISPLAY_SLEEP = auto() # display off — probe to detect wake


def _start_lock_listener(state_ref: list):
    """Listen for macOS screen lock/unlock via distributed notifications."""
    try:
        from Foundation import NSDistributedNotificationCenter, NSRunLoop, NSDate

        center = NSDistributedNotificationCenter.defaultCenter()

        def on_lock(_):
            print("Screen locked — pausing capture.")
            state_ref[0] = State.LOCKED

        def on_unlock(_):
            print("Screen unlocked — resuming capture.")
            if state_ref[0] == State.LOCKED:
                state_ref[0] = State.CAPTURING

        center.addObserverForName_object_queue_usingBlock_(
            "com.apple.screenIsLocked", None, None, on_lock)
        center.addObserverForName_object_queue_usingBlock_(
            "com.apple.screenIsUnlocked", None, None, on_unlock)

        loop = NSRunLoop.currentRunLoop()
        while True:
            loop.runUntilDate_(NSDate.dateWithTimeIntervalSinceNow_(1.0))
    except Exception as e:
        print(f"Lock listener unavailable: {e}")


def main():
    state = [State.CAPTURING]
    frame_monitor = FrameMonitor()
    static_count = 0
    triggered_b64 = [None]  # screenshot that triggered the overlay

    lock_thread = threading.Thread(target=_start_lock_listener, args=(state,), daemon=True)
    lock_thread.start()

    print("JARVIS daemon started. Press Ctrl+C to stop.")

    while True:
        loop_start = time.monotonic()

        if state[0] == State.OVERLAY:
            time.sleep(1)
            continue

        if state[0] == State.LOCKED:
            # Locked via notification — wait for screenIsUnlocked, no probing needed
            time.sleep(1)
            continue

        if state[0] == State.DISPLAY_SLEEP:
            # Display slept — probe every 2s to detect wake
            try:
                capture_screen(monitor_index=MONITOR_INDEX)
                print("Display woke — resuming capture.")
                state[0] = State.CAPTURING
                frame_monitor.reset()
            except Exception:
                pass
            time.sleep(2)
            continue

        # Capture
        try:
            image_b64, image_bytes = capture_screen(monitor_index=MONITOR_INDEX)
        except IndexError:
            # Monitor unavailable — display slept (not locked)
            print("Display slept — pausing capture.")
            state[0] = State.DISPLAY_SLEEP
            time.sleep(2)
            continue
        except Exception as e:
            print(f"Capture error: {e}")
            time.sleep(1)
            continue

        ts = datetime.now()
        name = ts.strftime("%Y%m%d_%H%M%S_%f") + ".png"
        img = Image.open(io.BytesIO(image_bytes))

        frame_monitor.save_frame(image_bytes, name)
        score, psnr = frame_monitor.update(img, name)

        if score == 0:
            static_count += 1
        else:
            static_count = 0

        psnr_str = "inf" if psnr == float("inf") else f"{psnr:.1f}"
        print(f"[{ts.strftime('%H:%M:%S')}] dHash={score} PSNR={psnr_str} static={static_count}s")

        if static_count >= STATIC_THRESHOLD and state[0] == State.CAPTURING:
            state[0] = State.OVERLAY
            static_count = 0
            triggered_b64[0] = image_b64
            triggered_bytes = image_bytes  # keep raw bytes for stats

            print("Static screen detected — streaming to overlay...")
            try:
                stream = stream_response(image_b64, prompt=STUCK_PROMPT)
            except Exception as e:
                state[0] = State.CAPTURING
                print(f"Stream error: {e}")
                continue

            accumulated_text = [""]

            def on_stream_done(stats, text):
                in_tok, out_tok, ttft, total = stats
                log_llm_call("stuck", ttft, total, in_tok, out_tok,
                             response_text=text,
                             image_bytes=triggered_bytes)

            def on_more():
                try:
                    text, in_tok, out_tok, ttft, total = get_response(triggered_b64[0], prompt=MORE_PROMPT)
                    log_llm_call("more", ttft, total, in_tok, out_tok, response_text=text)
                except Exception as e:
                    text = f"Error: {e}"
                return text

            def on_chat(msg: str):
                try:
                    text, in_tok, out_tok, ttft, total = get_response(triggered_b64[0], prompt=msg)
                    log_llm_call("chat", ttft, total, in_tok, out_tok, response_text=text)
                except Exception as e:
                    text = f"Error: {e}"
                return text

            show_overlay(stream, on_more=on_more, on_chat=on_chat, on_stream_done=on_stream_done)
            frame_monitor.reset()
            state[0] = State.CAPTURING

        elapsed = time.monotonic() - loop_start
        sleep_time = 1.0 - elapsed
        if sleep_time > 0:
            time.sleep(sleep_time)


if __name__ == "__main__":
    main()
