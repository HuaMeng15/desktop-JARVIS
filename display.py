import re
import threading
import tkinter as tk
from tkinter import scrolledtext


def _render_markdown(text_box: scrolledtext.ScrolledText, text: str):
    text_box.configure(state="normal")
    text_box.delete("1.0", tk.END)
    text_box.tag_configure("h1", font=("Helvetica", 14, "bold"), spacing3=4)
    text_box.tag_configure("h2", font=("Helvetica", 12, "bold"), spacing3=2)
    text_box.tag_configure("h3", font=("Helvetica", 11, "bold"))
    text_box.tag_configure("bold", font=("Helvetica", 11, "bold"))
    text_box.tag_configure("bullet", lmargin1=16, lmargin2=24)
    for line in text.splitlines():
        if line.startswith("### "):
            _insert_inline(text_box, line[4:], "h3")
        elif line.startswith("## "):
            _insert_inline(text_box, line[3:], "h2")
        elif line.startswith("# "):
            _insert_inline(text_box, line[2:], "h1")
        elif re.match(r"^[-*]\s", line):
            _insert_inline(text_box, "• " + line[2:], "bullet")
        elif re.match(r"^\d+\.\s", line):
            _insert_inline(text_box, line, "bullet")
        else:
            _insert_inline(text_box, line, None)
        text_box.insert(tk.END, "\n")
    text_box.configure(state="disabled")


def _insert_inline(text_box, line: str, base_tag):
    parts = re.split(r"(\*\*[^*]+\*\*)", line)
    for part in parts:
        if part.startswith("**") and part.endswith("**"):
            tags = ("bold",) if not base_tag else (base_tag, "bold")
            text_box.insert(tk.END, part[2:-2], tags)
        else:
            text_box.insert(tk.END, part, (base_tag,) if base_tag else ())


def show_overlay(text_or_stream, on_more, on_chat, on_stream_done=None) -> str:
    """Display overlay. text_or_stream: str or generator from stream_response().
    on_stream_done(stats_tuple) called when initial stream finishes.
    Returns 'dismiss' or 'good'."""
    BG = "#f5f5f5"
    FG = "#2c2c2c"
    ACCENT = "#5b5ea6"
    BTN_BG = "#e0e0e0"

    reaction = ["dismiss"]
    root = tk.Tk()
    root.title("JARVIS")
    root.attributes("-topmost", True)
    root.attributes("-alpha", 0.95)
    root.configure(bg=BG)
    root.resizable(True, True)

    screen_w = root.winfo_screenwidth()
    screen_h = root.winfo_screenheight()
    win_w, win_h = 480, 360
    root.geometry(f"{win_w}x{win_h}+{screen_w - win_w - 20}+{screen_h - win_h - 120}")

    tk.Label(root, text="JARVIS", bg=BG, fg=ACCENT,
             font=("Helvetica", 11, "bold")).pack(anchor="w", padx=12, pady=(10, 0))

    text_box = scrolledtext.ScrolledText(
        root, wrap=tk.WORD, bg="#ffffff", fg=FG,
        font=("Helvetica", 11), relief="flat", borderwidth=1,
        padx=10, pady=6, height=12,
    )
    text_box.pack(fill=tk.BOTH, expand=True, padx=8, pady=(4, 4))

    accumulated = [""]

    def _append_chunk(chunk: str):
        accumulated[0] += chunk
        text_box.configure(state="normal")
        text_box.insert(tk.END, chunk)
        text_box.see(tk.END)
        text_box.configure(state="disabled")

    def _set_text(new_text: str):
        accumulated[0] = new_text
        _render_markdown(text_box, new_text)

    closed = [False]

    if isinstance(text_or_stream, str):
        _set_text(text_or_stream)
    else:
        root.withdraw()  # hide until first token

        def _stream_worker():
            first = True
            for item in text_or_stream:
                if closed[0]:
                    break
                if isinstance(item, tuple):
                    if not closed[0]:
                        root.after(0, _render_markdown, text_box, accumulated[0])
                    if on_stream_done:
                        on_stream_done(item, accumulated[0])
                else:
                    if first:
                        root.after(0, root.deiconify)
                        first = False
                    if not closed[0]:
                        root.after(0, _append_chunk, item)
        threading.Thread(target=_stream_worker, daemon=True).start()

    # Chat input row (hidden initially)
    chat_frame = tk.Frame(root, bg=BG)
    chat_entry = tk.Entry(chat_frame, font=("Helvetica", 10), relief="flat", bg="#ffffff")
    chat_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4))
    chat_entry.bind("<Return>", lambda e: on_send_chat())

    def _run_in_thread(fn, *args):
        def worker():
            result = fn(*args)
            if not closed[0]:
                root.after(0, _set_text, result)
        threading.Thread(target=worker, daemon=True).start()

    def on_send_chat():
        msg = chat_entry.get().strip()
        if not msg:
            return
        chat_entry.delete(0, tk.END)
        chat_frame.pack_forget()
        _set_text("Thinking...")
        _run_in_thread(on_chat, msg)

    tk.Button(chat_frame, text="Send", command=on_send_chat,
              bg=BTN_BG, fg=FG, relief="flat",
              font=("Helvetica", 10), padx=6, pady=2).pack(side=tk.LEFT)

    # Bottom bar
    bottom_frame = tk.Frame(root, bg=BG)
    bottom_frame.pack(fill=tk.X, padx=12, pady=(0, 10))

    def _close(r):
        reaction[0] = r
        closed[0] = True
        try:
            root.withdraw()
            root.after(100, root.destroy)
        except Exception:
            pass

    root.protocol("WM_DELETE_WINDOW", lambda: _close("dismiss"))

    def _make_button(parent, text, command, bg, fg, bold=False):
        """Label-based button with true background color (macOS compatible)."""
        font = ("Helvetica", 10, "bold") if bold else ("Helvetica", 10)
        lbl = tk.Label(parent, text=text, bg=bg, fg=fg, font=font,
                       padx=10, pady=5, cursor="hand2")
        lbl.bind("<Button-1>", lambda e: command())
        lbl.bind("<Enter>", lambda e: lbl.configure(bg=_darken(bg)))
        lbl.bind("<Leave>", lambda e: lbl.configure(bg=bg))
        return lbl

    def _darken(hex_color):
        r, g, b = int(hex_color[1:3], 16), int(hex_color[3:5], 16), int(hex_color[5:7], 16)
        return f"#{max(0,r-30):02x}{max(0,g-30):02x}{max(0,b-30):02x}"

    _make_button(bottom_frame, "Good", lambda: _close("good"),
                 bg="#4caf50", fg="#ffffff", bold=True).pack(side=tk.LEFT)

    right_frame = tk.Frame(bottom_frame, bg=BG)
    right_frame.pack(side=tk.RIGHT)

    def on_more_click():
        _set_text("Thinking...")
        _run_in_thread(on_more)

    def on_chat_click():
        chat_frame.pack(fill=tk.X, padx=8, pady=(0, 4), before=bottom_frame)
        chat_entry.focus_set()

    for label, cmd in [("More", on_more_click), ("Chat", on_chat_click), ("Dismiss", lambda: _close("dismiss"))]:
        tk.Button(right_frame, text=label, command=cmd,
                  bg=BTN_BG, fg=FG, relief="flat",
                  font=("Helvetica", 10), padx=8, pady=4).pack(side=tk.LEFT, padx=(0, 6))

    root.mainloop()
    return reaction[0]
