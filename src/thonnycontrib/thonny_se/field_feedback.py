# SPDX-FileCopyrightText: 2026 Sebastian Ladhoff
# SPDX-License-Identifier: GPL-3.0-only
# See LICENSE in the project root for the full license text.

"""Visible input borders and contextual validation feedback."""
from thonny.ui_utils import ToolTip, get_style_configuration

from .ui_style import ERROR, FIELD_BORDER as BORDER, SELECT


class FieldFeedback:
    def __init__(self, widget, label, *, border=None, color=lambda value: value):
        self.widget = widget
        self.label = label
        self.error = ""
        self.color = color
        self.border = border if border is not None else widget
        self.border.configure(highlightthickness=1, highlightbackground=color(BORDER), highlightcolor=color(SELECT))
        if border is not None:
            widget.bind("<FocusIn>", lambda event: self._paint_border(focused=True), add=True)
            widget.bind("<FocusOut>", lambda event: self._paint_border(focused=False), add=True)
        options = dict(background="#ffffe0", foreground="#000000", relief="solid",
                       borderwidth=1, padx=1, pady=0)
        options.update(get_style_configuration("Tooltip"))
        self.tooltip = ToolTip(widget, options)
        self.toplevel = widget.winfo_toplevel()
        widget.bind("<Enter>", self._show_tip, add=True)
        widget.bind("<Leave>", self._hide_tip, add=True)
        widget.bind("<Destroy>", self._hide_tip, add=True)

    def _show_tip(self, event):
        # Tk Text returns None when the insertion point is outside its viewport.
        if self.widget.bbox("insert") is not None:
            self.tooltip.showtip(self.error or self.label)

    def _hide_tip(self, event=None):
        self.tooltip.hidetip()
        if self.tooltip.focus_out_bind_ref:
            self.toplevel.unbind("<FocusOut>", self.tooltip.focus_out_bind_ref)
            self.tooltip.focus_out_bind_ref = None

    def set_error(self, message=""):
        if self.error == message:
            return
        self._hide_tip()
        self.error = message
        self._paint_border(focused=self.border is not self.widget and self.widget.focus_get() is self.widget)

    def _paint_border(self, *, focused):
        self.border.configure(highlightbackground=self.color(ERROR if self.error else SELECT if focused else BORDER),
                              highlightcolor=self.color(ERROR if self.error else SELECT))
