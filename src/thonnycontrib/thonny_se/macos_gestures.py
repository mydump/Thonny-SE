# SPDX-FileCopyrightText: 2026 Sebastian Ladhoff
# SPDX-License-Identifier: GPL-3.0-only
# See LICENSE in the project root for the full license text.

"""App-local macOS magnification events for registered diagram scroll areas."""
import ctypes
import logging
import math
import tkinter as tk
import weakref
from collections import deque


class _Descriptor(ctypes.Structure):
    _fields_ = [('reserved', ctypes.c_ulong), ('size', ctypes.c_ulong)]


class _Block(ctypes.Structure):
    _fields_ = [('isa', ctypes.c_void_p), ('flags', ctypes.c_int),
                ('reserved', ctypes.c_int), ('invoke', ctypes.c_void_p),
                ('descriptor', ctypes.POINTER(_Descriptor))]


class MagnifyMonitor:
    """One local AppKit monitor per Tk application, removed with its last area."""
    def __init__(self, root):
        from .display_context import _objc_api
        self.root = root
        self.areas = weakref.WeakSet()
        self.pending = weakref.WeakKeyDictionary()
        self.job = None
        self.events = deque(maxlen=2048)
        self.active = False
        self.objc, self.ptr, _, _, self.number, _ = _objc_api()
        self.sel = lambda name: self.objc.sel_registerName(name.encode())
        address = ctypes.cast(self.objc.objc_msgSend, ctypes.c_void_p).value
        self.add_monitor = ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p,
            ctypes.c_void_p, ctypes.c_ulong, ctypes.c_void_p)(address)
        self.remove_monitor = ctypes.CFUNCTYPE(None, ctypes.c_void_p,
            ctypes.c_void_p, ctypes.c_void_p)(address)
        self.release = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_void_p)(address)
        self.event_class = self.objc.objc_getClass(b'NSEvent')
        self.system = ctypes.CDLL('/usr/lib/libSystem.B.dylib')
        # Global block storage and the Python callback live until removeMonitor.
        isa = ctypes.addressof(ctypes.c_byte.in_dll(self.system, '_NSConcreteGlobalBlock'))
        self.callback = ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)(self._receive)
        self.descriptor = _Descriptor(0, ctypes.sizeof(_Block))
        self.block = _Block(isa, 1 << 28, 0, ctypes.cast(self.callback, ctypes.c_void_p),
                            ctypes.pointer(self.descriptor))
        token = self.add_monitor(self.event_class,
            self.sel('addLocalMonitorForEventsMatchingMask:handler:'), 1 << 30,
            ctypes.byref(self.block))
        if not token:
            raise RuntimeError('AppKit did not register the magnification monitor')
        self.token = self.ptr(token, self.sel('retain'))
        self.job = self.root.after(16, self.poll)

    def _receive(self, block, event):
        # Never propagate a Python exception through an Objective-C callback.
        try:
            delta = self.number(event, self.sel('magnification'))
            if self.active and math.isfinite(delta) and abs(delta) <= 10:
                self.events.append(delta)
                return None
            # NO Tk calls here, including hit-testing or after registration.
            # `active` is a conservative hit snapshot maintained by Tk's timer.
            return event
        except Exception:
            logging.getLogger(__name__).exception('Could not process macOS magnification')
            return event

    def poll(self):
        """Enter Tk only through its normal timer callback on the main thread."""
        self.job = None
        values = list(self.events)
        self.events.clear()
        try:
            self.active = self._target() is not None
            if values:
                self.route(sum(values))
            self.flush()
        finally:
            if self.token is not None and self.areas:
                self.job = self.root.after(16, self.poll)

    def _target(self):
        if self.root.tk.call('grab', 'current'):
            return None
        x, y = self.root.winfo_pointerxy()
        widget = self.root.winfo_containing(x, y)
        if widget is None:
            return None
        # Native editor controls may be created after the diagram's scroll
        # bindings. Pinch targets the enclosing diagram, independent of the
        # editor's own wheel/scroll handling.
        tags = set()
        current = widget
        while current is not None:
            tags.update(current.bindtags())
            current = current.master
        for area in list(self.areas):
            canvas = area.canvas
            if area.tag not in tags or not canvas.winfo_ismapped():
                continue
            position = x-canvas.winfo_rootx(), y-canvas.winfo_rooty()
            if 0 <= position[0] < canvas.winfo_width() and 0 <= position[1] < canvas.winfo_height():
                return area, position
        return None

    def route(self, delta):
        if not math.isfinite(delta) or abs(delta) > 10:
            return False
        target = self._target()
        if target is None:
            return False
        area, position = target
        previous = self.pending.get(area, (0, position))[0]
        self.pending[area] = previous+delta, position
        return True

    def flush(self):
        updates = list(self.pending.items())
        self.pending.clear()
        for area, (delta, position) in updates:
            try:
                if area.canvas.winfo_exists():
                    area.magnify(delta, position)
            except tk.TclError:
                pass  # The tab may have closed after the gesture was queued.

    def discard(self, area):
        self.active = False
        self.areas.discard(area)
        self.pending.pop(area, None)
        if not self.areas:
            self.close()

    def close(self):
        self.active = False
        if self.job is not None:
            self.root.after_cancel(self.job)
            self.job = None
        self.pending.clear()
        self.events.clear()
        if self.token:
            self.remove_monitor(self.event_class, self.sel('removeMonitor:'), self.token)
            self.release(self.token, self.sel('release'))
            self.token = None
        if getattr(self.root, '_se_magnify_monitor', None) is self:
            self.root._se_magnify_monitor = None


def register(area):
    root = area.canvas._root()
    monitor = getattr(root, '_se_magnify_monitor', None)
    if monitor is None:
        try:
            monitor = MagnifyMonitor(root)
        except (OSError, AttributeError, RuntimeError, ValueError):
            logging.getLogger(__name__).exception('Could not enable native macOS pinch zoom')
            return None
        root._se_magnify_monitor = monitor
    monitor.areas.add(area)
    return monitor
