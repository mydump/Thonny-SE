# SPDX-FileCopyrightText: 2026 Sebastian Ladhoff
# SPDX-License-Identifier: GPL-3.0-only
# See LICENSE in the project root for the full license text.

"""Vertikale Bausteinpalette mit einfachem und vollständigem Umfang."""
from .scrolling import ScrollArea
from .display_context import context_for
from .visual_metrics import Typography
from .i18n import tr
import tkinter as tk
from tkinter import ttk

from .canvas import HEADER
from .diagram_preferences import uses_dark_diagrams
from .model import IF_KINDS
from .ui_style import DARK_DIAGRAM_COLORS, EDGE, INK, SELECT, draw_chevron

SIMPLE = (("statement", 'Statement'), ("if", 'Selection'), ("while", 'Loop'))
COMPLETE = (
    ("statement", 'Statement'), ("call", 'Function call'),
    ("if_single", 'One-way selection'), ("if", 'Two-way selection'),
    ("switch", 'Multiway selection'), ("while", 'Conditional loop'),
    ("repeat", 'Fixed-count loop'), ("for", 'Counting loop'),
    ("foreach", 'For each element'),
)


class DisclosureSwitch(tk.Canvas):
    """Großer einzelner Pfeil am Ende der Bausteinliste."""
    def __init__(self, master, command, background):
        super().__init__(master, width=190, height=34, background=background,
                         highlightthickness=0, takefocus=True)
        self.command = command
        self.expanded = False
        self.focused = False
        self.hovered = False
        self.bind("<Configure>", lambda event: self.draw())
        self.bind("<Button-1>", self.invoke)
        self.bind("<Return>", self.invoke)
        self.bind("<KP_Enter>", self.invoke)
        self.bind("<space>", self.invoke)
        self.bind("<FocusIn>", lambda event: self._state(focused=True))
        self.bind("<FocusOut>", lambda event: self._state(focused=False))
        self.bind("<Enter>", lambda event: self._state(hovered=True))
        self.bind("<Leave>", lambda event: self._state(hovered=False))

    def _state(self, **values):
        for name, value in values.items():
            setattr(self, name, value)
        self.draw()

    def set_expanded(self, value):
        self.expanded = value
        self.draw()

    def draw(self):
        self.delete("all")
        width, height = self.winfo_width(), self.winfo_height()
        if width < 2:
            return
        self.label = tr('Fewer blocks') if self.expanded else tr('All blocks')
        cx, cy = width/2, height/2
        dy = -1 if self.expanded else 1
        draw_chevron(self, cx, cy, dy, SELECT if self.hovered else getattr(self, "ink", INK))
        if self.focused:
            self.create_rectangle(1, 1, width-1, height-1, outline=SELECT if self.focused else EDGE)

    def invoke(self, event=None):
        self.focus_set()
        self.command()
        return "break"


