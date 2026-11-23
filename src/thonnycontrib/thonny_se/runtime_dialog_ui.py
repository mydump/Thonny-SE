# SPDX-FileCopyrightText: 2026 Sebastian Ladhoff
# SPDX-License-Identifier: GPL-3.0-only
"""Small shared content blocks for object creation and method calls."""
import tkinter as tk
from tkinter import font, ttk

from .graphics import rounded, clear_shapes
from .i18n import tr

from .ui_style import (UML_SECTION_FILLS, UML_SECTION_INKS, HINT_FILL,
                       HINT_BORDER, HINT_TEXT, HINT_INK, OBJECT_FILL, OBJECT_EDGE, EDGE, MUTED, DOC_FILL, INK, ERROR, SELECT, OBJECT_FOCUS, OBJECT_ACTIVE_FILL, ui_color)


def rounded_surface(parent, row, fill, edge):
    """Use the existing rounded drawing for a padded native content frame."""
    outer = tk.Canvas(parent, borderwidth=0, highlightthickness=0, takefocus=False, width=1, height=1)
    outer.grid(row=row, column=0, columnspan=3, sticky='ew', pady=(0, 12))
    content = tk.Frame(outer, background=ui_color(fill))
    window = outer.create_window(12, 10, window=content, anchor='nw')
    def draw(event=None):
        background = ttk.Style(parent).lookup('TFrame', 'background')
        outer.configure(background=background)
        content.configure(background=ui_color(fill))
        # The embedded frame follows allocated space, including shrinking
        # again after a wider window; its request is only an initial size hint.
        width = outer.winfo_width()
        if width <= 1:
            width = content.winfo_reqwidth()+24
        height = content.winfo_reqheight()+20
        if int(outer.cget('height')) != height:
            outer.configure(height=height)
        if int(outer.cget('width')) != content.winfo_reqwidth()+24:
            outer.configure(width=content.winfo_reqwidth()+24)
        outer.itemconfigure(window, width=max(1, width-24))
        clear_shapes(outer, 'surface')
        rounded(outer, 1, 1, width-1, height-1, radius=8,
                fill=ui_color(fill), outline=ui_color(edge), group='surface')
        outer.tag_lower('surface')
    outer.bind('<Configure>', draw)
    content.bind('<Configure>', draw)
    outer.bind('<<ThemeChanged>>', draw)
    content.surface = outer
    content.refresh_surface = draw
    outer.after_idle(draw)
    return content


