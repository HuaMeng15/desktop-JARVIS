"""Overlay window: pure AppKit, runs on the AppKit main thread."""

import re
import threading

# Design tokens
BG_R, BG_G, BG_B       = 0x87/255, 0x83/255, 0x7b/255
CARD_R, CARD_G, CARD_B  = 0x7e/255, 0x7a/255, 0x73/255
BTN_R, BTN_G, BTN_B     = 0x7a/255, 0x76/255, 0x70/255
GOOD_R, GOOD_G, GOOD_B  = 0x1f/255, 0x53/255, 0x0e/255
WIN_W    = 460
MIN_H    = 140
MAX_H    = 480
HEADER_H = 32
BOTTOM_H = 56
CHAT_ROW_H = 54   # extra height added when chat input is visible
CHAT_H   = 44
RADIUS   = 12.0
ALPHA    = 0.93
GAP      = 8    # gap above pet
MARGIN_R = 32   # margin from right screen edge


def _ns_color(r, g, b, a=1.0):
    from AppKit import NSColor
    return NSColor.colorWithSRGBRed_green_blue_alpha_(r, g, b, a)


_MainCallerCls = None

def _on_main(fn):
    from Foundation import NSThread
    if NSThread.isMainThread():
        fn()
    else:
        import objc as _objc
        global _MainCallerCls
        if _MainCallerCls is None:
            from Foundation import NSObject
            class _MainCallerCls(NSObject):
                @_objc.python_method
                def schedule(self, fn):
                    self._fn = fn
                    self.performSelectorOnMainThread_withObject_waitUntilDone_(
                        "run:", None, False)
                def run_(self, _):
                    self._fn()
        caller = _MainCallerCls.alloc().init()
        caller.schedule(fn)


def _cg_color(r, g, b, a=1.0):
    import objc
    from Quartz import CGColorCreateGenericRGB
    return CGColorCreateGenericRGB(r, g, b, a)


def _parse_markdown(text: str):
    """Return list of (string, attrs_dict) for NSAttributedString."""
    from AppKit import NSFont, NSForegroundColorAttributeName, NSFontAttributeName
    white = _ns_color(1, 1, 1)
    dim   = _ns_color(0.88, 0.87, 0.85)
    body_font  = NSFont.fontWithName_size_("SF Pro Display", 16) or NSFont.systemFontOfSize_(16)
    bold_font  = NSFont.fontWithName_size_("SF Pro Display Bold", 16) or NSFont.boldSystemFontOfSize_(16)
    h1_font    = NSFont.fontWithName_size_("SF Pro Display Bold", 20) or NSFont.boldSystemFontOfSize_(20)
    italic_font= NSFont.fontWithName_size_("SF Pro Display Italic", 15) or NSFont.systemFontOfSize_(15)

    runs = []
    for line in text.splitlines():
        if line.startswith("# "):
            runs += _inline(line[2:], h1_font, white)
        elif line.startswith("## "):
            runs += _inline(line[3:], bold_font, white)
        elif line.startswith("### "):
            runs += _inline(line[4:], bold_font, white)
        elif re.match(r"^[-*]\s", line):
            runs += _inline("• " + line[2:], body_font, white)
        elif re.match(r"^\d+\.\s", line):
            runs += _inline(line, body_font, white)
        else:
            runs += _inline(line, body_font, white)
        runs.append(("\n", {NSFontAttributeName: body_font, NSForegroundColorAttributeName: white}))
    return runs


def _inline(line, base_font, base_color):
    from AppKit import NSFont, NSForegroundColorAttributeName, NSFontAttributeName
    white = base_color
    dim   = _ns_color(0.88, 0.87, 0.85)
    bold_font   = NSFont.fontWithName_size_("SF Pro Display Bold", base_font.pointSize()) or NSFont.boldSystemFontOfSize_(base_font.pointSize())
    italic_font = NSFont.fontWithName_size_("SF Pro Display Italic", 14) or NSFont.systemFontOfSize_(14)

    parts = re.split(r"(\*\*[^*]+\*\*|\*[^*]+\*)", line)
    runs = []
    for p in parts:
        if p.startswith("**") and p.endswith("**"):
            runs.append((p[2:-2], {NSFontAttributeName: bold_font, NSForegroundColorAttributeName: white}))
        elif p.startswith("*") and p.endswith("*"):
            runs.append((p[1:-1], {NSFontAttributeName: italic_font, NSForegroundColorAttributeName: dim}))
        else:
            runs.append((p, {NSFontAttributeName: base_font, NSForegroundColorAttributeName: white}))
    return runs


