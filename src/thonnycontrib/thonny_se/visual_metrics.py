# SPDX-FileCopyrightText: 2026 Sebastian Ladhoff
# SPDX-License-Identifier: GPL-3.0-only
# See LICENSE in the project root for the full license text.

"""Native, named typography roles and font-derived UI distances."""
from tkinter import font
from collections import OrderedDict
from .display_context import context_for

ROLES = {'body':{},'heading':{'weight':'bold'},'abstract':{'weight':'bold','slant':'italic'},
         'abstract_method':{'slant':'italic'},'caption':{},'object_heading':{'weight':'bold','underline':True}}


def scaled_size(size, zoom):
    result = max(1,round(abs(int(size))*zoom))
    return -result if size < 0 else result


class Typography:
    """Keep font objects stable so open entries inherit updates without rebuilds."""
    def __init__(self, widget, *, zoom=1.0):
        self.widget = widget
        self.zoom = zoom
        self.fonts = {role:font.nametofont('TkDefaultFont',root=widget).copy() for role in ROLES}
        self._applied = {}
        self._zoom_fonts = OrderedDict()
        self._selected_zoom = False
        self._pixel_size = None
        self.refresh()

    def refresh(self, zoom=None):
        if zoom is not None:self.zoom=zoom
        if self._selected_zoom:
            self.select_zoom(self.zoom, pixel_size=self._pixel_size)
            return
        base = font.nametofont('TkDefaultFont',root=self.widget).actual()
        for role,target in self.fonts.items():
            values = {**base,**ROLES[role]}
            values['size'] = scaled_size(base['size'],self.zoom)
            if self._applied.get(role) != values:
                target.configure(**values)
                self._applied[role] = values

    def select_zoom(self, zoom, *, pixel_size=None):
        """Use immutable variants: configuring a live Tk named font broadcasts
        geometry changes throughout the host, even during a small slider move.
        """
        self._selected_zoom=True
        base=font.nametofont('TkDefaultFont',root=self.widget).actual()
        self._pixel_size = pixel_size
        base['size'] = -max(1, round(pixel_size)) if pixel_size is not None else scaled_size(base['size'],zoom)
        key=tuple(sorted(base.items()))
        if key not in self._zoom_fonts:
            self._zoom_fonts[key]={role:font.Font(root=self.widget,**{**base,**style})
                                   for role,style in ROLES.items()}
        self._zoom_fonts.move_to_end(key)
        self.zoom=zoom
        self.fonts=self._zoom_fonts[key]
        if len(self._zoom_fonts)>32:self._zoom_fonts.popitem(last=False)

    def __getitem__(self, role):return self.fonts[role]

    def units(self, value):
        return max(1,round(value*context_for(self.widget).state.ui_scale))

    def line_height(self, role='body', *, padding=12, minimum=30):
        return max(self.units(minimum),self.fonts[role].metrics('linespace')+self.units(padding))


def preserve_scroll(canvas, draw):
    """Display-only redraw; leave focus, entry widgets and model history alone."""
    x,y = canvas.xview(),canvas.yview()
    draw()
    if x:canvas.xview_moveto(x[0])
    if y:canvas.yview_moveto(y[0])
