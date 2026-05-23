"""Manual display tests — run directly to visually inspect UI components.

Usage:
  python test/test_display.py overlay   # test hint overlay
  python test/test_display.py pet       # test desktop pet (no LLM)
  python test/test_display.py both      # pet + overlay together
"""
import queue
import sys
import os
import time
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Re-exec via Python.app if needed (required for AppKit GUI on macOS)
_PYTHON_APP = (
    "/opt/homebrew/Cellar/python@3.14/3.14.5/Frameworks/Python.framework"
    "/Versions/3.14/Resources/Python.app/Contents/MacOS/Python"
)
if sys.executable != _PYTHON_APP and os.path.exists(_PYTHON_APP):
    import subprocess
    venv_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "venv")
    site_pkgs = subprocess.check_output(
        [f"{venv_dir}/bin/python", "-c", "import site; print(site.getsitepackages()[0])"],
        text=True).strip()
    env = os.environ.copy()
    env["PYTHONPATH"] = site_pkgs
    env["PYTHONNOUSERSITE"] = "1"
    try:
        sys.exit(subprocess.run([_PYTHON_APP, "-S"] + sys.argv, env=env).returncode)
    except KeyboardInterrupt:
        sys.exit(0)

# When re-exec'd with -S, manually add venv site-packages
if not any("site-packages" in p for p in sys.path):
    _venv = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "venv")
    sys.path.insert(0, os.environ.get("PYTHONPATH", ""))


HINT = "*(coding)* That `TypeError` on line 42 means `data` is None — add a null check before the loop."

def on_more():
    time.sleep(0.5)
    return "**More detail:**\n\nThe variable `data` comes from `fetch_records()` which returns `None` on an empty result set."

def on_chat(msg):
    time.sleep(0.5)
    return f"You asked: '{msg}'\n\nHere is a mock response."


def test_overlay():
    from display import show_overlay
    result = show_overlay(HINT, on_more=on_more, on_chat=on_chat)
    print(f"Overlay closed with: {result}")


def test_pet():
    """Show the desktop pet. Left-click shows hint overlay, right-click to pause/quit."""
    from pet import run_pet_loop
    from display import show_overlay

    ui_q = queue.Queue()
    paused = [False]

    def fake_capture():
        print("[pet] capture triggered — showing hint window")
        threading.Thread(
            target=lambda: show_overlay(HINT, on_more=on_more, on_chat=on_chat, _ui_queue=ui_q),
            daemon=True,
        ).start()

    run_pet_loop(
        on_capture=fake_capture,
        paused_ref=paused,
        ui_queue=ui_q,
        on_pause=lambda is_paused: print(f"[pet] {'paused' if is_paused else 'resumed'}"),
    )


def test_both():
    """Pet visible while overlay is shown — tests they coexist on the main thread."""
    from pet import run_pet_loop
    from display import show_overlay

    ui_q = queue.Queue()
    paused = [False]
    pet_pos_ref = [0, 0, 0, 0]
    active_close = [None]  # close fn for current overlay

    def fake_capture():
        print("[pet] capture triggered — showing hint window")
        close_ref = []
        active_close[0] = None
        threading.Thread(
            target=lambda: show_overlay(HINT, on_more=on_more, on_chat=on_chat,
                                        pet_pos_ref=pet_pos_ref, _ui_queue=ui_q,
                                        close_ref=close_ref),
            daemon=True,
        ).start()
        # show_overlay populates close_ref synchronously before blocking
        import time; time.sleep(0.05)
        if close_ref:
            active_close[0] = close_ref[0]

    def on_pause(is_paused):
        print(f"[pet] {'paused' if is_paused else 'resumed'}")
        if is_paused and active_close[0]:
            print(f"[pet] closing hint window, close_fn={active_close[0]}")
            active_close[0]()
            print("[pet] close called")

    run_pet_loop(
        on_capture=fake_capture,
        paused_ref=paused,
        ui_queue=ui_q,
        pet_pos_ref=pet_pos_ref,
        on_pause=on_pause,
    )


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "pet"
    {"overlay": test_overlay, "pet": test_pet, "both": test_both}.get(mode, test_pet)()