def heading(parent, title, section, letter, *, parameter_spans=None, surface=None):
    fill_color = surface or (OBJECT_FILL if section == 'object' else UML_SECTION_FILLS[section])
    fill = ui_color(fill_color)
    ink = ui_color(INK if section == 'object' else UML_SECTION_INKS[section])
    frame = rounded_surface(parent, 0, fill_color, EDGE if surface else OBJECT_EDGE)
    badge_font = font.Font(root=parent, font='TkDefaultFont')
    badge_font.configure(weight='bold', slant='italic')
    title_font = font.Font(root=parent, font='TkDefaultFont')
    title_font.configure(weight='bold')
    frame.fonts = badge_font, title_font
    if letter:
        tk.Label(frame, text=letter, font=badge_font, foreground=ink,
                 background=fill, padx=4).grid(row=0, column=0, padx=(0, 8), sticky='n')
    parameter_canvases = {}
    signature_canvases = []
    frame.active_parameter = None
    def draw_parameters():
        background = ui_color(fill_color)
        for canvas in signature_canvases:
            canvas.configure(background=background)
            canvas.itemconfigure('parameter-text', fill=ui_color(INK))
        for name, canvas in parameter_canvases.items():
            clear_shapes(canvas, 'parameter-pill')
            if name == frame.active_parameter:
                rounded(canvas, 2, 2, canvas.logical_width-2, canvas.logical_height-2,
                    radius=5, fill=ui_color(OBJECT_ACTIVE_FILL), outline=ui_color(OBJECT_FOCUS), group='parameter-pill')
                canvas.tag_lower('parameter-pill')
            canvas.itemconfigure('parameter-text', fill=ui_color(INK))
    if parameter_spans:
        title_text = tk.Text(frame, font=title_font, background=fill, foreground=ink,
            width=1, height=1, wrap='word', borderwidth=0, highlightthickness=0,
            padx=0, pady=0, takefocus=False, cursor='arrow', exportselection=False)
        layout_width = 540
        frame.multiline_signature = False
        def fragment(text, parameter=None):
            for index, line in enumerate(text.split('\n')):
                if index:
                    title_text.insert('end', '\n')
                if not line:
                    continue
                canvas = tk.Canvas(title_text, background=fill, borderwidth=0,
                                   highlightthickness=0, takefocus=False)
                pad = 4 if parameter else 0
                width = min(max(60, layout_width-(40 if parameter else 0)), title_font.measure(line))
                canvas.create_text(pad, 3, text=line, font=title_font, anchor='nw',
                                   width=width, fill=ink, tags='parameter-text')
                bounds = canvas.bbox('parameter-text')
                canvas.logical_width = width+(10 if parameter else 1)
                canvas.logical_height = bounds[3]-bounds[1]+6
                canvas.configure(width=canvas.logical_width, height=canvas.logical_height)
                title_text.window_create('end', window=canvas, align='center')
                signature_canvases.append(canvas)
                if parameter:
                    parameter_canvases[parameter] = canvas
        ordered = sorted(parameter_spans.items(), key=lambda item: item[1][0])
        def piece_width(text, parameter=False):
            return 0 if not text else min(max(60, layout_width-(40 if parameter else 0)), title_font.measure(text))+(10 if parameter else 1)
        def layout(width):
            nonlocal layout_width
            layout_width = max(100, width-4)
            for canvas in signature_canvases:
                canvas.destroy()
            signature_canvases.clear()
            parameter_canvases.clear()
            title_text.configure(state='normal')
            title_text.delete('1.0', 'end')
            frame.multiline_signature = title_font.measure(title)+10*len(parameter_spans) > layout_width
            cursor = 0
            for index, (name, (start, end)) in enumerate(ordered):
                gap = title[cursor:start]
                if frame.multiline_signature:
                    if index == 0:
                        opening = gap.rfind('(')
                        gap = gap[:opening+1]+'\n    '+gap[opening+1:]
                    gap = gap.replace(', ', ',\n    ')
                fragment(gap)
                fragment(title[start:end], name)
                cursor = end
            tail = title[cursor:]
            if frame.multiline_signature:
                tail = tail.replace(', ', ',\n    ').replace(')', '\n)', 1)
            fragment(tail)
            title_text.configure(state='disabled')
            draw_parameters()
        layout(540)
        title_holder = tk.Frame(frame, background=fill, width=1, height=1)
        title_holder.grid(row=0, column=1, sticky='ew')
        title_text.place(in_=title_holder, x=0, y=0, relwidth=1, relheight=1)
        title_text.lift()
        frame.columnconfigure(1, weight=1, minsize=min(540, title_font.measure(title)+10*len(parameter_spans)))
        last_width = None
        def fit(event=None):
            nonlocal last_width
            width = title_text.winfo_width()
            if width >= 100 and width != last_width:
                last_width = width
                layout(width)
            pixels = int(title_text.tk.call(title_text, 'count', '-update', '-ypixels', '1.0', 'end'))
            pixels = max(pixels, max(canvas.logical_height for canvas in parameter_canvases.values()))
            if int(title_holder.cget('height')) != pixels:
                title_holder.configure(height=pixels)
        title_text.bind('<Configure>', fit)
        title_text.after_idle(fit)
        frame.title_text = title_text
        def highlight_parameter(name):
            frame.active_parameter = name
            draw_parameters()
    else:
        title_label = tk.Label(frame, text=title, font=title_font, background=fill,
                 foreground=ink, wraplength=540, justify='left', anchor='w')
        title_label.grid(row=0, column=1, sticky='ew')
        frame.columnconfigure(1, weight=1)
        title_label.bind('<Configure>', lambda event: title_label.configure(wraplength=max(60,event.width)))
        def highlight_parameter(name):
            pass
    frame.parameter_canvases = parameter_canvases
    frame.highlight_parameter = highlight_parameter
    def refresh(event=None):
        background = ui_color(fill_color)
        foreground = ui_color(INK if section == 'object' else UML_SECTION_INKS[section])
        frame.configure(background=background)
        frame.refresh_surface()
        for label in frame.winfo_children():
            if isinstance(label, tk.Frame):
                label.configure(background=background)
            else:
                label.configure(background=background, foreground=foreground)
        draw_parameters()
    frame.bind('<<ThemeChanged>>', refresh)
    return frame


