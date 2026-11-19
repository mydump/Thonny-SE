# SPDX-FileCopyrightText: 2026 Sebastian Ladhoff
# SPDX-License-Identifier: GPL-3.0-only
# See LICENSE in the project root for the full license text.

"""Rounded surface for UML row editing and deletion."""
from .i18n import tr
from .display_context import context_for
import tkinter as tk
from tkinter import font as tkfont

from .ui_style import UML_SECTION_FILLS, UML_SECTION_INKS, UML_SECTION_BADGES, ERROR, FIELD_BORDER, INK, SELECT, SELECTION_FILL
from thonny.ui_utils import create_tooltip

from .uml_gesture_icons import letter_badge

DELETE_FILL = "#fff0ee"
PANEL_INSET = 8
PANEL_SURROUND = "#d6d6d6"


def edit_panel(outer, *, deleting=False, section="methods"):
    fill, accent = (DELETE_FILL, ERROR) if deleting else (UML_SECTION_FILLS[section], UML_SECTION_INKS[section])
    # Native Tk widgets are rectangular. Keep the native rectangle entirely
    # inside the rounded canvas surface drawn by UmlCanvas._place_editor.
    outer.configure(background=fill, highlightthickness=0, borderwidth=0)
    outer._panel_surface = (fill, accent)
    content = tk.Frame(outer, background=fill)
    content.pack(fill="both", expand=True, padx=PANEL_INSET, pady=4)
    return content

def panel_badge(parent, section, font, *, deleting=False):
    fill, accent = (DELETE_FILL, ERROR) if deleting else (UML_SECTION_FILLS[section], UML_SECTION_INKS[section])
    badge = tk.Canvas(parent, width=35, height=36, background=fill, highlightthickness=0)
    def size(state):
        badge.configure(width=round(35*state.ui_scale),height=round(36*state.ui_scale))
        paint_panel_badge(badge,section,font,accent)
    context_for(badge).subscribe(badge,size)
    size(context_for(badge).state)
    badge.bind("<Configure>", lambda event: paint_panel_badge(badge, section, font, accent))
    return badge


def paint_panel_badge(canvas, section, font, color):
    fill = "#faddd9" if color == ERROR else UML_SECTION_BADGES[section]
    color = ERROR if color == ERROR else UML_SECTION_INKS[section]
    actual = tkfont.nametofont("TkDefaultFont",root=canvas).actual()
    radius = 12*context_for(canvas).state.ui_scale
    key = (canvas.winfo_width(),canvas.winfo_height(),section,color,fill,radius,
           actual['family'],'bold')
    if getattr(canvas,'_badge_paint_key',None) == key and canvas.find_withtag('insert'):
        return
    canvas._badge_paint_key=key
    canvas.delete("all")
    letter_badge(canvas,canvas.winfo_width()/2,canvas.winfo_height()/2,
                 section,color,fill,font,radius=radius,tags=("insert",))


def delete_switch(parent, active, command, *, background=None):
    fill = DELETE_FILL if active else background or SELECTION_FILL
    switch = tk.Canvas(parent, width=63, height=35, background=fill, takefocus=True,
                       highlightthickness=0)
    track = ERROR if active else "#a6b4c3"
    switch.create_rectangle(18, 5, 45, 30, fill=track, outline="", tags="insert")
    for center in (18, 45):
        switch.create_oval(center-12, 5, center+12, 30, fill=track, outline="")
    x = 45 if active else 18
    knob = switch.create_oval(x-11, 6, x+11, 29, fill="white", outline="")
    ink = ERROR if active else "#47586b"
    switch.create_line(x-7, 13, x+7, 13, fill=ink, width=1.5, capstyle="round")
    switch.create_line(x-5, 13, x-4, 23, x+4, 23, x+5, 13, fill=ink, width=1.5, joinstyle="round")
    switch.create_line(x-3, 13, x-3, 10, x+3, 10, x+3, 13, fill=ink, width=1.5, joinstyle="round")
    for offset in (-2, 2):
        switch.create_line(x+offset, 16, x+offset, 21, fill=ink, capstyle="round")
    focus_fill = "#faddd9" if active else "#dceaff"
    switch.bind("<FocusIn>", lambda event: switch.itemconfigure(knob, fill=focus_fill))
    switch.bind("<FocusOut>", lambda event: switch.itemconfigure(knob, fill="white"))
    create_tooltip(switch, tr('Disable delete mode (Esc)') if active else tr('Enable delete mode'))
    for key in ("<ButtonRelease-1>", "<Return>", "<KP_Enter>", "<space>"):
        switch.bind(key, lambda event: command() or "break")
    base_widths = {item:float(switch.itemcget(item,'width')) for item in switch.find_all()}
    switch._se_control_scale = 1.0
    def size(state):
        scale=state.ui_scale
        switch.scale('all',0,0,scale/switch._se_control_scale,scale/switch._se_control_scale)
        switch._se_control_scale=scale
        switch.configure(width=round(63*scale),height=round(35*scale))
        for item,width in base_widths.items():switch.itemconfigure(item,width=width*scale)
    context_for(switch).subscribe(switch,size)
    size(context_for(switch).state)
    return switch


