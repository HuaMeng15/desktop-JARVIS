import re
import threading
import tkinter as tk


# ── Design tokens ────────────────────────────────────────────────────────────
BG          = "#87837b"
BG_CARD     = "#7e7a73"
FG          = "#ffffff"
FG_DIM      = "#e0ddd8"
ACCENT      = "#ffffff"
BTN_BG      = "#7a7670"
BTN_FG      = "#ffffff"
BTN_GOOD_BG = "#1f530e"
BTN_GOOD_FG = "#ffffff"
RADIUS      = 20
ALPHA       = 0.93


def _rounded_rect(canvas, x1, y1, x2, y2, r, **kwargs):
    """Draw a rounded rectangle on a canvas."""
    canvas.create_arc(x1, y1, x1+2*r, y1+2*r, start=90,  extent=90,  style="pieslice", **kwargs)
    canvas.create_arc(x2-2*r, y1, x2, y1+2*r, start=0,   extent=90,  style="pieslice", **kwargs)
    canvas.create_arc(x1, y2-2*r, x1+2*r, y2, start=180, extent=90,  style="pieslice", **kwargs)
    canvas.create_arc(x2-2*r, y2-2*r, x2, y2, start=270, extent=90,  style="pieslice", **kwargs)
    canvas.create_rectangle(x1+r, y1, x2-r, y2, **kwargs)
    canvas.create_rectangle(x1, y1+r, x2, y2-r, **kwargs)


def _render_markdown(text_box: tk.Text, text: str):
    text_box.configure(state="normal")
    text_box.delete("1.0", tk.END)
    text_box.tag_configure("h1", font=("SF Pro Display", 14, "bold"), spacing3=4, foreground=FG)
    text_box.tag_configure("h2", font=("SF Pro Display", 12, "bold"), spacing3=2, foreground=FG)
    text_box.tag_configure("h3", font=("SF Pro Display", 11, "bold"), foreground=FG)
    text_box.tag_configure("bold", font=("SF Pro Display", 11, "bold"), foreground=FG)
    text_box.tag_configure("bullet", lmargin1=16, lmargin2=24, foreground=FG)
    text_box.tag_configure("italic", font=("SF Pro Display", 10, "italic"), foreground=FG_DIM)
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
    # Handle *italic* (single asterisk)
    parts = re.split(r"(\*\*[^*]+\*\*|\*[^*]+\*)", line)
    for part in parts:
        if part.startswith("**") and part.endswith("**"):
            tags = ("bold",) if not base_tag else (base_tag, "bold")
            text_box.insert(tk.END, part[2:-2], tags)
        elif part.startswith("*") and part.endswith("*"):
            tags = ("italic",) if not base_tag else (base_tag, "italic")
            text_box.insert(tk.END, part[1:-1], tags)
        else:
            text_box.insert(tk.END, part, (base_tag,) if base_tag else ())


