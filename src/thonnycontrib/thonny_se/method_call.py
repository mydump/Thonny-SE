# SPDX-FileCopyrightText: 2026 Sebastian Ladhoff
# SPDX-License-Identifier: GPL-3.0-only
# See LICENSE in the project root for the full license text.

"""Structured method calls in the object inspector, using the live backend."""
from uuid import uuid4
from tkinter import ttk, messagebox

from thonny import get_runner
from thonny.common import InlineCommand

from .arguments import ArgumentFields
from .dialogs import EditDialog
from .i18n import tr
from .ui_style import ERROR, SELECT


def method_error(response):
    if response.get('error_type') == 'KeyboardInterrupt':
        return tr('Method call interrupted.')
    messages = {
        'stale_object': tr('This object or method has changed. Please open the method again.'),
        'unsupported_method': tr('This method cannot be represented by the parameter dialog.'),
        'async_method': tr('Call asynchronous methods in the Python shell using an event loop.'),
        'invalid_varargs': tr('Enter a list or tuple for additional positional arguments.'),
        'invalid_kwargs': tr('Enter a dictionary with string keys for additional keyword arguments.'),
        'duplicate_arguments': tr('An argument was supplied more than once.'),
    }
    return messages.get(response.get('error'), tr('Method call failed: {type}: {error}').format(
        type=response.get('error_type', ''), error=response.get('error', '')))


class MethodCallDialog(EditDialog):
    def __init__(self, controller, owner, name, method, prepared):
        self.controller, self.prepared = controller, prepared
        self.name, self.method = name, method
        self.waiting = False
        self.result = None
        super().__init__(owner, tr('Call method'))

    def build_body(self, master):
        self.controller.dialog = self
        ttk.Label(master, text=f'{self.name}.{self.method}{self.prepared["signature"]}',
                  font='TkHeadingFont', wraplength=600).grid(row=0, column=0, columnspan=3, sticky='w', pady=(0, 8))
        row = 1
        documentation = self.prepared.get('documentation')
        if documentation:
            # A bounded, scrollable read-only area also accommodates longer docstrings.
            import tkinter as tk
            help_frame = ttk.Frame(master)
            help_frame.grid(row=row, column=0, columnspan=3, sticky='ew', pady=(0, 8))
            text = tk.Text(help_frame, height=min(5, len(documentation.splitlines())+1), width=64,
                           wrap='word', font='TkDefaultFont', relief='flat', borderwidth=0,
                           background=ttk.Style(self).lookup('TFrame', 'background') or self.cget('background'),
                           foreground=ttk.Style(self).lookup('TLabel', 'foreground') or '#202020')
            text.insert('1.0', documentation)
            text.configure(state='disabled')
            text.pack(side='left', fill='both', expand=True)
            scroll = ttk.Scrollbar(help_frame, orient='vertical', command=text.yview)
            scroll.pack(side='right', fill='y')
            text.configure(yscrollcommand=scroll.set)
            row += 1
        self.arguments = ArgumentFields(master, self.prepared['parameters'], self.controller.objects.objects, start=row)
        self.values = self.arguments.values
        row = self.arguments.next_row
        self.error = ttk.Label(master, foreground=ERROR, wraplength=550, justify='left')
        self.error.grid(row=row, column=0, columnspan=3, sticky='w')
        self.output = ttk.Label(master, foreground=SELECT, wraplength=550, justify='left')
        self.output.grid(row=row+1, column=0, columnspan=3, sticky='w', pady=(4, 0))
        return next(iter(self.arguments.entries.values()), None)

    def buttonbox(self):
        actions = ttk.Frame(self, padding=(20, 4, 20, 16), style='SE.TFrame')
        actions.pack(fill='x')
        actions.grid_anchor('e')
        self.close_button = self._action_button(actions, 0, tr('Stop'), self.cancel, gap=8)
        self.close_button.configure(text=tr('Close'))
        self.apply_button = self._action_button(actions, 1, tr('Call'), self.ok)
        self.bind('<Return>', self.ok)
        self.bind('<KP_Enter>', self.ok)
        self.bind('<Escape>', self.cancel)

    def ok(self, event=None):
        if self.waiting:
            return
        error = self.arguments.validate()
        self.error.configure(text=error)
        if error:
            return
        self.output.configure(text='')
        self.controller.call(self)

    def completed(self, response):
        self.waiting = False
        self.apply_button.configure(state='normal')
        self.close_button.configure(text=tr('Close'))
        self.error.configure(text=method_error(response) if 'error' in response else '')
        self.output.configure(text='' if 'error' in response else tr('Result: {value}').format(value=response['result']))

    def cancel(self, event=None):
        if self.waiting:
            runner = get_runner()
            if runner and runner.get_backend_proxy():
                runner.get_backend_proxy().interrupt()
            return
        super().cancel(event)


