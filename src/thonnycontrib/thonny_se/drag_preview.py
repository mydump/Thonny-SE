# SPDX-FileCopyrightText: 2026 Sebastian Ladhoff
# SPDX-License-Identifier: GPL-3.0-only
# See LICENSE in the project root for the full license text.

"""Passive, translucent palette graphic following a local drag gesture."""
import tkinter as tk
from .palette import PaletteButton


class DragPreview:
    def __init__(self, button, kind):
        self.window = tk.Toplevel(button.winfo_toplevel(), takefocus=False)
        self.window.withdraw()
        self.window.transient(button.winfo_toplevel())
        self.window.overrideredirect(True)
        if self.window.tk.call('tk', 'windowingsystem') == 'aqua':
            try:
                self.window.tk.call('::tk::unsupported::MacWindowStyle', 'style',
                                    self.window._w, 'help', 'noActivates')
            except tk.TclError:
                pass
        try:
            self.window.attributes('-topmost', True, '-alpha', 0.65)
        except tk.TclError:
            pass  # Some window managers do not support alpha-composited windows.
        self.graphic = PaletteButton(self.window, kind, button.label, lambda: None)
        self.graphic.configure(width=max(160,button.winfo_width()-2),height=62,takefocus=False)
        self.graphic.pack()
        self.width = max(162,button.winfo_width())
        self.height = 64
        self.visible = False
        self.redraw_job = None

    def move(self, x, y):
        # Root coordinates can be negative on monitors above/left of the primary.
        # Explicit '+' preserves absolute offsets; '-100' alone means right-relative in Tk.
        left,top = int(x)+16,int(y)+18
        self.window.geometry(f'{self.width}x{self.height}+{left}+{top}')
        if not self.visible:
            self.visible = True
            self.window.deiconify()
            self.window.lift()
            # Aqua may map the translucent window before painting its canvas.
            # Invalidate its items once after the initial window-server commit.
            self.redraw_job = self.window.after(50,self._redraw)

    def _redraw(self):
        self.redraw_job = None
        if self.graphic.winfo_exists():
            self.graphic.itemconfigure('content',state='hidden')
            self.graphic.itemconfigure('content',state='normal')

    def destroy(self):
        try:
            if self.redraw_job is not None:
                self.window.after_cancel(self.redraw_job)
                self.redraw_job = None
            self.window.destroy()
        except tk.TclError:
            pass
