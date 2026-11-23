# SPDX-FileCopyrightText: 2026 Sebastian Ladhoff
# SPDX-License-Identifier: GPL-3.0-only
# See LICENSE in the project root for the full license text.

"""Shared parameter fields for constructors and method calls."""
import ast
import tkinter as tk
from tkinter import ttk, font

from .i18n import tr
from .ui_style import OBJECT_FOCUS, MUTED, ERROR, ARGUMENT_MISSING, ui_color
from .diagram_preferences import enabled, OBJECT_CHECK_ARGUMENTS
from thonnycontrib.backend.thonny_se_argument_types import field_states


def matching_objects(annotation, objects):
    """Filter suggestions only; never evaluate annotations or reject expressions."""
    if not annotation:
        return objects
    try:
        node = ast.parse(annotation, mode='eval').body
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            node = ast.parse(node.value, mode='eval').body
    except SyntaxError:
        return objects
    def names(node):
        if isinstance(node, ast.Name):
            return {node.id}
        if isinstance(node, ast.Attribute):
            return {node.attr}
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
            return names(node.left) | names(node.right)
        if isinstance(node, ast.Subscript):
            base = names(node.value)
            if base & {'Optional', 'Union', 'Annotated'}:
                parts = node.slice.elts if isinstance(node.slice, ast.Tuple) else [node.slice]
                if 'Annotated' in base:
                    parts = parts[:1]
                return set().union(*(names(part) for part in parts))
            return base
        return set()
    types = names(node)
    if not types or types & {'Any', 'object'}:
        return objects
    return [obj for obj in objects if types.intersection(obj.get('class_names', [obj['class_name']]))]


def default_placeholder(field, variable, default):
    """Display a default without ever putting it into the argument variable."""
    label = tk.Label(field, text=default, anchor='w', padx=0, pady=0, borderwidth=0, takefocus=False)
    def update(*args):
        if variable.get():
            label.place_forget()
            return
        style = ttk.Style(field)
        face = style.lookup(field.cget('style'), 'font') or 'TkDefaultFont'
        background = style.lookup(field.cget('style'), 'fieldbackground') or ui_color('#ffffff')
        label.configure(font=face, foreground=ui_color(MUTED), background=background)
        bounds = field.bbox(0)
        # Some native ttk themes return text-local bbox coordinates even for
        # non-empty entries. Never let a placeholder undercut the entry padding.
        padding = style.lookup(field.cget('style'), 'padding') or 4
        inset = field.winfo_pixels(field.tk.splitlist(padding)[0])+1
        left = max(inset, bounds[0]+1 if bounds else inset)
        available = max(0, field.winfo_width()-left-(24 if isinstance(field, ttk.Combobox) else 6))
        width = min(font.Font(root=field, font=face).measure(default), available)
        label.place(x=left, rely=.5, anchor='w', width=width)
    def focus(event):
        field.focus_set()
        field.icursor(0)
        return 'break'
    label.bind('<Button-1>', focus)
    variable.trace_add('write', update)
    field.bind('<Configure>', update, add='+')
    field.bind('<<ThemeChanged>>', update, add='+')
    field.after_idle(update)
    return label


class ArgumentFields:
    def __init__(self, master, parameters, objects=(), *, start=0, on_focus=None, context=None):
        self.master, self.on_focus = master, on_focus
        self.context, self.on_change = context or {}, None
        self.states, self.missing = {}, set()
        self.active_name = None
        self.frames, self.invalid = {}, set()
        self.parameters = parameters
        self.values, self.entries, self.placeholders = {}, {}, {}
        if not parameters:
            self.next_row = start
            return
        for row, parameter in enumerate(parameters, start=start):
            label = parameter['name']
            if parameter['kind'] == 'VAR_POSITIONAL':
                label = '*' + label
            elif parameter['kind'] == 'VAR_KEYWORD':
                label = '**' + label
            if parameter.get('annotation'):
                label += ': ' + parameter['annotation']
            if parameter['required']:
                label += ' *'
            ttk.Label(master, text=label, wraplength=220).grid(row=row, column=0, sticky='w', padx=(0, 12), pady=4)
            candidates = matching_objects(parameter.get('annotation', ''), objects)
            names = [name for obj in candidates for name in obj['names']]
            variable = tk.StringVar(master)
            variable.trace_add('write', lambda *args: self.revalidate())
            self.values[parameter['name']] = variable
            border = tk.Frame(master, borderwidth=0, highlightthickness=2)
            border.grid(row=row, column=1, sticky='ew', pady=4)
            border.columnconfigure(0, weight=1)
            self.frames[parameter['name']] = border
            if names and parameter['kind'] not in ('VAR_POSITIONAL', 'VAR_KEYWORD'):
                field = ttk.Combobox(border, textvariable=variable, values=names, width=30, style='SE.TCombobox')
            else:
                field = ttk.Entry(border, textvariable=variable, width=30, style='SE.TEntry')
            field.grid(row=0, column=0, sticky='ew')
            field.bind('<FocusIn>', lambda event, name=parameter['name']: self.focus(name), add='+')
            field.bind('<FocusOut>', lambda event: self.master.after_idle(self.sync_focus), add='+')
            border.bind('<<ThemeChanged>>', lambda event: self.refresh_borders())
            self.entries[parameter['name']] = field
            if parameter['default']:
                self.placeholders[parameter['name']] = default_placeholder(field, variable, parameter['default'])
        row = start + len(parameters)
        hints = [tr('Values are Python expressions, e.g. 3 or "Hello".')]
        if any(not parameter['required'] for parameter in parameters):
            hints.append(tr('Leave optional fields empty to use their defaults.'))
        if any(parameter['required'] for parameter in parameters):
            hints.append(tr('Fields marked with * must be filled in.'))
        ttk.Label(master, text=' '.join(hints), wraplength=550, justify='left').grid(
            row=row, column=0, columnspan=3, sticky='w', pady=(8, 4))
        self.next_row = row + 1
        master.columnconfigure(1, weight=1)
        self.revalidate()

    def set_callback(self, callback):
        self.on_change = callback
        self.revalidate()

    def revalidate(self):
        self.states = field_states(self.parameters, self.expressions(), self.context, enabled(OBJECT_CHECK_ARGUMENTS))
        self.invalid = {name for name, state in self.states.items() if state == "invalid"}
        self.missing = {name for name, state in self.states.items() if state == "missing"}
        self.refresh_borders()
        if self.on_change:
            self.on_change()
        return not self.invalid and not self.missing

    def focus(self, name):
        self.active_name = name
        self.refresh_borders()
        if self.on_focus:
            self.on_focus(name)

    def sync_focus(self):
        try:
            focused = self.master.focus_get()
        except (tk.TclError, KeyError):
            # Tcl-owned combobox popdowns are not Python widget objects.
            return
        name = next((name for name, entry in self.entries.items()
                     if focused is entry or str(focused).startswith(str(entry)+'.')), None)
        self.focus(name)

    def refresh_borders(self):
        background = ttk.Style(self.master).lookup('TFrame', 'background')
        for name, border in self.frames.items():
            color = ui_color(ERROR) if name in self.invalid else ui_color(OBJECT_FOCUS) if name == self.active_name else ui_color(ARGUMENT_MISSING) if name in self.missing else background
            border.configure(background=background, highlightbackground=color, highlightcolor=color)

    def validate(self):
        return '' if self.revalidate() else tr('Check the highlighted fields.')

    def expressions(self):
        return {key: value.get() for key, value in self.values.items()}
