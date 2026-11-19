# SPDX-FileCopyrightText: 2026 Sebastian Ladhoff
# SPDX-License-Identifier: GPL-3.0-only
# See LICENSE in the project root for the full license text.

"""Shared parameter fields for constructors and method calls."""
import ast
import tkinter as tk
from tkinter import ttk

from .i18n import tr


class ArgumentFields:
    def __init__(self, master, parameters, objects=(), *, start=0):
        self.parameters = parameters
        self.values, self.entries = {}, {}
        # Every alias is a valid expression; show the class alongside selection
        # separately in the help below so the field always contains valid Python.
        names = [name for obj in objects for name in obj['names']]
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
            variable = tk.StringVar(master)
            self.values[parameter['name']] = variable
            if names and parameter['kind'] not in ('VAR_POSITIONAL', 'VAR_KEYWORD'):
                field = ttk.Combobox(master, textvariable=variable, values=names, width=30, style='SE.TCombobox')
            else:
                field = ttk.Entry(master, textvariable=variable, width=30, style='SE.TEntry')
            field.grid(row=row, column=1, sticky='ew', pady=4)
            self.entries[parameter['name']] = field
            if parameter['default']:
                ttk.Label(master, text=tr('Default: {value}').format(value=parameter['default']), wraplength=230).grid(
                    row=row, column=2, sticky='w', padx=(8, 0))
        row = start + len(parameters)
        if names:
            ttk.Label(master, text=tr('Enter a value or select an existing object.'), wraplength=550).grid(
                row=row, column=0, columnspan=3, sticky='w', pady=(8, 0))
            row += 1
            objects_label = ', '.join(f"{obj['names'][0]}: {obj['class_name']}" for obj in objects)
            ttk.Label(master, text=tr('Available objects: {objects}').format(objects=objects_label), wraplength=550).grid(
                row=row, column=0, columnspan=3, sticky='w')
            row += 1
        ttk.Label(master, text=tr('Enter Python expressions. Leave optional fields empty to use their defaults.\n* Required argument.'),
                  wraplength=550, justify='left').grid(row=row, column=0, columnspan=3, sticky='w', pady=(8, 4))
        self.next_row = row + 1
        master.columnconfigure(1, weight=1)

    def validate(self):
        for parameter in self.parameters:
            name = parameter['name']
            value = self.values[name].get().strip()
            message = ''
            if not value and parameter['required']:
                message = tr('Enter a value for {name}.').format(name=name)
            elif value:
                try:
                    ast.parse(value, mode='eval')
                except SyntaxError as error:
                    from .execution_errors import report_python_error
                    report_python_error(error)
                    message = tr('Enter a valid Python expression for {name}.').format(name=name)
            if message:
                field = self.entries[name]
                field.focus_set()
                field.selection_range(0, 'end')
                return message
        return ''

    def expressions(self):
        return {key: value.get() for key, value in self.values.items()}