class MethodCallController:
    def __init__(self, objects):
        self.objects = objects
        self.workbench = objects.workbench
        self.pending = None
        self.dialog = None
        self.workbench.bind('thonny_se_prepare_method_response', self.prepared, True)
        self.workbench.bind('thonny_se_call_method_response', self.completed, True)
        self.workbench.bind('BackendRestart', self.restart, True)

    def available(self):
        return self.objects.session.available()

    def open(self, owner, obj, method):
        if self.pending or self.dialog is not None:
            return
        if not self.available():
            messagebox.showinfo(tr('Call method'), tr('Wait until the local Python interpreter is ready.'), parent=owner)
            return
        current = obj
        path = current.get('path', current['names'][0] if current['names'] else '')
        name = (path['root'] if isinstance(path,dict) else path)
        if isinstance(path,dict):
            for step in path['steps']:
                name += '.'+step[1] if step[0]=='attr' else '['+str(step[1])+']' if step[0]=='index' else '[…]'
        request = uuid4().hex
        self.pending = request, owner, name, method
        get_runner().send_command(InlineCommand('thonny_se_prepare_method', request_id=request,
            object_name=path, object_id=current['id'], method=method))

    def prepared(self, response):
        if not self.pending or response.get('request_id') != self.pending[0]:
            return
        request, owner, name, method = self.pending
        if not owner.winfo_exists():
            self.pending = None
            return
        if 'error' in response:
            self.workbench.show_view('ShellView', set_focus=False)
            self.pending = None
            messagebox.showerror(tr('Call method'), method_error(response), parent=owner)
            return
        # Open outside Thonny's response handler so its backend polling resumes.
        self.workbench.after_idle(lambda: self.show_dialog(request, owner, name, method, response))

    def show_dialog(self, request, owner, name, method, response):
        if not self.pending or self.pending[0] != request or not owner.winfo_exists():
            return
        self.pending = None
        dialog = MethodCallDialog(self, owner, name, method, response)
        if self.dialog is dialog:
            self.dialog = None

    def call(self, dialog):
        if not self.available():
            dialog.error.configure(text=tr('Wait until the local Python interpreter is ready.'))
            return
        dialog.waiting = True
        dialog.apply_button.configure(state='disabled')
        dialog.close_button.configure(text=tr('Stop'))
        request = uuid4().hex
        self.pending = request, dialog
        get_runner().send_command(InlineCommand('thonny_se_call_method', request_id=request,
            token=dialog.prepared['token'], values=dialog.arguments.expressions(),
            expanded=list(self.objects.existing_view().expanded) if self.objects.existing_view() is not None else [],
            item_limits=self.objects.existing_view().item_limits if self.objects.existing_view() is not None else {},
            representation_error=tr('<Representation failed>')))

    def completed(self, response):
        if 'error' in response:
            self.workbench.show_view('ShellView', set_focus=False)
        if not self.pending or response.get('request_id') != self.pending[0]:
            return
        _, dialog = self.pending
        self.pending = None
        if 'objects' in response:
            self.objects.received(response)
        if dialog.winfo_exists():
            dialog.completed(response)

    def restart(self, event):
        self.pending = None
        if self.dialog is not None and self.dialog.winfo_exists():
            self.dialog.waiting = False
            self.dialog.cancel()
        self.dialog = None
