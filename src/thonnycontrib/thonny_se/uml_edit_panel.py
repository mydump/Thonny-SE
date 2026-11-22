# SPDX-FileCopyrightText: 2026 Sebastian Ladhoff
# SPDX-License-Identifier: GPL-3.0-only
# See LICENSE in the project root for the full license text.

"""Rounded surface for UML row editing and deletion."""
from .i18n import tr
from .display_context import context_for
import tkinter as tk
from tkinter import font as tkfont

from .ui_style import ui_color, UML_SECTION_FILLS, UML_SECTION_INKS, UML_SECTION_BADGES, ERROR, FIELD_BORDER, INK, SELECT, SELECTION_FILL
from thonny.ui_utils import create_tooltip

from .uml_gesture_icons import letter_badge
from .graphics import clear_icon_images, clear_shapes, icon, rounded
from .tooltips import attach_tip

DELETE_FILL = "#fff0ee"
PANEL_INSET = 8
PANEL_SURROUND = "#d6d6d6"


def edit_panel(outer, *, deleting=False, section="methods", color=lambda value: value):
    fill, accent = (DELETE_FILL, ERROR) if deleting else (UML_SECTION_FILLS[section], UML_SECTION_INKS[section])
    fill, accent = color(fill), color(accent)
    # Native Tk widgets are rectangular. Keep the native rectangle entirely
    # inside the rounded canvas surface drawn by UmlCanvas._place_editor.
    outer.configure(background=fill, highlightthickness=0, borderwidth=0)
    outer._panel_surface = (fill, accent)
    content = tk.Frame(outer, background=fill)
    content.pack(fill="both", expand=True, padx=PANEL_INSET, pady=4)
    return content

def panel_badge(parent, section, font, *, deleting=False, color=lambda value: value):
    fill, accent = (DELETE_FILL, ERROR) if deleting else (UML_SECTION_FILLS[section], UML_SECTION_INKS[section])
    badge = tk.Canvas(parent, width=35, height=36, background=color(fill), highlightthickness=0)
    def size(state):
        badge.configure(width=round(35*state.ui_scale),height=round(36*state.ui_scale))
        paint_panel_badge(badge,section,font,accent,color_map=color)
    context_for(badge).subscribe(badge,size)
    size(context_for(badge).state)
    badge.bind("<Configure>", lambda event: paint_panel_badge(badge, section, font, accent, color_map=color))
    return badge


def paint_panel_badge(canvas, section, font, color, *, color_map=lambda value: value):
    fill = "#faddd9" if color == ERROR else UML_SECTION_BADGES[section]
    color = ERROR if color == ERROR else UML_SECTION_INKS[section]
    fill, color = color_map(fill), color_map(color)
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
    fill = ui_color(DELETE_FILL) if active else background or ui_color(SELECTION_FILL)
    switch = tk.Canvas(parent, width=63, height=35, background=fill, takefocus=True,
                       highlightthickness=0)
    track = ui_color(ERROR) if active else ui_color("#a6b4c3")
    ink = ui_color(ERROR) if active else ui_color("#47586b")
    focus_fill = ui_color("#faddd9") if active else ui_color("#dceaff")
    knob_fill = ui_color("white")
    face = tkfont.nametofont("TkDefaultFont", root=switch).copy()
    context = context_for(switch)
    center_x = 45 if active else 18

    def show_focus(focused):
        switch.itemconfigure("knob-normal", state="hidden" if focused else "normal")
        switch.itemconfigure("knob-focus", state="normal" if focused else "hidden")

    def resize(state):
        scale = state.ui_scale
        switch.configure(width=round(63 * scale), height=round(35 * scale))
        face.configure(size=-round(14 * scale))
        for group in ("track", "knob-normal", "knob-focus", "insert"):
            clear_shapes(switch, group)
        clear_icon_images(switch)
        rounded(switch, *(value * scale for value in (6, 5, 57, 30)),
                radius=12 * scale, fill=track, outline=track, group="track")
        bounds = tuple(value * scale for value in (center_x - 11, 6, center_x + 11, 29))
        for group, color in (("knob-normal", knob_fill), ("knob-focus", focus_fill)):
            rounded(switch, *bounds, radius=11 * scale, fill=color, outline=color, group=group)
        icon(switch, center_x * scale, 17.5 * scale, "edit.delete", face, ink,
             pixels=14 * scale, tags=("insert",))
        show_focus(switch.focus_get() is switch)

    context.subscribe(switch, resize)
    resize(context.state)
    switch.bind("<FocusIn>", lambda event: show_focus(True))
    switch.bind("<FocusOut>", lambda event: show_focus(False))
    attach_tip(switch, tr("Disable delete mode (Esc)") if active else tr("Enable delete mode"))
    for key in ("<ButtonRelease-1>", "<Return>", "<KP_Enter>", "<space>"):
        switch.bind(key, lambda event: command() or "break")
    return switch


def picker(parent, build_field, choices, select, *, editable=True, color=lambda value: value):
    frame = tk.Frame(parent, background=color("white"), highlightthickness=1, highlightbackground=color(FIELD_BORDER))
    field = build_field(frame)
    field.pack(side="left", fill="both", expand=True)
    arrow = tk.Label(frame, text="⌄", foreground=color(SELECT), background=color("white"), padx=4, pady=0,
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


def header_picker(parent, variable, choices, *, width, editable=False, color=lambda value: value):
    def build_field(frame):
        options = dict(textvariable=variable, width=width, background=color("white"), foreground=color(INK), borderwidth=0,
                       highlightthickness=0, takefocus=True)
        if editable:
            return tk.Entry(frame, insertbackground=color(INK), relief="flat", **options)
        return tk.Label(frame, anchor="w", padx=4, pady=1, **options)

    frame, field = picker(parent, build_field, ((value, value or tr('No base class')) for value in choices),
                          variable.set, editable=editable, color=color)
    field.bind("<FocusIn>", lambda event: frame.configure(highlightbackground=color(SELECT)))
    field.bind("<FocusOut>", lambda event: frame.configure(highlightbackground=color(FIELD_BORDER)))
    return frame, field


class DeleteButton(tk.Canvas):
    def __init__(self, parent, font, command):
        super().__init__(parent, width=font.measure(tr('Delete'))+24, height=font.metrics("linespace")+12,
                         background=ui_color(DELETE_FILL), highlightthickness=0, takefocus=True)
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
                            fill=ui_color("#faddd9") if self.hovered else ui_color("#fff8f7"), outline=ui_color(ERROR),
                            width=2 if self.focused else 1)
        self.create_text(w/2, h/2, text=tr('Delete'), font=self.font, fill=ui_color(ERROR))

    def _click(self, event):
        if 0 <= event.x < self.winfo_width() and 0 <= event.y < self.winfo_height():
            self.invoke()

    def invoke(self):
        self.command()