def documentation(parent, text, row, *, truncated=False):
    """A bounded documentation extract, visibly attributed to the Python code."""
    original_length = len(text)
    if truncated:
        text += '\n\n'+tr('Documentation shortened. The complete text is in the Python code.')
    background = ui_color(DOC_FILL)
    frame = tk.Frame(parent, background=background, padx=12, pady=10,
                     highlightthickness=1, highlightbackground=ui_color(OBJECT_EDGE))
    frame.grid(row=row, column=0, columnspan=3, sticky='nsew', pady=(0, 12))
    caption_font = font.Font(root=parent, font='TkDefaultFont')
    caption_font.configure(slant='italic')
    frame.caption_font = caption_font
    caption = tk.Label(frame, text=tr('Documentation from the code'), font=caption_font,
        background=background, foreground=ui_color(MUTED), anchor='w')
    caption.grid(row=0, column=0, columnspan=2, sticky='w', pady=(0, 6))
    face = font.nametofont('TkDefaultFont', root=parent)
    lines = sum(max(1, (face.measure(line)+519)//520) for line in text.splitlines())
    if lines <= 5:
        help_text = tk.Label(frame, text=text, wraplength=520, justify='left',
            background=background, foreground=ui_color(INK), anchor='w')
        help_text.grid(row=1, column=0, sticky='ew')
        frame.bind('<Configure>', lambda event: help_text.configure(wraplength=max(60,event.width-26)))
    else:
        help_text = tk.Text(frame, height=5, width=60, wrap='word', font='TkDefaultFont',
            relief='flat', borderwidth=0, highlightthickness=0, padx=0, pady=0,
            background=background, foreground=ui_color(INK))
        help_text.insert('1.0', text)
        if truncated:
            help_text.tag_add('doc-note', f'1.0+{original_length+2}c', 'end-1c')
            help_text.tag_configure('doc-note', foreground=ui_color(MUTED), font=caption_font)
        help_text.configure(state='disabled')
        help_text.grid(row=1, column=0, sticky='nsew')
        frame.rowconfigure(1, weight=1)
        parent.rowconfigure(row, weight=1)
        scroll = ttk.Scrollbar(frame, orient='vertical', command=help_text.yview)
        scroll.grid(row=1, column=1, sticky='ns', padx=(8, 0))
        def scrolled(first, last):
            scroll.set(first, last)
            if float(first) <= 0 and float(last) >= 1:
                scroll.grid_remove()
            else:
                scroll.grid()
        help_text.configure(yscrollcommand=scrolled)
    def refresh(event=None):
        frame.configure(background=ui_color(DOC_FILL), highlightbackground=ui_color(OBJECT_EDGE))
        caption.configure(background=ui_color(DOC_FILL), foreground=ui_color(MUTED))
        help_text.configure(background=ui_color(DOC_FILL), foreground=ui_color(INK))
        if truncated and isinstance(help_text, tk.Text):
            help_text.tag_configure('doc-note', foreground=ui_color(MUTED))
    frame.bind('<<ThemeChanged>>', refresh)
    frame.columnconfigure(0, weight=1)
    frame.help_text = help_text
    frame.truncated = truncated
    return frame


class FeedbackLabel(tk.Label):
    """A native label in a status surface, shown only when it has content."""
    def configure(self, cnf=None, **kwargs):
        result = super().configure(cnf, **kwargs)
        if 'text' in kwargs:
            if kwargs['text']:
                self.panel.grid()
            else:
                self.panel.grid_remove()
        return result

    config = configure


def feedback(parent, row, *, error=False):
    fill = '#fff0ee' if error else OBJECT_FILL
    edge = ERROR if error else OBJECT_EDGE
    panel = tk.Frame(parent, background=ui_color(fill), highlightthickness=1,
                     highlightbackground=ui_color(edge), padx=12, pady=10)
    panel.grid(row=row, column=0, columnspan=3, sticky='ew', pady=(8, 0))
    label = FeedbackLabel(panel, background=ui_color(fill), foreground=ui_color(INK),
                          wraplength=500, justify='left', anchor='w')
    label.panel = panel
    label.grid(row=0, column=0, sticky='w')
    def refresh(event=None):
        panel.configure(background=ui_color(fill), highlightbackground=ui_color(edge))
        label.configure(background=ui_color(fill), foreground=ui_color(INK))
    label.refresh_colors = refresh
    panel.bind('<<ThemeChanged>>', refresh)
    panel.columnconfigure(0, weight=1)
    panel.grid_remove()
    return label


class ResultPanel(tk.Frame):
    """A fixed-height output area: arrow always visible, long values scroll."""
    def __init__(self, parent, row):
        super().__init__(parent, padx=12, pady=10, highlightthickness=1)
        self.grid(row=row, column=0, columnspan=3, sticky='ew', pady=(8, 0))
        self.failed = False
        self.text = ''
        self._geometry_job = None
        self._reserved_geometry = None
        self.arrow = tk.Label(self, text='→', font='TkDefaultFont', padx=0, pady=0,
                              borderwidth=0, highlightthickness=0, anchor='nw')
        self.arrow.grid(row=0, column=0, sticky='nw', padx=(0, 8))
        self.body = tk.Text(self, height=3, width=60, font='TkDefaultFont', wrap='word',
            relief='flat', borderwidth=0, highlightthickness=0, padx=0, pady=0, state='disabled')
        self.body.grid(row=0, column=1, sticky='nsew')
        self.scroll = ttk.Scrollbar(self, orient='vertical', command=self.body.yview)
        self.scroll.grid(row=0, column=2, sticky='ns', padx=(8, 0))
        self.scroll.grid_remove()
        self._scroll_visible = False
        self.columnconfigure(2, minsize=self.scroll.winfo_reqwidth()+8)
        self.body.configure(yscrollcommand=self._scrolled)
        self.columnconfigure(1, weight=1)
        self.bind('<<ThemeChanged>>', self.refresh_colors)
        self.scroll.bind('<<ThemeChanged>>', self._queue_geometry, add='+')
        self.scroll.bind('<Configure>', self._queue_geometry, add='+')
        self.body.bind('<Configure>', self._queue_geometry, add='+')
        self.refresh_colors()

    def _scrolled(self, first, last):
        self.scroll.set(first, last)
        needed = float(first) > 0 or float(last) < 1
        if needed != self._scroll_visible:
            self._scroll_visible = needed
            if needed:
                self.scroll.grid()
            else:
                self.scroll.grid_remove()

    def set(self, text='', *, failed=False):
        self.text, self.failed = text, failed
        self.body.configure(state='normal')
        self.body.delete('1.0', 'end')
        self.body.insert('1.0', text)
        self.body.configure(state='disabled')
        self.body.yview_moveto(0)
        self.after_idle(self._sync_scroll)
        self.refresh_colors()

    def _sync_scroll(self):
        self.body.tk.call(self.body, 'count', '-update', '-ypixels', '1.0', 'end')
        self._scrolled(*self.body.yview())

    def refresh_colors(self, event=None):
        fill = ui_color('#fff0ee' if self.failed else OBJECT_FILL if self.text else '#f1f2f3')
        edge = ui_color(ERROR if self.failed else OBJECT_EDGE if self.text else EDGE)
        self._reserve_geometry()
        # ttk can publish its new requested size after the panel's theme event.
        # Read it again after native theme/layout processing has settled.
        self._queue_geometry()
        ink = ui_color(INK if self.text else MUTED)
        self.configure(background=fill, highlightbackground=edge)
        self.arrow.configure(background=fill, foreground=ui_color(ERROR) if self.failed else ink)
        self.body.configure(background=fill, foreground=ink)

    def _reserve_geometry(self):
        geometry = (self.scroll.winfo_reqwidth()+8,
                    max(self.body.winfo_reqheight(), self.scroll.winfo_reqheight()))
        if geometry != self._reserved_geometry:
            self._reserved_geometry = geometry
            self.columnconfigure(2, minsize=geometry[0])
            self.rowconfigure(0, minsize=geometry[1])

    def _queue_geometry(self, event=None):
        if self._geometry_job is None:
            self._geometry_job = self.after_idle(self._finish_geometry)

    def _finish_geometry(self):
        self._geometry_job = None
        self._reserve_geometry()

    def destroy(self):
        if self._geometry_job is not None:
            self.after_cancel(self._geometry_job)
            self._geometry_job = None
        super().destroy()


def warning(parent, text, row):
    frame = tk.Frame(parent, background=ui_color(HINT_FILL),
                     highlightbackground=ui_color(HINT_BORDER), highlightthickness=1,
                     padx=12, pady=10)
    frame.grid(row=row, column=0, columnspan=3, sticky='ew', pady=(12, 0))
    badge_font = font.Font(root=parent, font='TkDefaultFont')
    badge_font.configure(weight='bold')
    frame.badge_font = badge_font
    tk.Label(frame, text='!', font=badge_font, background=ui_color(HINT_FILL),
             foreground=ui_color(HINT_INK)).grid(row=0, column=0, sticky='n', padx=(0, 10))
    tk.Label(frame, text=text, wraplength=490, justify='left',
             background=ui_color(HINT_FILL), foreground=ui_color(HINT_TEXT)).grid(row=0, column=1, sticky='w')
    frame.columnconfigure(1, weight=1)
    def refresh(event=None):
        frame.configure(background=ui_color(HINT_FILL), highlightbackground=ui_color(HINT_BORDER))
        for label in frame.winfo_children():
            if isinstance(label, tk.Label):
                label.configure(background=ui_color(HINT_FILL),
                    foreground=ui_color(HINT_INK if label.cget('text') == '!' else HINT_TEXT))
    frame.bind('<<ThemeChanged>>', refresh)
    return frame


def follow_theme(dialog, error, output=None):
    # The native outer Frame is not a ttk widget. Keep it in step with Thonny;
    # use the default live ttk frame style for these runtime dialog containers.
    def refresh(event=None):
        if event is not None and event.widget is not dialog:
            return
        background = ttk.Style(dialog).lookup('TFrame', 'background')
        dialog.configure(background=background)
        for child in dialog.winfo_children():
            if type(child) is tk.Frame:
                child.configure(background=background)
                for content in child.winfo_children():
                    if isinstance(content, ttk.Frame):
                        content.configure(style='TFrame')
            elif isinstance(child, ttk.Frame):
                child.configure(style='TFrame')
        if hasattr(error, 'refresh_colors'):
            error.refresh_colors()
        else:
            error.configure(foreground=ui_color(ERROR))
        if output is not None:
            if hasattr(output, 'refresh_colors'):
                output.refresh_colors()
            else:
                output.configure(foreground=ui_color(SELECT))
    dialog.bind('<<ThemeChanged>>', refresh, add='+')
    dialog.after_idle(refresh)
