# SPDX-FileCopyrightText: 2026 Sebastian Ladhoff
# SPDX-License-Identifier: GPL-3.0-only
# See LICENSE in the project root for the full license text.

"""Session-local card arrangement and naming returned Python objects."""
import keyword
import tkinter as tk
from tkinter import ttk

from .dialogs import EditDialog
from .i18n import tr
from .runtime_dialog_ui import heading
from .ui_style import ARGUMENT_MISSING, ERROR, OBJECT_FOCUS, ui_color


class ObjectBankLayout:
    def __init__(self):
        self.order = []
        self.collapsed = set()

    def sync(self, objects):
        by_id = {obj['id']: obj for obj in objects}
        self.order = [key for key in self.order if key in by_id]
        self.order.extend(key for key in by_id if key not in self.order)
        self.collapsed.intersection_update(by_id)
        return [by_id[key] for key in self.order]

    def move(self, key, index):
        if key not in self.order:
            return
        self.order.remove(key)
        self.order.insert(max(0, min(len(self.order), index)), key)

    def clear(self):
        self.order.clear()
        self.collapsed.clear()


class ObjectNameDialog(EditDialog):
    def __init__(self, owner, class_name, names):
        from .instantiation import suggested_object_name
        self.class_name = class_name
        self.names = set(names)
        self.suggestion = suggested_object_name(class_name, self.names)
        self.result = None
        self.focused = False
        super().__init__(owner, tr('Keep result object'))

    def build_body(self, master):
        heading(master, self.class_name, 'object', '')
        ttk.Label(master, text=tr('Object name')).grid(row=1, column=0, sticky='w', padx=(0, 12))
        self.name = tk.StringVar(self, value=self.suggestion)
        self.border = tk.Frame(master, borderwidth=0, highlightthickness=2)
        self.border.grid(row=1, column=1, sticky='ew', pady=(8, 4))
        self.border.columnconfigure(0, weight=1)
        self.entry = ttk.Entry(self.border, textvariable=self.name, style='SE.TEntry', width=30)
        self.entry.grid(row=0, column=0, sticky='ew')
        self.entry.bind('<FocusIn>', lambda event: self.focus_name(True))
        self.entry.bind('<FocusOut>', lambda event: self.focus_name(False))
        self.border.bind('<<ThemeChanged>>', lambda event: self.refresh())
        self.name.trace_add('write', lambda *args: self.refresh())
        ttk.Label(master, text=tr('Choose an unused Python name.'), wraplength=360).grid(
            row=2, column=0, columnspan=2, sticky='w', pady=(8, 0))
        master.columnconfigure(1, weight=1)
        self.refresh()
        return self.entry

    def buttonbox(self):
        super().buttonbox()
        self.apply_button.configure(text=tr('Keep object'))
        self.refresh()

    def valid(self):
        name = self.name.get()
        return name.isidentifier() and not keyword.iskeyword(name) and name not in self.names

    def focus_name(self, focused):
        self.focused = focused
        self.refresh()

    def refresh(self):
        color = (ui_color(ERROR) if self.name.get() and not self.valid() else
                 ui_color(OBJECT_FOCUS) if self.focused else
                 ui_color(ARGUMENT_MISSING) if not self.name.get() else
                 (ttk.Style(self).lookup('TFrame', 'background') or self.cget('background')))
        self.border.configure(background=color, highlightbackground=color, highlightcolor=color)
        if hasattr(self, 'apply_button'):
            self.apply_button.configure(state='normal' if self.valid() else 'disabled')

    def validate(self):
        return self.valid()

    def apply(self):
        self.result = self.name.get()


class ObjectValueChanges:
    """Compare displayed values without calling user equality/property code."""
    DURATION = 2.0

    def __init__(self):
        self.values = {}
        self.described = set()
        self.until = {}

    def observe(self, objects, now):
        current, described, ids, object_ids = {}, set(), set(), set()
        def visit(node):
            if node.get('kind') == 'scalar':
                return
            key = node['id'];ids.add(key)
            if node.get('kind') != 'container' and (node.get('expanded') or node.get('attributes')):
                described.add(key);object_ids.add(key)
                for name,value in node.get('attributes', {}).items():
                    child = node.get('references', {}).get(name)
                    current[key,name] = (('reference',child['id'],child.get('length')) if child else
                                         ('value',value))
            if node.get('kind')=='container' and node.get('expanded'):
                described.add(key)
                for entry in node.get('items', ()):
                    child = entry['node']
                    step = tuple(child['path']['steps'][-1])
                    current[key,step] = (('value',child['value']) if child['kind']=='scalar' else
                                         ('reference',child['id'],child.get('length')))
            for child in node.get('references', {}).values():
                visit(child)
            for entry in node.get('items', ()):
                visit(entry['node'])
        for obj in objects:
            visit(obj)
        for key,value in current.items():
            if key[0] in self.described and ((key in self.values and value!=self.values[key]) or
                                            (key not in self.values and key[0] in object_ids)):
                self.until[key] = now+self.DURATION
        self.values = {key:value for key,value in self.values.items()
                       if key[0] in ids and key[0] not in described}
        self.values.update(current)
        self.described.intersection_update(ids)
        self.described.update(described)
        self.until = {key:end for key,end in self.until.items() if key[0] in ids and end>now}
        return ids

    def strength(self, key, now):
        remaining = self.until.get(key,now)-now
        return max(0.,min(1.,remaining/1.4))

    def clear(self):
        self.values.clear();self.described.clear();self.until.clear()
