"""JARVIS daemon: continuous screen monitoring with AI assistance."""

import base64
import io
import json
import queue
import threading
import time
from datetime import datetime
from enum import Enum, auto

from PIL import Image

from activity import ActivityTracker
from capture import capture_screen, get_clipboard_text, get_clipboard_change_count
from display import show_overlay
from monitor import FrameMonitor
from pet import run_pet_loop
from response import get_hint, get_response, get_selection_hint
from stats import log_activity_call, log_llm_call, update_llm_reaction

MONITOR_INDEX = 1
STATIC_THRESHOLD = 5       # seconds of dHash==0 before stuck-screen trigger
SWITCH_THRESHOLD = 20      # dHash score above this = context switch

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
            log_activity_call(record.id, total_ms, in_tok, out_tok,
                              app=app, summary=summary,
                              screenshot_file=record.screenshot_file)
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


def main(ui_queue: queue.Queue, paused: list, on_capture_ref: list,
         tk_root_ref: list | None = None, static_count: list | None = None,
         pet_pos_ref: list | None = None, thinking_ref: list | None = None):
    state = [State.CAPTURING]
    # paused is passed in (shared with pet)
    frame_monitor = FrameMonitor()
    activity_tracker = ActivityTracker()
    if static_count is None:
        static_count = [0]
    triggered_b64 = [None]
    pending_hint = queue.Queue()  # HintResult posted from background thread

    # Clipboard tracking
    last_clipboard_count = [get_clipboard_change_count()]
    last_triggered_clipboard = [None]  # text of last clipboard that triggered a hint

    # Context-switch tracking
    prev_image_bytes = [None]
    in_post_switch = [False]
    post_switch_scores = []
    pending_activity_bytes = [None]
    pending_overlay = [None]  # ("previous_work", record) | ("recap", records)

    lock_thread = threading.Thread(target=_start_lock_listener, args=(state,), daemon=True)
    lock_thread.start()

    def _show_overlay_main(text, on_more, on_chat, on_stream_done=None):
        """Run show_overlay — posts UI work to main thread, blocks background thread until closed."""
        return show_overlay(text, on_more=on_more, on_chat=on_chat,
                            on_stream_done=on_stream_done,
                            pet_pos_ref=pet_pos_ref,
                            on_thinking=_set_thinking,
                            _ui_queue=ui_queue)

    def _set_thinking(val: bool):
        if thinking_ref is not None:
            thinking_ref[0] = val
            if tk_root_ref and tk_root_ref[0]:
                ui_queue.put(lambda: tk_root_ref[0].contentView().setNeedsDisplay_(True))

    def _on_pet_capture():
        """Left-click on pet: capture screen after 1s and trigger hint."""
        if paused[0]:
            return
        print(f"[pet] capture triggered (state={state[0].name})")
        state[0] = State.OVERLAY
        try:
            b64, raw, cx, cy, sw, sh = capture_screen(monitor_index=MONITOR_INDEX)
        except Exception as e:
            print(f"[pet] capture error: {e}")
            state[0] = State.CAPTURING
            return
        triggered_b64[0] = b64
        _set_thinking(True)

        def _run():
            try:
                hint = get_hint(b64, cx, cy, sw, sh, 0)
                print(f"[pet] hint: needs={hint.needs_hint} conf={hint.confidence} reason={hint.reason}")
                pending_hint.put((hint, b64, raw, cx, cy, None, True))
            except Exception as e:
                print(f"[pet] hint error: {e}")
                state[0] = State.CAPTURING
            finally:
                _set_thinking(False)

        threading.Thread(target=_run, daemon=True).start()

    on_capture_ref[0] = _on_pet_capture

    print("JARVIS daemon started. Press Ctrl+C to stop.")

    while True:
        loop_start = time.monotonic()

        # Check for pending hint result (from background get_hint thread)
        try:
            item = pending_hint.get_nowait()
            hint, h_b64, h_bytes, h_cx, h_cy, h_selection = item[:6]
            forced = item[6] if len(item) > 6 else False
            show = hint.needs_hint and hint.confidence != "low"
            if not show and not forced:
                print(f"[hint] skipped: needs={hint.needs_hint} conf={hint.confidence} reason={hint.reason}")
                state[0] = State.CAPTURING
            else:
                log_key = log_llm_call("stuck", hint.total_ms, hint.total_ms,
                                       hint.input_tokens, hint.output_tokens,
                                       response_text=hint.hint, image_bytes=h_bytes,
                                       cursor_x=h_cx, cursor_y=h_cy,
                                       selected_text=h_selection)

                def on_more(b64=h_b64):
                    try:
                        text, in_tok, out_tok, ttft, total = get_response(b64, prompt=MORE_PROMPT)
                        log_llm_call("more", ttft, total, in_tok, out_tok, response_text=text)
                    except Exception as e:
                        text = f"Error: {e}"
                    return text

                def on_chat(msg: str, b64=h_b64):
                    try:
                        text, in_tok, out_tok, ttft, total = get_response(b64, prompt=msg)
                        log_llm_call("chat", ttft, total, in_tok, out_tok,
                                     response_text=text, selected_text=msg)
                    except Exception as e:
                        text = f"Error: {e}"
                    return text

                if not hint.needs_hint:
                    overlay_text = f"*(nothing specific to suggest)* {hint.reason}"
                elif hint.confidence == "medium":
                    overlay_text = f"*({hint.category})* {hint.hint}"
                else:
                    overlay_text = hint.hint

                reaction = _show_overlay_main(overlay_text, on_more=on_more, on_chat=on_chat)
                update_llm_reaction(log_key, reaction)
                frame_monitor.reset()
                state[0] = State.CAPTURING
        except queue.Empty:
            pass

        # Check for pending overlay (from activity tracking)
        if pending_overlay[0] is not None and state[0] == State.CAPTURING:
            kind, data = pending_overlay[0]
            pending_overlay[0] = None
            state[0] = State.OVERLAY
            if kind == "previous_work":
                overlay_text = _format_previous_work(data)
                snap_b64 = triggered_b64[0]
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
                        log_llm_call("chat", ttft, total, in_tok, out_tok,
                                     response_text=text, selected_text=msg)
                    except Exception as e:
                        text = f"Error: {e}"
                    return text
                return on_chat

            _show_overlay_main(overlay_text, on_more=_make_more(), on_chat=_make_chat())
            frame_monitor.reset()
            state[0] = State.CAPTURING

        if state[0] == State.OVERLAY:
            time.sleep(1)
            continue

        if state[0] == State.LOCKED:
            time.sleep(1)
            continue

        if paused[0]:
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
            image_b64, image_bytes, cx, cy, screen_w, screen_h = capture_screen(monitor_index=MONITOR_INDEX)
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
            static_count[0] += 1
        else:
            static_count[0] = 0

        psnr_str = "inf" if psnr == float("inf") else f"{psnr:.1f}"
        print(f"[{ts.strftime('%H:%M:%S')}] dHash={score} PSNR={psnr_str} static={static_count[0]}s")

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

        # --- Clipboard-based hint (new copy detected) ---
        if state[0] == State.CAPTURING and not paused[0]:
            current_count = get_clipboard_change_count()
            if current_count != last_clipboard_count[0]:
                last_clipboard_count[0] = current_count
                clipboard_text = get_clipboard_text()
                if clipboard_text and clipboard_text != last_triggered_clipboard[0]:
                    last_triggered_clipboard[0] = clipboard_text
                    state[0] = State.OVERLAY
                    triggered_b64[0] = image_b64
                    triggered_bytes = image_bytes
                    _cx, _cy = cx, cy
                    _sel = clipboard_text
                    print(f"Clipboard copy detected — querying hint for {_sel[:60]!r}...")

                    def _run_selection_hint(b64=triggered_b64[0], raw=triggered_bytes, sel=_sel):
                        try:
                            hint = get_selection_hint(sel)
                            print(f"[hint] needs={hint.needs_hint} conf={hint.confidence} reason={hint.reason}")
                            pending_hint.put((hint, b64, raw, _cx, _cy, sel))
                        except Exception as e:
                            print(f"[hint] error: {e}")
                            state[0] = State.CAPTURING

                    threading.Thread(target=_run_selection_hint, daemon=True).start()

        # --- Stuck-screen detection ---
        if static_count[0] >= STATIC_THRESHOLD and state[0] == State.CAPTURING and not paused[0]:
            state[0] = State.OVERLAY
            static_count[0] = 0
            triggered_b64[0] = image_b64
            triggered_bytes = image_bytes
            _cx, _cy, _sw, _sh = cx, cy, screen_w, screen_h
            _idle = STATIC_THRESHOLD

            print(f"Static screen detected — querying hint (cursor={_cx},{_cy})...")

            def _run_hint(b64=triggered_b64[0], raw=triggered_bytes):
                try:
                    hint = get_hint(b64, _cx, _cy, _sw, _sh, _idle)
                    print(f"[hint] needs={hint.needs_hint} conf={hint.confidence} cat={hint.category}: {hint.reason}")
                    pending_hint.put((hint, b64, raw, _cx, _cy, None))
                except Exception as e:
                    print(f"[hint] error: {e}")
                    state[0] = State.CAPTURING

            threading.Thread(target=_run_hint, daemon=True).start()

        elapsed = time.monotonic() - loop_start
        sleep_time = 1.0 - elapsed
        if sleep_time > 0:
            time.sleep(sleep_time)


if __name__ == "__main__":
    ui_queue: queue.Queue = queue.Queue()
    paused_shared = [False]
    on_capture_ref = [lambda: None]
    tk_root_ref = [None]
    static_count_shared = [0]
    pet_pos_ref = [0, 0, 0, 0]
    thinking_ref = [False]

    t = threading.Thread(
        target=main, args=(ui_queue, paused_shared, on_capture_ref, tk_root_ref, static_count_shared, pet_pos_ref, thinking_ref), daemon=True)
    t.start()

    run_pet_loop(
        on_capture=lambda: on_capture_ref[0](),
        paused_ref=paused_shared,
        ui_queue=ui_queue,
        root_ref=tk_root_ref,
        on_pause=lambda is_paused: static_count_shared.__setitem__(0, 0),
        pet_pos_ref=pet_pos_ref,
        thinking_ref=thinking_ref,
    )
