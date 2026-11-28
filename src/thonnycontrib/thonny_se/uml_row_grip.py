# SPDX-FileCopyrightText: 2026 Sebastian Ladhoff
# SPDX-License-Identifier: GPL-3.0-only
# See LICENSE in the project root for the full license text.

"""Vertical reordering from any part of the member editor."""
from .i18n import tr
from .display_context import context_for
import tkinter as tk

from thonny.ui_utils import create_tooltip

from .ui_style import SELECT, ui_color
from .uml_edit_panel import paint_panel_badge


class RowGrip(tk.Canvas):
    def __init__(self, parent, row_editor):
        super().__init__(parent, width=35, height=36, background=row_editor.fill,
                         highlightthickness=0, takefocus=False)
        self.row_editor = row_editor
        self.start = None
        self.direction = 0
        self.last_y = None
        self.preview_row = None
        self.drag_tag = "SEUmlRowDrag" + str(id(self))
        for sequence, handler in (("<ButtonPress-1>", self._press),
                                  ("<B1-Motion>", self._motion), ("<ButtonRelease-1>", self._release)):
            self.bind_class(self.drag_tag,sequence,handler)
        self.bindtags((self.drag_tag,*self.bindtags()))
        self.bind("<Configure>", self.draw)
        self.bind("<Escape>", self._escape)
        create_tooltip(self, tr('Drag the editing box up or down'))
        context_for(self).subscribe(self,self._display_changed)
        self._display_changed(context_for(self).state)

    def destroy(self):
        for sequence in ("<ButtonPress-1>","<B1-Motion>","<ButtonRelease-1>"):
            self.unbind_class(self.drag_tag,sequence)
        super().destroy()

    def _display_changed(self,state):
        self.configure(width=round(35*state.ui_scale),height=round(36*state.ui_scale))
        self.draw()

    def bind_surface(self, widget):
        tags = widget.bindtags()
        if self.drag_tag not in tags:
            widget.bindtags((self.drag_tag, *tags))

    def draw(self, event=None):
        paint_panel_badge(self, self.row_editor.section, self.row_editor.diagram.bold, SELECT, color_map=ui_color)

    def _press(self, event):
        self.start = event.x_root, event.y_root
        self.last_y = event.y_root

    def _motion(self, event):
        if self.start is None:
            return
        x, y = self.start
        dx, dy = event.x_root-x, event.y_root-y
        row = self.row_editor
        if not row.reorder_mode:
            if abs(dx) >= 7 and abs(dx) >= abs(dy):
                self.start = None
                return
            if abs(dy) < 7:
                return
            self.previous_focus = self.focus_get()
            self.grab_set()
            self.focus_set()
            row.set_reorder_mode(True)
        if not row.can_reorder():
            self.preview_row = None
            row.diagram._position_member()
            return "break"
        ids = row.visible_row_ids()
        if row.row_id not in ids:
            self.preview_row=None
            row.diagram._position_member()
            return "break"
        index = ids.index(row.row_id)
        movement = event.y_root - self.last_y
        if movement:
            self.direction = -1 if movement < 0 else 1
            self.last_y = event.y_root
        step = row.diagram.row_height * row.diagram.zoom
        distance = int(abs(dy)/step + .5) * (-1 if dy < 0 else 1)
        target = ids[min(len(ids)-1, max(0, index+distance))]
        self.preview_row = target if target != row.row_id else None
        row.diagram._position_member()
        return "break"

    def _release(self, event):
        if not self.row_editor.reorder_mode:
            self.start = None
            return
        self._motion(event)
        target = self.preview_row
        self._reset_drag()
        if target is not None:
            self.row_editor.move_to(target)
        return "break"

    def _reset_drag(self):
        if self.grab_current() is self:
            self.grab_release()
        self.start = self.preview_row = self.last_y = None
        self.direction = 0
        self.row_editor.set_reorder_mode(False)
        self.row_editor.diagram._position_member()
        if self.previous_focus is not None and self.previous_focus.winfo_exists():
            self.previous_focus.focus_set()

    def _escape(self, event):
        if self.row_editor.reorder_mode:
            self._reset_drag()
            return "break"
        return self.row_editor._cancel()