def _make_attr_string(text: str):
    from Foundation import NSMutableAttributedString, NSAttributedString
    result = NSMutableAttributedString.alloc().init()
    for s, attrs in _parse_markdown(text):
        chunk = NSAttributedString.alloc().initWithString_attributes_(s, attrs)
        result.appendAttributedString_(chunk)
    return result


_BtnDelegate = None
_BtnViewCls  = None
_OvWindowCls = None
_OvDelegateCls = None
_FadeTargetCls = None
_FollowTargetCls = None
_ChatFieldDelegateCls = None

def _button(parent_view, title, rect, bg_r, bg_g, bg_b, action_fn, refs):
    global _BtnViewCls
    from AppKit import NSView, NSFont, NSColor, NSBezierPath, NSString
    from AppKit import NSForegroundColorAttributeName, NSFontAttributeName

    if _BtnViewCls is None:
        class _BtnView(NSView):
            def isOpaque(self): return False
            def acceptsFirstMouse_(self, event): return True
            def mouseDown_(self, event):
                self._down = True
                self.setNeedsDisplay_(True)
            def mouseUp_(self, event):
                was_down = getattr(self, '_down', False)
                self._down = False
                self.setNeedsDisplay_(True)
                if was_down:
                    print(f"[btn] clicked: {self._title}", flush=True)
                    self._fn()
            def drawRect_(self, rect):
                from AppKit import NSBezierPath, NSFont, NSColor, NSString
                from AppKit import NSForegroundColorAttributeName, NSFontAttributeName
                alpha = 0.7 if getattr(self, '_down', False) else 1.0
                _ns_color(self._r, self._g, self._b, alpha).set()
                NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
                    self.bounds(), 10, 10).fill()
                font = NSFont.fontWithName_size_("SF Pro Display", 12) or NSFont.systemFontOfSize_(12)
                attrs = {NSFontAttributeName: font,
                         NSForegroundColorAttributeName: NSColor.whiteColor()}
                s = NSString.stringWithString_(self._title)
                sz = s.sizeWithAttributes_(attrs)
                b = self.bounds()
                s.drawAtPoint_withAttributes_(
                    ((b.size.width - sz.width) / 2, (b.size.height - sz.height) / 2), attrs)
        _BtnViewCls = _BtnView

    v = _BtnViewCls.alloc().initWithFrame_(rect)
    v._title = title
    v._fn    = action_fn
    v._r, v._g, v._b = bg_r, bg_g, bg_b
    v._down  = False
    refs.append(v)
    parent_view.addSubview_(v)
    return v


def show_overlay(text_or_stream, on_more, on_chat, on_stream_done=None,
                 parent=None, pet_size: int = 0, pet_pos_ref: list | None = None,
                 _ui_queue=None, close_ref: list | None = None,
                 on_thinking=None) -> str:
    """Show overlay. Must be called from background thread with _ui_queue provided."""
    import queue as _queue
    reaction = ["dismiss"]
    closed   = [False]

    win_ref = [None]  # set by _show_overlay_impl after window creation

    if close_ref is not None:
        def _external_close():
            closed[0] = True
            if win_ref[0] is not None:
                if _ui_queue is not None:
                    _ui_queue.put(lambda: win_ref[0].close())
                else:
                    win_ref[0].close()
        close_ref.append(_external_close)

    def _build():
        print("[display] _build running on main thread", flush=True)
        try:
            _show_overlay_impl(text_or_stream, on_more, on_chat, on_stream_done,
                               pet_pos_ref, reaction, closed, close_ref, win_ref,
                               on_thinking)
        except Exception:
            import traceback; traceback.print_exc()
            closed[0] = True

    if _ui_queue is not None:
        print("[display] queuing _build", flush=True)
        _ui_queue.put(_build)
    else:
        _build()

    import time
    deadline = time.monotonic() + 300  # 5-minute safety timeout
    while not closed[0]:
        if time.monotonic() > deadline:
            print("[display] show_overlay timed out — forcing close", flush=True)
            closed[0] = True
            break
        time.sleep(0.05)
    return reaction[0]


