"""Desktop pet: persistent tkinter widget, bottom-right corner.

Call run_pet_loop(on_capture, paused_ref, ui_queue) on the MAIN thread.
The JARVIS loop posts callables to ui_queue; the pet's after() loop drains it.
"""

import queue
import tkinter as tk

PET_SIZE = 48
PET_BG = "#2d2d2d"
PET_PAUSED_BG = "#8b0000"
PET_FG = "#ffffff"


def run_pet_loop(on_capture, paused_ref: list, ui_queue: queue.Queue) -> None:
    """Create the pet window and run tkinter mainloop. Blocks forever."""
    root = tk.Tk()
    root.overrideredirect(True)
    root.attributes("-topmost", True)
    root.attributes("-alpha", 0.85)
    root.resizable(False, False)

    try:
        from AppKit import NSApplication, NSApplicationActivationPolicyAccessory
        NSApplication.sharedApplication().setActivationPolicy_(
            NSApplicationActivationPolicyAccessory)
    except Exception:
        pass

    sw = root.winfo_screenwidth()
    sh = root.winfo_screenheight()
    root.geometry(f"{PET_SIZE}x{PET_SIZE}+{sw - PET_SIZE - 12}+{sh - PET_SIZE - 12}")

    canvas = tk.Canvas(root, width=PET_SIZE, height=PET_SIZE,
                       highlightthickness=0, cursor="hand2")
    canvas.pack()

    def _draw():
        canvas.delete("all")
        bg = PET_PAUSED_BG if paused_ref[0] else PET_BG
        r = PET_SIZE // 2
        canvas.create_oval(2, 2, PET_SIZE - 2, PET_SIZE - 2,
                            fill=bg, outline="#555555", width=1)
        canvas.create_text(r, r, text="⏸" if paused_ref[0] else "J",
                           fill=PET_FG, font=("SF Pro Display", 16, "bold"))

    _draw()

    # Drag
    _drag = {}

    def _drag_start(e):
        _drag["x"] = e.x_root
        _drag["y"] = e.y_root

    def _drag_move(e):
        dx = e.x_root - _drag["x"]
        dy = e.y_root - _drag["y"]
        root.geometry(f"+{root.winfo_x() + dx}+{root.winfo_y() + dy}")
        _drag["x"] = e.x_root
        _drag["y"] = e.y_root

    canvas.bind("<ButtonPress-1>", _drag_start)
    canvas.bind("<B1-Motion>", _drag_move)

    def _on_left_release(e):
        if abs(e.x_root - _drag.get("x", e.x_root)) < 5 and \
           abs(e.y_root - _drag.get("y", e.y_root)) < 5:
            root.after(1000, on_capture)

    canvas.bind("<ButtonRelease-1>", _on_left_release)

    # Right-click menu
    menu = tk.Menu(root, tearoff=0, bg=PET_BG, fg=PET_FG,
                   activebackground="#555555", activeforeground=PET_FG,
                   font=("SF Pro Display", 11))

    def _toggle_pause():
        paused_ref[0] = not paused_ref[0]
        menu.entryconfigure(0, label="Resume" if paused_ref[0] else "Pause")
        _draw()
        print(f"[pet] {'paused' if paused_ref[0] else 'resumed'}")

    menu.add_command(label="Pause", command=_toggle_pause)
    menu.add_separator()
    menu.add_command(label="Quit", command=lambda: __import__("os")._exit(0))

    def _on_right_click(e):
        menu.entryconfigure(0, label="Resume" if paused_ref[0] else "Pause")
        try:
            menu.tk_popup(e.x_root, e.y_root)
        finally:
            menu.grab_release()

    canvas.bind("<Button-2>", _on_right_click)
    canvas.bind("<Button-3>", _on_right_click)

    # Drain ui_queue: run callables posted from the JARVIS background thread
    def _drain():
        try:
            while True:
                fn = ui_queue.get_nowait()
                fn()
        except queue.Empty:
            pass
        _draw()
        root.after(200, _drain)

    root.after(200, _drain)
    root.mainloop()
