# SPDX-FileCopyrightText: 2026 Sebastian Ladhoff
# SPDX-License-Identifier: GPL-3.0-only
# See LICENSE in the project root for the full license text.

"""A passive info badge pinned to the visible portion of a diagram canvas."""
from .display_context import context_for
from .visual_metrics import Typography
from .graphics import clear_shapes, rounded, badge

from .diagram_preferences import enabled
from .ui_style import HINT_BADGE, HINT_BORDER, HINT_FILL, HINT_INK, HINT_TEXT


class DiagramHint:
    TAG = "diagram-info"

    def __init__(self, canvas, hide_option=None, *, color=lambda value: value):
        self.canvas = canvas
        self.hide_option = hide_option
        self.color = color
        self.text = ""
        self.image = None
        self.typography = Typography(canvas)
        self.font = self.typography["caption"]
        context_for(canvas).subscribe(canvas,self._display_changed)

    def _display_changed(self, state):
        self.typography.refresh()
        self.draw()

    def show(self, text="", image=None):
        self.image = image
        self.text = text
        self.draw()

    def draw(self):
        canvas = self.canvas
        clear_shapes(canvas,self.TAG)
        u = self.typography.units
        width, height = canvas.winfo_width(), canvas.winfo_height()
        if not self.text or width < u(82) or height < u(42):
            return
        if self.hide_option is not None and enabled(self.hide_option):
            return
        center_x = canvas.canvasx(width / 2)
        y = canvas.canvasy(height / 2)
        text = canvas.create_text(center_x+(0 if self.image else u(14)), y, text=self.text, font=self.font, fill=self.color(HINT_TEXT),
                                  width=width-u(110 if self.image else 82), justify="center",
                                  anchor="center", tags=self.TAG)
        left, top, right, bottom = canvas.bbox(text)
        x0, y0, x1, y1 = left-u(42), top-u(10), right+(max(u(42), u(22)+self.image.width()/2+u(10)) if self.image else u(14)), bottom+u(10)
        if self.image is not None:
            canvas.create_image(right+u(22),y,image=self.image,tags=(self.TAG,"diagram-info-run-icon"))
        radius = u(11)
        background = rounded(canvas,x0,y0,x1,y1,radius=radius,
                             fill=self.color(HINT_FILL),outline=self.color(HINT_BORDER),group=self.TAG)
        canvas.tag_lower(background, text)
        icon_x, icon_y = left-u(23), (top+bottom)/2
        badge(canvas,icon_x,icon_y,radius=u(11),fill=self.color(HINT_BADGE),
              outline=self.color(HINT_INK),group=self.TAG,exclamation=True)