class PaletteButton(tk.Canvas):
    def __init__(self, master, kind, label, command):
        super().__init__(master, width=184, height=64, background="#ffffff",
                         highlightthickness=1, highlightbackground=EDGE,
                         takefocus=True)
        self.command = command
        self.label = label
        self.kind = kind
        self.symbol = self.create_rectangle(10, 17, 50, 45, fill=HEADER[kind], outline=INK)
        if kind == "statement":
            self.create_line(18, 27, 42, 27, fill=INK)
            self.create_line(18, 34, 36, 34, fill=INK)
        elif kind == "call":
            self.create_line(15, 17, 15, 45, fill=INK)
            self.create_line(45, 17, 45, 45, fill=INK)
        elif kind in IF_KINDS or kind == "switch":
            self.create_line(10, 17, 30, 33, 50, 17, fill=INK)
            self.create_line(30, 33, 30, 45, fill=INK)
            if kind == "switch":
                self.create_line(20, 25, 20, 45, fill=INK)
        else:
            self.create_line(19, 27, 50, 27, fill=INK)
            self.create_line(19, 27, 19, 45, fill=INK)
        self.label_item = self.create_text(62, 32, text=label, width=120, anchor="w", fill=INK)
        self.addtag_all("content")
        self._content_offset = 0
        self._content_scale = 1.0
        self.typography = Typography(self)
        self.itemconfigure(self.label_item,font=self.typography["body"])
        context_for(self).subscribe(self,self._display_changed)
        self._display_changed(context_for(self).state)
        self.bind("<Configure>", self._layout)
        self.bind("<Button-1>", self.invoke)
        self.bind("<Return>", self.invoke)
        self.bind("<KP_Enter>", self.invoke)
        self.bind("<space>", self.invoke)
        self.bind("<FocusIn>", lambda event: self.refresh_appearance(focused=True))
        self.bind("<FocusOut>", lambda event: self.refresh_appearance(focused=False))
        self.refresh_appearance()

    def refresh_appearance(self, *, focused=None):
        colors = DARK_DIAGRAM_COLORS if uses_dark_diagrams() else {}
        if focused is None:
            focused = self.focus_get() is self
        border = SELECT if focused else EDGE
        self.configure(background=colors.get("#ffffff", "#ffffff"),
                       highlightbackground=colors.get(border, border))
        fill = HEADER[self.kind]
        ink = colors.get(INK, INK)
        self.itemconfigure("content", fill=ink)
        self.itemconfigure(self.symbol, fill=colors.get(fill, fill), outline=ink)

    def _display_changed(self, state):
        self.typography.refresh()
        scale = state.ui_scale
        self.move('content',0,-self._content_offset)
        self._content_offset = 0
        self.scale('content',0,0,scale/self._content_scale,scale/self._content_scale)
        self._content_scale = scale
        self.configure(width=round(184*scale),height=round(64*scale))
        self._layout(type('Size',(),dict(width=self.winfo_width(),height=self.winfo_height()))())

    def _layout(self, event):
        offset = event.height/2-32*self._content_scale
        self.move("content", 0, offset-self._content_offset)
        self._content_offset = offset
        self.itemconfigure(self.label_item, width=max(40, event.width-70*self._content_scale))

    def set_label(self, text):
        self.label = text
        self.itemconfigure(self.label_item, text=text)

    def invoke(self, event=None):
        self.focus_set()
        self.command()
        return "break"


