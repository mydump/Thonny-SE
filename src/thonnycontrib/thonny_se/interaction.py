# SPDX-FileCopyrightText: 2026 Sebastian Ladhoff
# SPDX-License-Identifier: GPL-3.0-only
# See LICENSE in the project root for the full license text.

"""Lokale Mausgesten: Palette ziehen, Teilbäume verschieben, Shift-Bereich."""
import tkinter as tk
from .drag_preview import DragPreview
from .model import Selection
from .ui_style import SELECT


class DiagramInteraction:
    def __init__(self, editor):
        self.editor = editor
        self.canvas = editor.diagram.canvas
        self.gesture = None
        self.preview = None
        self._scroll_job = None
        self.canvas.bind("<Button-1>", self.press_diagram)
        self.canvas.bind("<B1-Motion>", self.motion)
        self.canvas.bind("<ButtonRelease-1>", self.release)
        self.canvas.bind("<Escape>", self.cancel)
        self.canvas.bind("<Unmap>", self.cancel, add=True)
        self.canvas.bind("<Destroy>", self.cancel, add=True)
        for kind, button in editor.palette_buttons.items():
            button.bind("<Button-1>", lambda event, kind=kind: self.press_palette(event, kind))
            button.bind("<B1-Motion>", self.motion)
            button.bind("<ButtonRelease-1>", self.release)
            button.bind("<Escape>", self.cancel)

    def _begin(self, event, kind=None, pending=None):
        self.cancel()
        self.gesture = dict(x=event.x_root, y=event.y_root, last_x=event.x_root,
                            last_y=event.y_root, kind=kind, widget=event.widget,
                            dragging=False, pending=pending)

    def press_palette(self, event, kind):
        event.widget.focus_set()
        self._begin(event, kind=kind)
        return "break"

    def press_diagram(self, event):
        self.editor.diagram.try_tip.dismiss()
        self.canvas.focus_set()
        selection = self.editor.diagram.region_at(self.canvas.canvasx(event.x), self.canvas.canvasy(event.y))
        if selection is None:
            self.cancel()
            return "break"
        current = self.editor.selection
        last = current.end_index if current.end_index is not None else current.index
        within = (selection.path == current.path and selection.index is not None
                  and current.index is not None and current.index <= selection.index <= last)
        pending = None
        if event.state & 1:
            self.editor.extend_selection(selection)
        elif within and current.end_index is not None:
            pending = selection
        else:
            self.editor.select_region(selection)
        if self.editor.selection.index is not None:
            self._begin(event, pending=pending)
        else:
            self.cancel()
        return "break"

    def target_at(self, root_x, root_y):
        x, y = root_x-self.canvas.winfo_rootx(), root_y-self.canvas.winfo_rooty()
        if not 0 <= x < self.canvas.winfo_width() or not 0 <= y < self.canvas.winfo_height():
            return None
        cx, cy = self.canvas.canvasx(x), self.canvas.canvasy(y)
        target = self.editor.diagram.region_at(cx, cy)
        if target is None:
            return None
        region = next((r for r in reversed(self.editor.diagram.regions) if r.selection == target), None)
        # Die schmale obere Kante ermöglicht Einfügen vor dem ersten Element.
        if target.index is not None and region and cy < region.bounds[1]+6*self.editor.diagram.zoom:
            target = Selection(target.path, target.index-1) if target.index else Selection(target.path, at_start=True)
        if self.gesture and self.gesture["kind"] is None:
            source = self.editor.selection
            last = source.end_index if source.end_index is not None else source.index
            if target.path[:len(source.path)] == source.path and len(target.path) > len(source.path):
                if source.index <= target.path[len(source.path)] <= last:
                    return None
            if target.path == source.path and target.index is not None and source.index <= target.index <= last:
                return None
        return target

    def motion(self, event):
        if self.gesture is None:
            return "break"
        gesture = self.gesture
        gesture["last_x"], gesture["last_y"] = event.x_root, event.y_root
        if abs(event.x_root-gesture["x"])+abs(event.y_root-gesture["y"]) < 6 and not gesture["dragging"]:
            return "break"
        gesture["dragging"] = True
        if gesture['kind'] is not None:
            if self.preview is None:
                self.preview = DragPreview(gesture['widget'],gesture['kind'])
            self.preview.move(event.x_root,event.y_root)
        self._show_target()
        if self._scroll_job is None:
            self._scroll_job = self.canvas.after(80, self._autoscroll)
        return "break"

    def _show_target(self):
        self.canvas.delete("drop-target")
        target = self.target_at(self.gesture["last_x"], self.gesture["last_y"])
        if target is None:
            return
        lookup = Selection(target.path) if target.at_start else target
        region = next((r for r in reversed(self.editor.diagram.regions) if r.selection == lookup), None)
        if region:
            x1, y1, x2, y2 = region.bounds
            y = y1+3 if target.at_start else y2-3
            self.canvas.create_line(x1+4, y, x2-4, y, fill=SELECT, width=4, tags="drop-target")
            self.canvas.create_oval(x1, y-4, x1+8, y+4, fill=SELECT, outline=SELECT, tags="drop-target")

    def _autoscroll(self):
        self._scroll_job = None
        if not self.gesture or not self.gesture["dragging"]:
            return
        x = self.gesture["last_x"]-self.canvas.winfo_rootx()
        y = self.gesture["last_y"]-self.canvas.winfo_rooty()
        if 0 <= x < self.canvas.winfo_width() and 0 <= y < self.canvas.winfo_height():
            if y < 24:
                self.canvas.yview_scroll(-20, "units")
            elif y > self.canvas.winfo_height()-24:
                self.canvas.yview_scroll(20, "units")
            self._show_target()
        self._scroll_job = self.canvas.after(80, self._autoscroll)

    def release(self, event):
        gesture = self.gesture
        if gesture is None:
            return "break"
        target = self.target_at(event.x_root, event.y_root) if gesture["dragging"] else None
        self.cancel()
        if gesture["dragging"]:
            if target is not None:
                self.editor.drop_blocks(target, gesture["kind"])
                self.canvas.focus_set()
        elif gesture["kind"] is not None:
            widget = gesture["widget"]
            x, y = event.x_root-widget.winfo_rootx(), event.y_root-widget.winfo_rooty()
            if 0 <= x < widget.winfo_width() and 0 <= y < widget.winfo_height():
                widget.invoke()
        elif gesture["pending"] is not None:
            self.editor.select_region(gesture["pending"])
        return "break"

    def cancel(self, event=None):
        if self._scroll_job is not None:
            try:
                self.canvas.after_cancel(self._scroll_job)
            except tk.TclError:
                pass
            self._scroll_job = None
        self.gesture = None
        if self.preview is not None:
            self.preview.destroy()
            self.preview = None
        if self.canvas.winfo_exists():
            self.canvas.delete("drop-target")
        return "break"
