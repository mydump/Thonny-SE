# SPDX-FileCopyrightText: 2026 Sebastian Ladhoff
# SPDX-License-Identifier: GPL-3.0-only
# See LICENSE in the project root for the full license text.

"""Read-only, per-window display state and coalesced change notifications.

Never changes process DPI awareness, global Tk scaling or Thonny's theme.
Screen movement is presentation state, not a document/model operation.
"""
from dataclasses import dataclass
import ctypes
from functools import lru_cache
import logging
import math
import tkinter as tk
from tkinter import font
import weakref

LOG = logging.getLogger(__name__)


@dataclass(frozen=True)
class DisplayState:
    """Tk UI scale is distinct from OS display mode and physical backing pixels."""
    backend: str
    tk_version: str
    pixels_per_point: float
    font_spec: tuple
    ui_scale: float
    backing_scale: float | None = None
    dpi_awareness: str = 'unknown'
    window_dpi: int | None = None

    @property
    def host_mixed_dpi_limited(self):
        return self.backend == 'win32' and self.dpi_awareness in ('unaware', 'system')

    @property
    def native_paths(self):
        return self.backend == 'aqua'

    @property
    def raster_pixels_per_unit(self):
        # Win32 per-monitor-aware and X11 canvas coordinates are raster pixels.
        # Aqua backing pixels differ from canvas units: photos are not a
        # verified high-resolution surface there, so use native paths.
        return self.backing_scale if self.backend == 'aqua' else 1.0


def valid_scale(value, fallback=1.0):
    try:
        value = float(value)
        return value if math.isfinite(value) and 0.25 <= value <= 8 else fallback
    except (TypeError, ValueError):
        return fallback


@lru_cache(maxsize=1)
def _objc_api():
    objc = ctypes.CDLL('/usr/lib/libobjc.A.dylib')
    objc.objc_getClass.argtypes = (ctypes.c_char_p,)
    objc.objc_getClass.restype = ctypes.c_void_p
    objc.sel_registerName.argtypes = (ctypes.c_char_p,)
    objc.sel_registerName.restype = ctypes.c_void_p
    address = ctypes.cast(objc.objc_msgSend,ctypes.c_void_p).value
    pointer = ctypes.CFUNCTYPE(ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p)(address)
    integer = ctypes.CFUNCTYPE(ctypes.c_ulong,ctypes.c_void_p,ctypes.c_void_p)(address)
    indexed = ctypes.CFUNCTYPE(ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_ulong)(address)
    decimal = ctypes.CFUNCTYPE(ctypes.c_double,ctypes.c_void_p,ctypes.c_void_p)(address)
    string = ctypes.CFUNCTYPE(ctypes.c_char_p,ctypes.c_void_p,ctypes.c_void_p)(address)
    return objc,pointer,integer,indexed,decimal,string


def _aqua_backing_scale(widget):
    """Find an unambiguous NSWindow owned by this Tk process, without pointer casts.

    Tk window ids are NOT NSWindow/NSView pointers. Never message those ids.
    Ambiguous/missing titles report unknown, not a guessed display factor.
    """
    objc,ptr,count,at,number,string = _objc_api()
    selector = lambda text: objc.sel_registerName(text.encode())
    app = ptr(objc.objc_getClass(b'NSApplication'),selector('sharedApplication'))
    windows = ptr(app,selector('windows'))
    title = widget.winfo_toplevel().title()
    matches = []
    for index in range(count(windows,selector('count'))):
        window = at(windows,selector('objectAtIndex:'),index)
        name = ptr(window,selector('title'))
        raw = string(name,selector('UTF8String')) if name else None
        if raw is not None and raw.decode('utf-8') == title:
            matches.append(window)
    return valid_scale(number(matches[0],selector('backingScaleFactor'))) if len(matches) == 1 else None