class ElementPalette(ttk.Frame):
    def __init__(self, master, mode_variable, on_insert):
        super().__init__(master, width=220, padding=6, borderwidth=1, relief="solid")
        self.grid_propagate(False)
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)
        self.mode_variable = mode_variable
        background = ttk.Style(self).lookup("TFrame", "background") or "#ececec"
        self.canvas = tk.Canvas(self, width=190, highlightthickness=0, background=background, yscrollincrement=16)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.scrollbar.grid(row=0, column=1, sticky="ns")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.content = ttk.Frame(self.canvas)
        self.window = self.canvas.create_window(0, 0, window=self.content, anchor="nw")
        self.scrolling = ScrollArea(self.canvas, self, axes="y")
        self.buttons = {}
        for kind, label in COMPLETE:
            button = PaletteButton(self.content, kind, tr(label), lambda kind=kind: on_insert(kind))
            self.buttons[kind] = button
            button.bind("<FocusIn>", lambda event, kind=kind: self.reveal(kind), add=True)
            self._bind_scroll(button)
        self.disclosure = DisclosureSwitch(self.content, self.toggle_extent, background)
        self._bind_scroll(self.disclosure)
        self.bind("<<ThemeChanged>>", lambda event: self.after_idle(self._update_theme))
        self.canvas.bind("<Configure>", self._resize)
        self.canvas.bind("<Map>", lambda event: self.after_idle(self._redraw_mapped))
        self.content.bind("<Configure>", lambda event: self._sync_scrollbar())
        for surface in (self, self.canvas, self.content, self.scrollbar):
            self._bind_scroll(surface)
        self._mode_trace = mode_variable.trace_add("write", self._mode_changed)
        if mode_variable.get() not in ("Einfach", "Vollständig"):
            mode_variable.set("Einfach")
        self._mode_changed()
        context_for(self).subscribe(self,self._display_changed)
        self._display_changed(context_for(self).state)

    def _display_changed(self,state):
        self.configure(width=round(220*state.ui_scale))
        self.disclosure.configure(height=round(34*state.ui_scale))
        self.after_idle(self._sync_scrollbar)

    def _update_theme(self):
        if not self.winfo_exists():
            return
        style = ttk.Style(self)
        background = style.lookup("TFrame", "background") or "#ececec"
        self.canvas.configure(background=background)
        self.disclosure.configure(background=background)
        self.disclosure.ink = style.lookup("TLabel", "foreground") or INK
        self.disclosure.draw()

    def refresh_appearance(self):
        for button in self.buttons.values():
            button.refresh_appearance()
        self._update_theme()

    def _redraw_mapped(self):
        if not self.winfo_exists() or not self.winfo_ismapped():
            return
        self._update_theme()
        self.canvas.itemconfigure(self.window, width=self.canvas.winfo_width())
        self._sync_scrollbar()
        # Auch die eingebetteten Canvas-Karten nach dem Tabwechsel invalidieren.
        for kind in self.visible_kinds():
            self.buttons[kind].itemconfigure("content", state="normal")
        self.disclosure.draw()

    def set_mode(self, mode):
        if mode not in ("Einfach", "Vollständig"):
            raise ValueError(tr('Unknown palette extent'))
        self.mode_variable.set(mode)

    def toggle_extent(self):
        self.set_mode("Vollständig" if self.mode_variable.get() == "Einfach" else "Einfach")

    def entries(self):
        return tuple((kind, tr(label)) for kind, label in (SIMPLE if self.mode_variable.get() == "Einfach" else COMPLETE))

    def visible_kinds(self):
        return [kind for kind, _ in self.entries()]

    def _mode_changed(self, *_):
        self.disclosure.set_expanded(self.mode_variable.get() == "Vollständig")
        self.disclosure.pack_forget()
        for button in self.buttons.values():
            button.pack_forget()
        for kind, label in self.entries():
            button = self.buttons[kind]
            button.set_label(label)
            button.pack(fill="x", padx=2, pady=(0, 6))
        self.disclosure.pack(fill="x", padx=2, pady=(0, 6))
        self.canvas.yview_moveto(0)
        self.after_idle(self._sync_scrollbar)

    def _resize(self, event):
        self.canvas.itemconfigure(self.window, width=event.width)
        self._sync_scrollbar()

    def _sync_scrollbar(self):
        if not self.winfo_exists():
            return
        height = self.natural_height()
        display_height = height
        # Feste Kartenhöhe; die freie Fläche darunter bleibt im neutralen Grau.
        self.canvas.itemconfigure(self.window, height=display_height)
        self.canvas.configure(scrollregion=(0, 0, self.canvas.winfo_width(), display_height))
        if height > self.canvas.winfo_height():
            self.scrollbar.grid()
        else:
            self.scrollbar.grid_remove()
            self.canvas.yview_moveto(0)

    def _bind_scroll(self, widget):
        self.scrolling.bind(widget)

    def natural_height(self):
        return sum(self.buttons[kind].winfo_reqheight()+6 for kind in self.visible_kinds()) + self.disclosure.winfo_reqheight()+6

    def reveal(self, kind):
        if kind not in self.visible_kinds():
            return
        self.update_idletasks()
        button = self.buttons[kind]
        top = self.canvas.canvasy(0)
        y = button.winfo_y()
        bottom = y+button.winfo_height()
        height = self.canvas.winfo_height()
        total = max(1, self.content.winfo_height())
        if y < top:
            self.canvas.yview_moveto(y/total)
        elif bottom > top+height:
            self.canvas.yview_moveto(max(0, bottom-height)/total)

    def destroy(self):
        if self._mode_trace:
            self.mode_variable.trace_remove("write", self._mode_trace)
            self._mode_trace = None
        super().destroy()