def _show_overlay_impl(text_or_stream, on_more, on_chat, on_stream_done,
                       pet_pos_ref, reaction, closed, close_ref=None, win_ref=None,
                       on_thinking=None):
    global _OvWindowCls, _OvDelegateCls, _FadeTargetCls, _FollowTargetCls, _ChatFieldDelegateCls
    from AppKit import (NSWindow, NSBorderlessWindowMask,
                        NSBackingStoreBuffered, NSColor, NSView, NSTextView,
                        NSScrollView, NSTextField, NSMakeRect, NSFont,
                        NSScreen, NSMakeSize)
    from Foundation import NSObject, NSTimer, NSAttributedString

    if _OvWindowCls is None:
        class _OvWindowCls(NSWindow):
            def canBecomeKeyWindow(self): return True
            def sendEvent_(self, event):
                import objc as _objc
                from AppKit import NSKeyDown as _KD
                if (event.type() == _KD and event.keyCode() == 36
                        and hasattr(self, '_on_enter') and self._on_enter):
                    self._on_enter()
                    return
                _objc.super(_OvWindowCls, self).sendEvent_(event)

    if _OvDelegateCls is None:
        class _OvDelegateCls(NSObject):
            def windowWillClose_(self, notif):
                self._closed[0] = True

    if _FadeTargetCls is None:
        class _FadeTargetCls(NSObject):
            def tick_(self, timer):
                if self._closed[0]:
                    timer.invalidate(); return
                self._steps[0] = min(self._steps[0] + ALPHA / 20, ALPHA)
                self._win.setAlphaValue_(self._steps[0])
                if self._steps[0] >= ALPHA:
                    timer.invalidate()

    if _FollowTargetCls is None:
        class _FollowTargetCls(NSObject):
            def follow_(self, timer):
                if self._closed[0]:
                    timer.invalidate(); return
                self._resize()

    if _ChatFieldDelegateCls is None:
        import objc as _objc
        class _ChatFieldDelegateCls(NSObject):
            def control_textView_doCommandBySelector_(self, control, tv, sel):
                if sel == b"insertNewline:":
                    self._send()
                    return True
                return False
            @_objc.python_method
            def _setup_field(self, field):
                field.setTarget_(self)
                field.setAction_("fieldEnter:")
            def fieldEnter_(self, sender):
                self._send()

    _refs    = []

    screen_w = int(NSScreen.mainScreen().frame().size.width)
    screen_h = int(NSScreen.mainScreen().frame().size.height)

    def _pos(win_h):
        if pet_pos_ref and len(pet_pos_ref) == 4:
            px, py, pw, ph = pet_pos_ref
            # py is tkinter coord (Y=0 top); convert to AppKit (Y=0 bottom)
            appkit_pet_y = screen_h - py - ph
            ax = px + pw // 2 - WIN_W // 2
            ax = max(0, min(screen_w - WIN_W, ax))
            ay = appkit_pet_y + ph + GAP
        else:
            ax = screen_w - WIN_W - MARGIN_R
            ay = screen_h - win_h - 100
        return ax, ay

    WIN_H = [200]
    ax, ay = _pos(WIN_H[0])

    win = _OvWindowCls.alloc().initWithContentRect_styleMask_backing_defer_(
        NSMakeRect(ax, ay, WIN_W, WIN_H[0]),
        NSBorderlessWindowMask, NSBackingStoreBuffered, False)
    if win_ref is not None:
        win_ref[0] = win
    win._on_enter = None
    win.setOpaque_(False)
    win.setAlphaValue_(0.0)
    win.setLevel_(4)  # above floating

    cv = win.contentView()
    cv.setWantsLayer_(True)
    cv.layer().setCornerRadius_(RADIUS)
    cv.layer().setMasksToBounds_(True)
    cv.layer().setBackgroundColor_(_cg_color(BG_R, BG_G, BG_B, ALPHA))

    # ── Header ────────────────────────────────────────────────────────────────
    header = NSView.alloc().initWithFrame_(NSMakeRect(0, WIN_H[0] - HEADER_H, WIN_W, HEADER_H))
    header.setWantsLayer_(True)
    header.layer().setBackgroundColor_(_cg_color(BG_R, BG_G, BG_B))
    cv.addSubview_(header)

    title_field = NSTextField.alloc().initWithFrame_(NSMakeRect(12, 6, 200, 18))
    title_field.setStringValue_("JARVIS")
    title_field.setEditable_(False)
    title_field.setBordered_(False)
    title_field.setDrawsBackground_(False)
    title_field.setTextColor_(NSColor.whiteColor())
    title_field.setFont_(NSFont.fontWithName_size_("SF Pro Display Bold", 9) or NSFont.boldSystemFontOfSize_(9))
    header.addSubview_(title_field)

    # ── Scroll + text ─────────────────────────────────────────────────────────
    scroll = NSScrollView.alloc().initWithFrame_(
        NSMakeRect(0, BOTTOM_H, WIN_W, WIN_H[0] - HEADER_H - BOTTOM_H))
    scroll.setHasVerticalScroller_(True)
    scroll.setAutohidesScrollers_(True)
    scroll.setDrawsBackground_(False)
    cv.addSubview_(scroll)

    text_view = NSTextView.alloc().initWithFrame_(
        NSMakeRect(0, 0, WIN_W - 16, WIN_H[0] - HEADER_H - BOTTOM_H))
    text_view.setEditable_(False)
    text_view.setSelectable_(True)
    text_view.setDrawsBackground_(False)
    text_view.setTextContainerInset_(NSMakeSize(8, 8))
    text_view.textContainer().setWidthTracksTextView_(True)
    scroll.setDocumentView_(text_view)

    accumulated = [""]

    def _set_text(t):
        accumulated[0] = t
        astr = _make_attr_string(t)
        text_view.textStorage().setAttributedString_(astr)
        _resize()

    def _append_text(chunk):
        accumulated[0] += chunk
        from Foundation import NSAttributedString
        from AppKit import NSFont, NSForegroundColorAttributeName, NSFontAttributeName
        font  = NSFont.fontWithName_size_("SF Pro Display", 13) or NSFont.systemFontOfSize_(13)
        attrs = {NSFontAttributeName: font, NSForegroundColorAttributeName: NSColor.whiteColor()}
        astr  = NSAttributedString.alloc().initWithString_attributes_(chunk, attrs)
        text_view.textStorage().appendAttributedString_(astr)
        text_view.scrollToEndOfDocument_(None)
        _resize()

    def _resize():
        if closed[0]:
            return
        text_view.layoutManager().ensureLayoutForTextContainer_(text_view.textContainer())
        used_h = text_view.layoutManager().usedRectForTextContainer_(text_view.textContainer()).size.height
        content_h = int(used_h) + 24
        chat_extra = CHAT_ROW_H if not chat_field.isHidden() else 0
        bottom = BOTTOM_H + chat_extra
        new_h = max(MIN_H, min(MAX_H, HEADER_H + content_h + bottom))
        WIN_H[0] = new_h
        ax2, ay2 = _pos(new_h)
        win.setFrame_display_(NSMakeRect(ax2, ay2, WIN_W, new_h), True)
        header.setFrame_(NSMakeRect(0, new_h - HEADER_H, WIN_W, HEADER_H))
        scroll.setFrame_(NSMakeRect(0, bottom, WIN_W, new_h - HEADER_H - bottom))
        _layout_buttons(new_h)

    # ── Bottom buttons ─────────────────────────────────────────────────────────
    BTN_H = 30
    _btns = {}

    def _layout_buttons(win_h):
        y = 14
        BTN_W = 70
        # buttons row always visible
        _btns['good'].setFrame_(NSMakeRect(12, y, BTN_W, BTN_H))
        _btns['more'].setFrame_(NSMakeRect(WIN_W - 12 - BTN_W*3 - 8*2, y, BTN_W, BTN_H))
        _btns['chat'].setFrame_(NSMakeRect(WIN_W - 12 - BTN_W*2 - 8,   y, BTN_W, BTN_H))
        _btns['dismiss'].setFrame_(NSMakeRect(WIN_W - 12 - BTN_W,       y, BTN_W, BTN_H))
        # chat input row above buttons
        if not chat_field.isHidden():
            chat_y = y + BTN_H + 12
            send_w = 60
            chat_field.setFrame_(NSMakeRect(12, chat_y, WIN_W - 12 - send_w - 8 - 12, BTN_H))
            _btns['send'].setFrame_(NSMakeRect(WIN_W - 12 - send_w, chat_y, send_w, BTN_H))
            _btns['send'].setHidden_(False)
        else:
            _btns['send'].setHidden_(True)

    def _close(r):
        reaction[0] = r
        closed[0] = True
        win.close()

    def _on_more():
        _set_text("Thinking…")
        if on_thinking:
            on_thinking(True)
        def _worker():
            result = on_more()
            if on_thinking:
                on_thinking(False)
            if not closed[0]:
                _on_main(lambda: _set_text(result))
        threading.Thread(target=_worker, daemon=True).start()

    # Chat input (hidden until Chat button clicked)
    CHAT_INPUT_H = 30
    chat_field = NSTextField.alloc().initWithFrame_(
        NSMakeRect(12, 10, WIN_W - 12 - 60 - 8 - 12, CHAT_INPUT_H))
    chat_field.setPlaceholderString_("Ask a question… (Enter to send)")
    chat_field.setHidden_(True)
    chat_field.setWantsLayer_(True)
    chat_field.layer().setCornerRadius_(6.0)
    chat_field.layer().setBackgroundColor_(_cg_color(1, 1, 1, 0.12))
    chat_field.setTextColor_(NSColor.whiteColor())
    chat_field.setFont_(NSFont.fontWithName_size_("SF Pro Display", 16) or NSFont.systemFontOfSize_(16))
    chat_field.setBordered_(True)
    chat_field.setBezelStyle_(0)  # NSTextFieldSquareBezel
    chat_field.setFocusRingType_(1)  # NSFocusRingTypeNone
    chat_field.setDrawsBackground_(False)
    cv.addSubview_(chat_field)

    _ChatDelegate = None

    def _on_chat_send():
        msg = chat_field.stringValue().strip()
        if not msg:
            return
        chat_field.setStringValue_("")
        chat_field.setHidden_(True)
        win._on_enter = None
        _resize()
        _set_text("Thinking…")
        if on_thinking:
            on_thinking(True)
        def _worker():
            result = on_chat(msg)
            if on_thinking:
                on_thinking(False)
            if not closed[0]:
                _on_main(lambda: _set_text(result))
        threading.Thread(target=_worker, daemon=True).start()

    chat_delegate = _ChatFieldDelegateCls.alloc().init()
    chat_delegate._send = _on_chat_send
    _refs.append(chat_delegate)
    chat_field.setDelegate_(chat_delegate)
    chat_delegate._setup_field(chat_field)

    def _on_chat_click():
        chat_field.setHidden_(False)
        win._on_enter = _on_chat_send
        win.makeKeyWindow()
        _resize()
        win.makeFirstResponder_(chat_field)

    _btns['good']    = _button(cv, "✓ Good",   NSMakeRect(12, 10, 80, BTN_H), GOOD_R, GOOD_G, GOOD_B, lambda: _close("good"), _refs)
    _btns['more']    = _button(cv, "More",      NSMakeRect(0, 10, 60, BTN_H),  BTN_R, BTN_G, BTN_B, _on_more, _refs)
    _btns['chat']    = _button(cv, "Chat",      NSMakeRect(0, 10, 60, BTN_H),  BTN_R, BTN_G, BTN_B, _on_chat_click, _refs)
    _btns['dismiss'] = _button(cv, "Dismiss",   NSMakeRect(0, 10, 60, BTN_H),  BTN_R, BTN_G, BTN_B, lambda: _close("dismiss"), _refs)
    _btns['send']    = _button(cv, "Send",      NSMakeRect(0, 10, 60, BTN_H),  BTN_R, BTN_G, BTN_B, _on_chat_send, _refs)
    _btns['send'].setHidden_(True)
    _layout_buttons(WIN_H[0])

    ov_delegate = _OvDelegateCls.alloc().init()
    ov_delegate._closed = closed
    _refs.append(ov_delegate)
    win.setDelegate_(ov_delegate)

    # ── Show & fade in ────────────────────────────────────────────────────────
    def _show_win():
        win.orderFrontRegardless()
        # Animate alpha via NSTimer steps
        _alpha_steps = [0.0]
        ft = _FadeTargetCls.alloc().init()
        ft._closed = closed
        ft._steps  = _alpha_steps
        ft._win    = win
        _refs.append(ft)
        NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            0.015, ft, "tick:", None, True)

    # ── Pet follow ────────────────────────────────────────────────────────────
    if pet_pos_ref is not None:
        follow_target = _FollowTargetCls.alloc().init()
        follow_target._closed  = closed
        follow_target._resize  = _resize
        _refs.append(follow_target)
        from Foundation import NSTimer
        NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            0.05, follow_target, "follow:", None, True)

    # ── Stream or static ──────────────────────────────────────────────────────
    if isinstance(text_or_stream, str):
        _set_text(text_or_stream)
        _show_win()
    else:
        def _stream_worker():
            first = True
            for item in text_or_stream:
                if closed[0]:
                    break
                if isinstance(item, tuple):
                    if not closed[0]:
                        _make_attr_string(accumulated[0])
                    if on_stream_done:
                        on_stream_done(item, accumulated[0])
                else:
                    if first:
                        _on_main(_show_win)
                        first = False
                    if not closed[0]:
                        _on_main(lambda chunk=item: _append_text(chunk))
        threading.Thread(target=_stream_worker, daemon=True).start()