def picker(parent, build_field, choices, select, *, editable=True):
    frame = tk.Frame(parent, background="white", highlightthickness=1, highlightbackground=FIELD_BORDER)
    field = build_field(frame)
    field.pack(side="left", fill="both", expand=True)
    arrow = tk.Label(frame, text="⌄", foreground=SELECT, background="white", padx=4, pady=0,
                     borderwidth=0, font=field.cget("font"))
    arrow.pack(side="right", fill="y")
    menu = tk.Menu(frame, tearoff=False)
    for value, label in choices:
        menu.add_command(label=label, command=lambda value=value: select(value))

    def popup(event):
        field.focus_set()
        try:
            menu.tk_popup(frame.winfo_rootx(), frame.winfo_rooty()+frame.winfo_height())
        finally:
            menu.grab_release()
        return "break"

    arrow.bind("<Button-1>", popup)
    field.bind("<Alt-Down>", popup)
    if not editable:
        field.bind("<Button-1>", popup)
        field.bind("<space>", popup)
        field.bind("<Down>", popup)
    return frame, field


def header_picker(parent, variable, choices, *, width, editable=False):
    def build_field(frame):
        options = dict(textvariable=variable, width=width, background="white", foreground=INK, borderwidth=0,
                       highlightthickness=0, takefocus=True)
        if editable:
            return tk.Entry(frame, insertbackground=INK, relief="flat", **options)
        return tk.Label(frame, anchor="w", padx=4, pady=1, **options)

    frame, field = picker(parent, build_field, ((value, value or tr('No base class')) for value in choices),
                          variable.set, editable=editable)
    field.bind("<FocusIn>", lambda event: frame.configure(highlightbackground=SELECT))
    field.bind("<FocusOut>", lambda event: frame.configure(highlightbackground=FIELD_BORDER))
    return frame, field


class DeleteButton(tk.Canvas):
    def __init__(self, parent, font, command):
        super().__init__(parent, width=font.measure(tr('Delete'))+24, height=font.metrics("linespace")+12,
                         background=DELETE_FILL, highlightthickness=0, takefocus=True)
        self.font = font
        self.command = command
        self.hovered = False
        self.focused = False
        self.bind("<Configure>", self.draw)
        self.bind("<Enter>", lambda event: self._set_state("hovered", True))
        self.bind("<Leave>", lambda event: self._set_state("hovered", False))
        self.bind("<FocusIn>", lambda event: self._set_state("focused", True))
        self.bind("<FocusOut>", lambda event: self._set_state("focused", False))
        self.bind("<ButtonRelease-1>", self._click)
        self.bind("<Return>", lambda event: self.invoke() or "break")
        self.bind("<KP_Enter>", lambda event: self.invoke() or "break")
        self.bind("<space>", lambda event: self.invoke() or "break")

    def _set_state(self, field, value):
        setattr(self, field, value)
        self.draw()

    def draw(self, event=None):
        self.delete("all")
        w, h = self.winfo_width()-1, self.winfo_height()-1
        self.create_polygon(1, 8, 1, 1, 8, 1, w-8, 1, w, 1, w, 8, w, h-8, w, h,
                            w-8, h, 8, h, 1, h, 1, h-8, smooth=True,
                            fill="#faddd9" if self.hovered else "#fff8f7", outline=ERROR,
                            width=2 if self.focused else 1)
        self.create_text(w/2, h/2, text=tr('Delete'), font=self.font, fill=ERROR)

    def _click(self, event):
        if 0 <= event.x < self.winfo_width() and 0 <= event.y < self.winfo_height():
            self.invoke()

    def invoke(self):
        self.command()
