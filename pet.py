"""Desktop pet: pure AppKit NSWindow with transparent background."""

import queue
import threading
from pathlib import Path

PET_SIZE = 50
_ICON_DIR = Path(__file__).parent / "src" / "icons"


def run_pet_loop(on_capture, paused_ref: list, ui_queue: queue.Queue,
                root_ref: list | None = None, on_pause=None,
                pet_pos_ref: list | None = None,
                thinking_ref: list | None = None) -> None:
    from AppKit import (NSApplication, NSApplicationActivationPolicyAccessory,
                        NSBorderlessWindowMask, NSColor, NSImage,
                        NSMakeRect, NSWindow, NSBackingStoreBuffered, NSScreen,
                        NSView, NSMenu, NSMenuItem,
                        NSEventTypeLeftMouseDown, NSEventTypeLeftMouseUp,
                        NSEventTypeLeftMouseDragged, NSEventTypeRightMouseDown)
    from Foundation import NSTimer, NSObject

    NSApplication.sharedApplication()
    NSApplication.sharedApplication().setActivationPolicy_(
        NSApplicationActivationPolicyAccessory)

    sw = int(NSScreen.mainScreen().frame().size.width)
    sh = int(NSScreen.mainScreen().frame().size.height)
    dock_h = int(NSScreen.mainScreen().visibleFrame().origin.y)
    ax = sw - PET_SIZE - 30
    ay = dock_h + 30

    _drag = {}
    _refs = []  # keep objects alive

    class _MenuDelegate(NSObject):
        def togglePause_(self, s):
            paused_ref[0] = not paused_ref[0]
            win.contentView().setNeedsDisplay_(True)
            if on_pause:
                on_pause(paused_ref[0])
        def quit_(self, s):
            NSApplication.sharedApplication().terminate_(None)

    _menu_delegate = _MenuDelegate.alloc().init()
    _refs.append(_menu_delegate)

    import objc as _objc

    class _PetWindow(NSWindow):
        def canBecomeKeyWindow(self): return True

        def sendEvent_(self, event):
            try:
                t = event.type()
                if t == NSEventTypeLeftMouseDown:
                    loc = self.convertPointToScreen_(event.locationInWindow())
                    _drag['sx'] = loc.x
                    _drag['sy'] = loc.y
                    _drag['ox'] = self.frame().origin.x
                    _drag['oy'] = self.frame().origin.y
                    _drag['moved'] = False
                elif t == NSEventTypeLeftMouseDragged:
                    loc = self.convertPointToScreen_(event.locationInWindow())
                    dx = loc.x - _drag.get('sx', loc.x)
                    dy = loc.y - _drag.get('sy', loc.y)
                    nx, ny = _drag['ox'] + dx, _drag['oy'] + dy
                    self.setFrameOrigin_((nx, ny))
                    _update_pos_ref(nx, ny)
                    _drag['moved'] = True
                elif t == NSEventTypeLeftMouseUp:
                    if not _drag.get('moved') and not paused_ref[0]:
                        threading.Timer(1.0, on_capture).start()
                elif t == NSEventTypeRightMouseDown:
                    menu = NSMenu.alloc().init()
                    lbl = "Resume" if paused_ref[0] else "Pause"
                    i1 = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(lbl, "togglePause:", "")
                    i1.setTarget_(_menu_delegate)
                    i2 = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Quit", "quit:", "")
                    i2.setTarget_(_menu_delegate)
                    menu.addItem_(i1)
                    menu.addItem_(NSMenuItem.separatorItem())
                    menu.addItem_(i2)
                    NSMenu.popUpContextMenu_withEvent_forView_(menu, event, self.contentView())
                    return
            except Exception as e:
                print(f'sendEvent_ error: {e}', flush=True)
            _objc.super(_PetWindow, self).sendEvent_(event)

    ns_img = NSImage.alloc().initWithContentsOfFile_(str(_ICON_DIR / "jarvis.heic"))
    ns_img_pause = NSImage.alloc().initWithContentsOfFile_(str(_ICON_DIR / "pause.heic"))
    ns_img_think = NSImage.alloc().initWithContentsOfFile_(str(_ICON_DIR / "thinking.heic"))
    _iw = ns_img.size().width
    _ih = ns_img.size().height
    PET_W = PET_SIZE
    PET_H = int(PET_SIZE * _ih / _iw) if _iw else PET_SIZE

    def _update_pos_ref(appkit_x, appkit_y):
        if pet_pos_ref is not None:
            pet_pos_ref[:] = [int(appkit_x), int(sh - appkit_y - PET_H), PET_W, PET_H]

    _update_pos_ref(ax, ay)  # set initial position

    win = _PetWindow.alloc().initWithContentRect_styleMask_backing_defer_(
        NSMakeRect(ax, ay, PET_W, PET_H),
        NSBorderlessWindowMask, NSBackingStoreBuffered, False)
    win.setBackgroundColor_(NSColor.clearColor())
    win.setOpaque_(False)
    win.setLevel_(3)

    if root_ref is not None:
        root_ref[0] = win

    class _PetView(NSView):
        def isOpaque(self): return False
        def drawRect_(self, rect):
            if paused_ref[0]:
                img = ns_img_pause
            elif thinking_ref and thinking_ref[0]:
                img = ns_img_think
            else:
                img = ns_img
            img.drawInRect_fromRect_operation_fraction_(
                NSMakeRect(0, 0, PET_W, PET_H),
                NSMakeRect(0, 0, 0, 0), 18, 1.0)

    view = _PetView.alloc().initWithFrame_(NSMakeRect(0, 0, PET_W, PET_H))
    win.setContentView_(view)

    class _DrainTarget(NSObject):
        def drain_(self, _timer):
            try:
                while True:
                    ui_queue.get_nowait()()
            except queue.Empty:
                pass

    drain_target = _DrainTarget.alloc().init()
    _refs.append(drain_target)
    NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
        0.2, drain_target, "drain:", None, True)

    win.orderFrontRegardless()

    from AppKit import NSEvent, NSEventMaskKeyDown, NSEventModifierFlagControl
    def _on_global_key(event):
        try:
            if not (event.modifierFlags() & NSEventModifierFlagControl):
                return
            kc = event.keyCode()
            ctrl = bool(event.modifierFlags() & NSEventModifierFlagControl)
            if kc == 111 and ctrl:  # Ctrl+F12 — toggle pause
                _menu_delegate.togglePause_(None)
            elif kc == 103 and ctrl and not paused_ref[0]:  # Ctrl+F11 — capture
                threading.Timer(1.0, on_capture).start()
        except Exception as e:
            print(f'hotkey error: {e}', flush=True)
    _monitor = NSEvent.addGlobalMonitorForEventsMatchingMask_handler_(NSEventMaskKeyDown, _on_global_key)
    _local_monitor = NSEvent.addLocalMonitorForEventsMatchingMask_handler_(NSEventMaskKeyDown, lambda e: (_on_global_key(e), e)[1])
    _refs.append(_monitor)
    _refs.append(_local_monitor)

    import signal
    signal.signal(signal.SIGINT, lambda *_: NSApplication.sharedApplication().terminate_(None))

    NSApplication.sharedApplication().run()
