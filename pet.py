"""Desktop pet: pure AppKit NSWindow with transparent background."""

import queue
import threading
from pathlib import Path

PET_SIZE = 100
_ICON_DIR = Path(__file__).parent / "src" / "icons"


def run_pet_loop(on_capture, paused_ref: list, ui_queue: queue.Queue,
                 root_ref: list | None = None, on_pause=None) -> None:
    from AppKit import (NSApplication, NSApplicationActivationPolicyAccessory,
                        NSBorderlessWindowMask, NSColor, NSImage, NSImageView,
                        NSMakeRect, NSWindow, NSBackingStoreBuffered, NSScreen,
                        NSView, NSMenu, NSMenuItem)
    from Foundation import NSTimer, NSObject
    import objc

    NSApplication.sharedApplication()
    NSApplication.sharedApplication().setActivationPolicy_(
        NSApplicationActivationPolicyAccessory)

    sw = int(NSScreen.mainScreen().frame().size.width)
    dock_h = int(NSScreen.mainScreen().visibleFrame().origin.y)
    ax = sw - PET_SIZE - 30
    ay = dock_h + 30

    win = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
        NSMakeRect(ax, ay, PET_SIZE, PET_SIZE),
        NSBorderlessWindowMask, NSBackingStoreBuffered, False)
    win.setBackgroundColor_(NSColor.clearColor())
    win.setOpaque_(False)
    win.setLevel_(3)  # NSFloatingWindowLevel

    if root_ref is not None:
        root_ref[0] = win

    _drag = {}
    _delegate_ref = []

    class _MenuDelegate(NSObject):
        def togglePause_(self, s):
            paused_ref[0] = not paused_ref[0]
            if on_pause:
                on_pause(paused_ref[0])
        def quit_(self, s):
            import os; os._exit(0)

    _menu_delegate = _MenuDelegate.alloc().init()
    _delegate_ref.append(_menu_delegate)

    class _PetView(NSView):
        def acceptsFirstMouse_(self, event): return True
        def mouseDownCanMoveWindow(self): return True

        def mouseDown_(self, event):
            _drag['wx'] = win.frame().origin.x
            _drag['wy'] = win.frame().origin.y

        def mouseUp_(self, event):
            dwx = win.frame().origin.x - _drag.get('wx', win.frame().origin.x)
            dwy = win.frame().origin.y - _drag.get('wy', win.frame().origin.y)
            if abs(dwx) < 5 and abs(dwy) < 5:
                threading.Timer(1.0, on_capture).start()

        def rightMouseDown_(self, event):
            menu = NSMenu.alloc().init()
            lbl = "Resume" if paused_ref[0] else "Pause"
            i1 = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(lbl, "togglePause:", "")
            i1.setTarget_(_menu_delegate)
            i2 = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Quit", "quit:", "")
            i2.setTarget_(_menu_delegate)
            menu.addItem_(i1)
            menu.addItem_(NSMenuItem.separatorItem())
            menu.addItem_(i2)
            NSMenu.popUpContextMenu_withEvent_forView_(menu, event, self)

    view = _PetView.alloc().initWithFrame_(NSMakeRect(0, 0, PET_SIZE, PET_SIZE))
    view.setWantsLayer_(True)
    view.layer().setBackgroundColor_(None)

    ns_img = NSImage.alloc().initWithContentsOfFile_(str(_ICON_DIR / "jarvis.heic"))
    img_view = NSImageView.alloc().initWithFrame_(NSMakeRect(0, 0, PET_SIZE, PET_SIZE))
    img_view.setImage_(ns_img)
    img_view.setImageScaling_(3)
    img_view.setIgnoreHitTest_(True)  # pass mouse events through to _PetView
    view.addSubview_(img_view)

    win.setContentView_(view)

    # --- UI queue drain via NSTimer ---
    class _DrainTarget(NSObject):
        def drain_(self, _timer):
            try:
                while True:
                    ui_queue.get_nowait()()
            except queue.Empty:
                pass

    drain_target = _DrainTarget.alloc().init()
    NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
        0.2, drain_target, "drain:", None, True)

    win.orderFrontRegardless()

    import signal
    signal.signal(signal.SIGINT, lambda *_: NSApplication.sharedApplication().terminate_(None))

    NSApplication.sharedApplication().run()
