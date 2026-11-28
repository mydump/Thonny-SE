# SPDX-FileCopyrightText: 2026 Sebastian Ladhoff
# SPDX-License-Identifier: GPL-3.0-only
# See LICENSE in the project root for the full license text.

"""A passive info badge pinned to the visible portion of a diagram canvas."""
import re
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
        if "{F5}" in self.text and self.image is not None:
            self._draw_run_hint(width, height)
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

    def _draw_run_hint(self, width, height):
        """Lay out the key and Run icon as atomic inline items, including wraps."""
        canvas, u = self.canvas, self.typography.units
        limit = max(u(40), width-u(110))
        key_width = self.font.measure('F5')+u(14)
        line_height = max(self.font.metrics('linespace')+u(12), self.image.height()+u(8))
        rows, row, used = [], [], 0
        for token in re.findall(r'\{F5\}|\{run\}|\n|[^\S\n]+|[^\s{}]+', self.text):
            if token == '\n':
                rows.append((row, used));row, used = [], 0
                continue
            size = key_width if token == '{F5}' else self.image.width()+u(6) if token == '{run}' else self.font.measure(token)
            if row and used+size > limit and not token.isspace():
                rows.append((row, used));row, used = [], 0
            if not row and token.isspace():
                continue
            row.append((token, size));used += size
        if row:rows.append((row, used))
        cx = canvas.canvasx(width/2)+u(12)
        cy = canvas.canvasy(height/2)
        total = len(rows)*line_height
        widest = max(size for _,size in rows)
        left, right = cx-widest/2, cx+widest/2
        top, bottom = cy-total/2, cy+total/2
        rounded(canvas,left-u(42),top-u(5),right+u(14),bottom+u(5),radius=u(11),
                fill=self.color(HINT_FILL),outline=self.color(HINT_BORDER),group=self.TAG)
        for index,(items,row_width) in enumerate(rows):
            x, y = left, top+(index+.5)*line_height
            for token,size in items:
                if token == '{F5}':
                    key_height = self.font.metrics('linespace')+u(6)
                    rounded(canvas,x,y-key_height/2,x+size,y+key_height/2,radius=u(3),
                            fill=self.color(HINT_BADGE),outline=self.color(HINT_INK),group=self.TAG)
                    canvas.create_text(x+size/2,y,text='F5',font=self.font,fill=self.color(HINT_TEXT),
                                       tags=(self.TAG,'diagram-info-keycap'))
                elif token == '{run}':
                    canvas.create_image(x+size/2,y,image=self.image,tags=(self.TAG,'diagram-info-run-icon'))
                elif not token.isspace():
                    canvas.create_text(x,y,anchor='w',text=token,font=self.font,fill=self.color(HINT_TEXT),tags=self.TAG)
                x += size
        badge(canvas,left-u(23),cy,radius=u(11),fill=self.color(HINT_BADGE),
              outline=self.color(HINT_INK),group=self.TAG,exclamation=True)