def _win32_state(widget):
    from ctypes import wintypes
    user = ctypes.WinDLL('user32',use_last_error=True)
    user.GetAncestor.argtypes = (wintypes.HWND,wintypes.UINT)
    user.GetAncestor.restype = wintypes.HWND
    handle = user.GetAncestor(widget.winfo_toplevel().winfo_id(),2)
    awareness,dpi = 'unknown',None
    if hasattr(user,'GetWindowDpiAwarenessContext'):
        user.GetWindowDpiAwarenessContext.argtypes = (wintypes.HWND,)
        user.GetWindowDpiAwarenessContext.restype = ctypes.c_void_p
        user.GetAwarenessFromDpiAwarenessContext.argtypes = (ctypes.c_void_p,)
        user.GetAwarenessFromDpiAwarenessContext.restype = ctypes.c_int
        context = user.GetWindowDpiAwarenessContext(handle)
        awareness = {0:'unaware',1:'system',2:'per_monitor'}.get(user.GetAwarenessFromDpiAwarenessContext(context),'unknown')
        if awareness == 'per_monitor' and hasattr(user,'AreDpiAwarenessContextsEqual'):
            user.AreDpiAwarenessContextsEqual.argtypes = (ctypes.c_void_p,ctypes.c_void_p)
            user.AreDpiAwarenessContextsEqual.restype = wintypes.BOOL
            if user.AreDpiAwarenessContextsEqual(context,ctypes.c_void_p(-4)):
                awareness = 'per_monitor_v2'
    if hasattr(user,'GetDpiForWindow'):
        user.GetDpiForWindow.argtypes = (wintypes.HWND,)
        user.GetDpiForWindow.restype = wintypes.UINT
        dpi = user.GetDpiForWindow(handle) or None
    return awareness,dpi


def inspect_display(widget):
    top = widget.winfo_toplevel()
    backend = str(widget.tk.call('tk','windowingsystem'))
    factor = valid_scale(widget.tk.call('tk','scaling','-displayof',top),96/72)
    base = font.nametofont('TkDefaultFont',root=widget)
    spec = tuple(sorted(base.actual().items()))
    backing,awareness,dpi = None,'unknown',None
    try:
        if backend == 'aqua':
            backing = _aqua_backing_scale(top)
        elif backend == 'win32':
            awareness,dpi = _win32_state(top)
    except (OSError,AttributeError,ValueError,tk.TclError):
        LOG.debug('Native display information unavailable',exc_info=True)
    return DisplayState(backend,str(widget.tk.call('package','require','Tk')),
                        factor,spec,valid_scale(factor/(96/72)),backing,awareness,dpi)


class DisplayContext:
    """One observer per toplevel; events plus a mapped-window safety check."""
    def __init__(self, top):
        self.top = top
        self.state = inspect_display(top)
        self.generation = 0
        self._listeners = {}
        self._pending = None
        self._poll_timer = None
        self._closed = False
        self._bindings = [(event,top.bind(event,self._schedule,add=True))
                          for event in ('<Configure>','<Map>','<FocusIn>','<<ThemeChanged>>','<<TkWorldChanged>>')]
        self._destroy_binding = top.bind('<Destroy>',self._destroy,add=True)

    def _schedule(self,event=None):
        if self._closed or (event is not None and event.widget is not self.top):
            return
        if self._pending is None:
            self._pending = self.top.after(80,self.refresh)
        self._ensure_poll()

    def _ensure_poll(self):
        # Tk does not expose every native backing/DPI notification. Keep one
        # modest fallback per visible toplevel, never one timer per component.
        if (not self._closed and self._listeners and self._poll_timer is None
                and self.top.winfo_ismapped()):
            self._poll_timer = self.top.after(750,self._poll)

    def _poll(self):
        self._poll_timer = None
        if self._closed or not self.top.winfo_ismapped():return
        self.refresh()
        self._ensure_poll()

    def refresh(self, *, force=False):
        if self._closed:return False
        if self._pending is not None:
            self.top.after_cancel(self._pending)
            self._pending = None
        state = inspect_display(self.top)
        if not force and state == self.state:return False
        self.state = state
        self.generation += 1
        for token,(owner,callback) in list(self._listeners.items()):
            widget = owner()
            if widget is None or not widget.winfo_exists():
                self._listeners.pop(token,None)
                continue
            target = callback() if isinstance(callback,weakref.WeakMethod) else callback
            if target is None:
                self._listeners.pop(token,None)
                continue
            if target is not None:
                try:target(state)
                except Exception:
                    self.top.report_callback_exception(*__import__('sys').exc_info())
        return True

    def subscribe(self, widget, callback):
        token = object()
        callback = weakref.WeakMethod(callback) if getattr(callback,'__func__',None) is not None else callback
        self._listeners[token] = (weakref.ref(widget),callback)
        self._ensure_poll()
        def remove():self._listeners.pop(token,None)
        widget.bind('<Destroy>',lambda event: remove() if event.widget is widget else None,add=True)
        return remove

    def _destroy(self,event):
        if event.widget is self.top:
            self._closed=True
            if self._pending is not None:self.top.after_cancel(self._pending)
            if self._poll_timer is not None:self.top.after_cancel(self._poll_timer)
            self._listeners.clear()


def context_for(widget):
    top = widget.winfo_toplevel()
    if not hasattr(top,'_se_display_context'):
        top._se_display_context = DisplayContext(top)
    return top._se_display_context
