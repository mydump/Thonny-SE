# SPDX-FileCopyrightText: 2026 Sebastian Ladhoff
# SPDX-License-Identifier: GPL-3.0-only
# See LICENSE in the project root for the full license text.

"""Scalable filled glyphs for the diagram's editing gestures."""

from tkinter import font as tkfont
from .graphics import badge


def direction_arrow(canvas, x, y, direction, size, color, tags=()):
    points = ((0, -0.5), (-0.5, 0.04), (-0.2, 0.04), (-0.2, 0.5),
              (0.2, 0.5), (0.2, 0.04), (0.5, 0.04))
    return canvas.create_polygon(
        *(coordinate for dx, dy in points for coordinate in (x+dx*size, y-dy*direction*size)),
        fill=color, outline="", tags=tags,
    )



BADGE_LETTERS = {"attributes": "A", "methods": "M", "name": "C"}


def letter_badge(canvas, x, y, section, color, fill, font, *, radius=11, tags=()):
    if hasattr(canvas, '_se_smooth_images'):
        canvas._se_smooth_images.clear()
    badge(canvas,x,y,radius=radius,fill=fill,outline=color,group=tags[0] if tags else 'letter-badge')
    if section in BADGE_LETTERS:
        # This is a fixed UI badge, not diagram text. Its letter must fit the
        # circle even when the edited row uses a large zoom/font size.
        actual = tkfont.nametofont('TkDefaultFont',root=canvas).actual()
        spec = dict(family=actual['family'],weight='bold',slant='italic',
                    size=-max(1,round(radius*1.2)))
        key=(section,spec['family'],radius)
        if not hasattr(canvas,'_badge_font'):
            canvas._badge_font=tkfont.Font(root=canvas,**spec)
        if getattr(canvas,'_badge_font_key',None)!=key:
            canvas._badge_font.configure(**spec)
            while (canvas._badge_font.metrics('linespace')>radius*1.6
                   or canvas._badge_font.measure(BADGE_LETTERS[section])>radius*1.4) and spec['size']<-1:
                spec['size']+=1
                canvas._badge_font.configure(size=spec['size'])
            canvas._badge_font_key=key
            canvas._badge_font_spec=spec
        font=canvas._badge_font
    canvas.create_text(x,y,text=BADGE_LETTERS[section],font=font,fill=color,tags=tags)
