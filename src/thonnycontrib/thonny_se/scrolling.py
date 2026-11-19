# SPDX-FileCopyrightText: 2026 Sebastian Ladhoff
# SPDX-License-Identifier: GPL-3.0-only
# See LICENSE in the project root for the full license text.

"""Local scrolling for Tk 8 mouse wheels and Tk 9 high-resolution devices.

Tk TIP 684 stores signed X/Y deltas in TouchpadScroll's 32-bit delta.
Bindings belong only to our scroll areas; the IDE's global bindings stay intact.
"""
import math
import tkinter as tk
from tkinter import ttk
from .zooming import event_position


def precise_deltas(packed):
    """Unpack signed 16-bit axes, including Python's unsigned event values."""
    packed = int(packed)
    x, y = (packed >> 16) & 0xffff, packed & 0xffff
    return (x-65536 if x >= 32768 else x,
            y-65536 if y >= 32768 else y)


def wheel_pixels(event, *, aqua=False, precise=False):
    if precise:
        x, y = precise_deltas(event.delta)
        if event.state & 1 and not x:
            x, y = y, 0
        return -x, -y
    button = getattr(event, 'num', None)
    if button in (4, 5, 6, 7):
        distance = -40 if button in (4, 6) else 40
        return (distance, 0) if button in (6, 7) or event.state & 1 else (0, distance)
    delta = getattr(event, 'delta', 0)
    # Old Aqua Tk reports small deltas; Windows and Tk 9 wheels use 120/tick.
    distance = -delta*12 if aqua and abs(delta) < 120 else -delta/120*40
    return (distance, 0) if event.state & 1 else (0, distance)


class ScrollArea:
    def __init__(self, canvas, owner=None, *, axes='xy', fallback_x=False, zoom=None, zoom_at=None):
        self.canvas, self.axes, self.fallback_x, self.zoom = canvas, axes, fallback_x, zoom
        self.zoom_at=zoom_at
        self.aqua = canvas.tk.call('tk', 'windowingsystem') == 'aqua'
        self.remainder = {'x': 0.0, 'y': 0.0}
        self.zoom_remainder = 0.0
        self.magnify_remainder = 0.0
        self.magnify_monitor = None
        self.tag = 'SEScroll:' + str(canvas)
        self.sequences = []
        # Canvas units otherwise depend on the viewport size (or a 16px grid).
        # Pixel units keep slow gestures and diagonal movement precise.
        canvas.configure(xscrollincrement=1, yscrollincrement=1)
        for sequence in ('<MouseWheel>', '<Shift-MouseWheel>', '<Button-4>', '<Button-5>',
                         '<Shift-Button-4>', '<Shift-Button-5>', '<Button-6>', '<Button-7>'):
            self._bind_sequence(sequence, self.handle)
        if zoom is not None or zoom_at is not None:
            modifiers = ('Control', 'Command') if self.aqua else ('Control',)
            for modifier in modifiers:
                for gesture in ('MouseWheel', 'Button-4', 'Button-5'):
                    self._bind_sequence(f'<{modifier}-{gesture}>', self.handle)
                self._bind_sequence(f'<{modifier}-TouchpadScroll>',
                                    lambda event: self.handle(event, precise=True))
        self._bind_sequence('<TouchpadScroll>', lambda event: self.handle(event, precise=True))
        if self.aqua and (zoom is not None or zoom_at is not None):
            from .macos_gestures import register
            self.magnify_monitor = register(self)
        canvas.bind('<Destroy>', self.destroy, add=True)
        self.bind(canvas)
        if owner is not None:
            self.bind(owner)

    def _bind_sequence(self, sequence, callback):
        try:
            self.canvas.bind_class(self.tag, sequence, callback)
            self.sequences.append(sequence)
        except tk.TclError:
            pass  # Older Tk has no TouchpadScroll; some platforms lack buttons 6/7.

    def bind(self, widget):
        if isinstance(widget, (tk.Menu, tk.Toplevel)):
            return
        tags = tuple(tag for tag in widget.bindtags() if tag != self.tag)
        widget.bindtags((self.tag, *tags))
        for child in widget.winfo_children():
            self.bind(child)

    def _can_move(self, widget, axis, distance):
        try:
            first, last = getattr(widget, axis+'view')()
            return (distance < 0 and first > 0.000001) or (distance > 0 and last < 0.999999)
        except (tk.TclError, AttributeError, ValueError):
            return False

    def _native_child(self, widget, x, y):
        # Nested multiline text/list views keep their native wheel handling
        # until their edge is reached. Entry/Combobox values must not spin.
        return isinstance(widget, (tk.Text, tk.Listbox, ttk.Treeview)) and (
            self._can_move(widget, 'x', x) or self._can_move(widget, 'y', y))

    def handle(self, event, *, precise=False):
        x, y = wheel_pixels(event, aqua=self.aqua, precise=precise)
        zoom_at=getattr(self,"zoom_at",None)
        if (self.zoom is not None or zoom_at is not None) and (event.state & 4 or self.aqua and event.state & 8):
            amount = -y or -x
            if precise:
                self.zoom_remainder += amount/40
                steps = math.trunc(self.zoom_remainder)
                self.zoom_remainder -= steps
            else:
                steps = (1 if amount > 0 else -1) if amount else 0
            if steps:
                steps=max(-3,min(3,steps))
                if zoom_at is not None:zoom_at(steps,event_position(self.canvas,event))
                else:self.zoom(steps)
            return 'break'
        if self._native_child(event.widget, x, y):
            return None
        if self.fallback_x and y and not x:
            first, last = self.canvas.yview()
            if last-first >= .999999:
                x, y = y, 0
        for axis, distance in (('x', x), ('y', y)):
            if axis not in self.axes or not distance:
                continue
            if not self._can_move(self.canvas, axis, distance):
                self.remainder[axis] = 0
                continue
            self.remainder[axis] += distance
            pixels = math.trunc(self.remainder[axis])
            self.remainder[axis] -= pixels
            if pixels:
                getattr(self.canvas, axis+'view_scroll')(pixels, 'units')
        return 'break'

    def magnify(self, delta, position):
        """Native pinch deltas use the same cursor-anchored zoom as the wheel."""
        if not math.isfinite(delta):
            return
        self.magnify_remainder += delta
        # NSD uses 1% zoom precision; retain smaller deltas across frames.
        amount = round(self.magnify_remainder, 2)
        if not amount:
            return
        self.magnify_remainder -= amount
        if self.zoom_at is not None:
            self.zoom_at(amount*10, position)
        elif self.zoom is not None:
            self.zoom(amount*10)

    def destroy(self, event):
        if event.widget is self.canvas:
            if self.magnify_monitor is not None:
                self.magnify_monitor.discard(self)
                self.magnify_monitor = None
            for sequence in self.sequences:
                self.canvas.unbind_class(self.tag, sequence)