def _pill_button(parent, text, command, bg, fg, bold=False):
    """Canvas-based pill button with true rounded corners."""
    font_spec = ("SF Pro Display", 10, "bold") if bold else ("SF Pro Display", 10)
    # measure text size
    tmp = tk.Label(parent, text=text, font=font_spec)
    tmp.update_idletasks()
    tw = tmp.winfo_reqwidth()
    th = tmp.winfo_reqheight()
    tmp.destroy()
    pw, ph = tw + 24, th + 8
    r = ph // 2  # fully pill-shaped

    c = tk.Canvas(parent, width=pw, height=ph, bg=parent["bg"],
                  highlightthickness=0, cursor="hand2")

    def _draw(color):
        c.delete("all")
        # pill shape via two arcs + rectangle
        c.create_arc(0, 0, 2*r, ph, start=90, extent=180, fill=color, outline=color)
        c.create_arc(pw-2*r, 0, pw, ph, start=270, extent=180, fill=color, outline=color)
        c.create_rectangle(r, 0, pw-r, ph, fill=color, outline=color)
        c.create_text(pw//2, ph//2, text=text, fill=fg, font=font_spec)

    _draw(bg)
    c.bind("<Enter>",           lambda e: _draw(_lighten(bg)))
    c.bind("<Leave>",           lambda e: _draw(bg))
    c.bind("<Button-1>",        lambda e: (_draw(_darken(bg)), command()))
    c.bind("<ButtonRelease-1>", lambda e: _draw(bg))
    return c


def _lighten(hex_color):
    r = min(255, int(hex_color[1:3], 16) + 20)
    g = min(255, int(hex_color[3:5], 16) + 20)
    b = min(255, int(hex_color[5:7], 16) + 20)
    return f"#{r:02x}{g:02x}{b:02x}"


def _darken(hex_color):
    r = max(0, int(hex_color[1:3], 16) - 20)
    g = max(0, int(hex_color[3:5], 16) - 20)
    b = max(0, int(hex_color[5:7], 16) - 20)
    return f"#{r:02x}{g:02x}{b:02x}"


def show_overlay(text_or_stream, on_more, on_chat, on_stream_done=None,
                 parent=None, pet_size: int = 0, pet_pos_ref: list | None = None) -> str:
    """Display overlay. Returns reaction string ('good'/'dismiss'/etc).

    If parent is given (a tk.Tk root), uses Toplevel + wait_window instead of
    a new Tk + mainloop, so it can be called from within an existing event loop.
    """

    reaction = ["dismiss"]
    if parent is not None:
        root = tk.Toplevel(parent)
    else:
        root = tk.Tk()
    root.withdraw()
    root.title("")
    root.attributes("-topmost", True)
    root.attributes("-alpha", ALPHA)
    root.configure(bg=BG)
    root.resizable(False, False)
    # Do NOT use overrideredirect — it breaks keyboard focus on macOS.
    # Title bar is hidden via AppKit in _apply_rounded_corners instead.

    # Set accessory policy
    try:
        from AppKit import NSApplication, NSApplicationActivationPolicyAccessory
        NSApplication.sharedApplication().setActivationPolicy_(NSApplicationActivationPolicyAccessory)
    except Exception:
        pass

    def _apply_rounded_corners():
        try:
            from AppKit import NSApp, NSColor, NSWindowButton
            root.update_idletasks()
            for w in NSApp.windows():
                w.setBackgroundColor_(NSColor.clearColor())
                w.setTitlebarAppearsTransparent_(True)
                w.setTitleVisibility_(1)  # NSWindowTitleHidden
                w.setStyleMask_(w.styleMask() | (1 << 15))  # NSWindowStyleMaskFullSizeContentView
                # Hide traffic light buttons
                for btn_type in (0, 1, 2):  # Close, Miniaturize, Zoom
                    btn = w.standardWindowButton_(btn_type)
                    if btn:
                        btn.setHidden_(True)
                cv = w.contentView()
                cv.setWantsLayer_(True)
                cv.layer().setCornerRadius_(RADIUS)
                cv.layer().setMasksToBounds_(True)
        except Exception:
            pass

    WIN_W = 420
    WIN_H = [200]   # mutable so _resize can update it
    MIN_H, MAX_H = 120, 400
    HEADER_H = 30
    BOTTOM_H = 46

    screen_w = root.winfo_screenwidth()
    screen_h = root.winfo_screenheight()

    def _resize_to_text():
        root.update_idletasks()
        text_box.configure(state="normal")
        try:
            # count display lines (accounts for word-wrap)
            dlines = text_box.count("1.0", tk.END, "displaylines")[0] or 1
            # measure one line height via first line bbox
            lb = text_box.bbox("1.0")
            line_h = lb[3] if lb else 18
            content_h = dlines * line_h + 24
        except Exception:
            content_h = 60
        text_box.configure(state="disabled")

        new_h = max(MIN_H, min(MAX_H, HEADER_H + content_h + BOTTOM_H))
        WIN_H[0] = new_h
        if pet_pos_ref and len(pet_pos_ref) == 4:
            px, py, pw, ph = pet_pos_ref
            x = px + pw // 2 - WIN_W // 2  # center over pet horizontally
            x = max(0, min(screen_w - WIN_W, x))
            y = py - new_h - 8  # 8px gap above pet
        else:
            margin = pet_size + 16 if pet_size else 24
            x = screen_w - WIN_W - 24
            y = screen_h - new_h - margin
        root.geometry(f"{WIN_W}x{new_h}+{x}+{y}")
        text_frame.place(x=0, y=HEADER_H, width=WIN_W, height=new_h - HEADER_H - BOTTOM_H)
        bottom.place(x=RADIUS, y=new_h - BOTTOM_H + 2, width=WIN_W - RADIUS*2)

    margin = pet_size + 16 if pet_size else 24
    root.geometry(f"{WIN_W}x{WIN_H[0]}+{screen_w - WIN_W - 24}+{screen_h - WIN_H[0] - margin}")

    # ── Drag support ──────────────────────────────────────────────────────────
    _drag = {"x": 0, "y": 0}
    def _drag_start(e): _drag["x"] = e.x_root; _drag["y"] = e.y_root
    def _drag_move(e):
        dx = e.x_root - _drag["x"]; dy = e.y_root - _drag["y"]
        nx = root.winfo_x() + dx;   ny = root.winfo_y() + dy
        root.geometry(f"+{nx}+{ny}")
        _drag["x"] = e.x_root;      _drag["y"] = e.y_root

    # ── Header (compact) ──────────────────────────────────────────────────────
    header = tk.Frame(root, bg=BG, pady=0)
    header.place(x=RADIUS, y=6, width=WIN_W - RADIUS*2)
    header.bind("<ButtonPress-1>",   _drag_start)
    header.bind("<B1-Motion>",       _drag_move)

    title_lbl = tk.Label(header, text="JARVIS", bg=BG, fg=ACCENT,
                         font=("SF Pro Display", 9, "bold"), cursor="fleur")
    title_lbl.pack(side=tk.LEFT)
    title_lbl.bind("<ButtonPress-1>", _drag_start)
    title_lbl.bind("<B1-Motion>",     _drag_move)

    def _close_x():
        _close("dismiss")
    close_btn = tk.Label(header, text="×", bg=BG, fg=FG_DIM,
                         font=("SF Pro Display", 13), cursor="hand2", padx=4)
    close_btn.pack(side=tk.RIGHT)
    close_btn.bind("<Button-1>", lambda e: _close_x())
    close_btn.bind("<Enter>",    lambda e: close_btn.configure(fg=FG))
    close_btn.bind("<Leave>",    lambda e: close_btn.configure(fg=FG_DIM))

    # Thin separator
    sep = tk.Frame(root, bg=BG_CARD, height=1)
    sep.place(x=RADIUS, y=28, width=WIN_W - RADIUS*2)

    # ── Text area ─────────────────────────────────────────────────────────────
    text_frame = tk.Frame(root, bg=BG)
    text_frame.place(x=0, y=HEADER_H, width=WIN_W, height=WIN_H[0] - HEADER_H - BOTTOM_H)

    # Canvas-based scrollbar — native tk.Scrollbar ignores color on macOS 14 / Tk 9
    sb_canvas = tk.Canvas(text_frame, width=8, bg=BG, highlightthickness=0)
    sb_canvas.pack(side=tk.RIGHT, fill=tk.Y)

    def _sb_set(lo, hi):
        lo, hi = float(lo), float(hi)
        sb_canvas.delete("all")
        h = sb_canvas.winfo_height()
        if h < 2:
            return
        y0 = int(lo * h) + 2
        y1 = max(y0 + 20, int(hi * h) - 2)
        r = 3
        sb_canvas.create_arc(1, y0, 1+2*r, y0+2*r, start=90, extent=180, fill=BG_CARD, outline=BG_CARD)
        sb_canvas.create_arc(7-2*r, y0, 7, y0+2*r, start=270, extent=180, fill=BG_CARD, outline=BG_CARD)
        sb_canvas.create_arc(1, y1-2*r, 1+2*r, y1, start=180, extent=180, fill=BG_CARD, outline=BG_CARD)
        sb_canvas.create_arc(7-2*r, y1-2*r, 7, y1, start=0, extent=180, fill=BG_CARD, outline=BG_CARD)
        sb_canvas.create_rectangle(1, y0+r, 7, y1-r, fill=BG_CARD, outline=BG_CARD)

    def _sb_click(e):
        h = sb_canvas.winfo_height()
        text_box.yview_moveto(e.y / h)
    sb_canvas.bind("<Button-1>", _sb_click)
    sb_canvas.bind("<B1-Motion>", _sb_click)

    text_box = tk.Text(
        text_frame, wrap=tk.WORD,
        bg=BG, fg=FG,
        font=("SF Pro Display", 11),
        relief="flat", borderwidth=0,
        highlightthickness=0,
        padx=16, pady=8,
        insertbackground=FG,
        selectbackground=BTN_BG,
        yscrollcommand=_sb_set,
    )
    text_box.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

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

    def _fade_in():
        step = ALPHA / 30
        def _tick(current):
            if closed[0]:
                return
            nxt = min(current + step, ALPHA)
            root.attributes("-alpha", nxt)
            if nxt < ALPHA:
                root.after(15, _tick, nxt)
        root.after(15, _tick, 0)

    def _show():
        _resize_to_text()
        root.update_idletasks()
        _apply_rounded_corners()
        root.attributes("-alpha", 0)
        root.attributes("-topmost", True)
        root.deiconify()
        root.update_idletasks()
        _fade_in()
        if pet_pos_ref is not None:
            _poll_pet_pos()

    def _poll_pet_pos():
        if closed[0]:
            return
        _resize_to_text()
        root.after(50, _poll_pet_pos)

    closed = [False]

    if isinstance(text_or_stream, str):
        _set_text(text_or_stream)
        root.after(0, _show)
    else:
        def _stream_worker():
            first = True
            for item in text_or_stream:
                if closed[0]:
                    break
                if isinstance(item, tuple):
                    if not closed[0]:
                        root.after(0, _render_markdown, text_box, accumulated[0])
                        root.after(10, _resize_to_text)
                    if on_stream_done:
                        on_stream_done(item, accumulated[0])
                else:
                    if first:
                        root.after(0, _show)
                        first = False
                    if not closed[0]:
                        root.after(0, _append_chunk, item)
        threading.Thread(target=_stream_worker, daemon=True).start()

    CHAT_H = 44

    # ── Chat input (hidden initially) ─────────────────────────────────────────
    chat_frame = tk.Frame(root, bg=BG)

    chat_entry = tk.Entry(chat_frame, font=("SF Pro Display", 10),
                          relief="flat", bg=BG_CARD, fg=FG,
                          insertbackground=FG, highlightthickness=0, bd=0)
    chat_entry.place(x=8, y=8, relwidth=1.0, width=-88, height=28)
    chat_entry.bind("<Return>", lambda e: on_send_chat())

    send_btn = _pill_button(chat_frame, "Send", lambda: on_send_chat(), BTN_BG, BTN_FG)
    send_btn.place(relx=1.0, x=-76, y=6, width=68, height=32)

    def _run_in_thread(fn, *args):
        def worker():
            result = fn(*args)
            if not closed[0]:
                root.after(0, _set_text_and_resize, result)
        threading.Thread(target=worker, daemon=True).start()

    def _set_text_and_resize(new_text: str):
        _set_text(new_text)
        _resize_to_text()
        if chat_visible[0]:
            _layout_with_chat()

    chat_visible = [False]

    def on_send_chat():
        msg = chat_entry.get().strip()
        if not msg:
            return
        chat_entry.delete(0, tk.END)
        chat_visible[0] = False
        chat_frame.place_forget()
        _set_text("Thinking…")
        _resize_to_text()
        _run_in_thread(on_chat, msg)

    # ── Bottom bar ────────────────────────────────────────────────────────────
    bottom = tk.Frame(root, bg=BG)
    bottom.place(x=RADIUS, y=WIN_H[0] - BOTTOM_H + 2, width=WIN_W - RADIUS*2)

    def _close(r):
        reaction[0] = r
        closed[0] = True
        try:
            root.destroy()
        except Exception:
            pass

    good_btn = _pill_button(bottom, "✓  Good", lambda: _close("good"),
                            BTN_GOOD_BG, BTN_GOOD_FG, bold=True)
    good_btn.pack(side=tk.LEFT)

    right = tk.Frame(bottom, bg=BG)
    right.pack(side=tk.RIGHT)

    def on_more_click():
        _set_text("Thinking…")
        _run_in_thread(on_more)

    def _layout_with_chat():
        _resize_to_text()
        new_h = min(MAX_H, WIN_H[0] + CHAT_H)
        WIN_H[0] = new_h
        x = screen_w - WIN_W - 24
        y = screen_h - new_h - 100
        root.geometry(f"{WIN_W}x{new_h}+{x}+{y}")
        text_frame.place(x=0, y=HEADER_H, width=WIN_W, height=new_h - HEADER_H - BOTTOM_H - CHAT_H)
        chat_frame.place(x=RADIUS, y=new_h - BOTTOM_H - CHAT_H + 4, width=WIN_W - RADIUS*2, height=CHAT_H)
        bottom.place(x=RADIUS, y=new_h - BOTTOM_H + 2, width=WIN_W - RADIUS*2)
        root.after(10, lambda: chat_entry.focus_set())

    def on_chat_click():
        chat_visible[0] = True
        _layout_with_chat()
        root.after(80, chat_entry.focus_set)

    for label, cmd in [("More", on_more_click), ("Chat", on_chat_click), ("Dismiss", lambda: _close("dismiss"))]:
        _pill_button(right, label, cmd, BTN_BG, BTN_FG).pack(side=tk.LEFT, padx=(0, 6))

    if parent is not None:
        root.wait_window()
    else:
        root.mainloop()
    return reaction[0]
