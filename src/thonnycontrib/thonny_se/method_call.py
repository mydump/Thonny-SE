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
from .runtime_dialog_ui import heading, documentation, warning, follow_theme, ResultPanel


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
    INTERRUPT_TIMEOUT_MS = 2000

    def __init__(self, controller, owner, name, method, prepared):
        self.controller, self.prepared = controller, prepared
        self.name, self.method = name, method
        self.waiting = False
        self.interrupt_timer = None
        self.result = None
        super().__init__(owner, tr('Call method'))

    def build_body(self, master):
        self.controller.dialog = self
        prefix = f'{self.name}.{self.method}'
        spans = {name: (len(prefix)+start, len(prefix)+end)
                 for name, (start, end) in self.prepared.get('parameter_spans', {}).items()}
        self.heading = heading(master, prefix+self.prepared['signature'], 'object', '', parameter_spans=spans, surface='#ffffff')
        row = 1
        doc = self.prepared.get('documentation')
        if doc:
            self.documentation = documentation(master, doc, row, truncated=self.prepared.get('documentation_truncated', False))
            row += 1
        self.arguments = ArgumentFields(master, self.prepared['parameters'], self.controller.objects.objects, start=row, on_focus=self.heading.highlight_parameter, context=self.prepared.get('argument_context'))
        self.values = self.arguments.values
        row = self.arguments.next_row
        self.output = ResultPanel(master, row)
        self.stop_help = warning(master,
            tr('The method is still running. You can end the Python session. This removes all objects.'), row+2)
        stop_actions = ttk.Frame(self.stop_help)
        stop_actions.grid(row=1, column=1, sticky='e', pady=(10, 0))
        self.end_session_button = self._action_button(stop_actions, 0, tr('End Python session'), self.end_session)
        self.stop_help.grid_remove()
        follow_theme(self, self.output)
        return next(iter(self.arguments.entries.values()), None)

    def buttonbox(self):
        # simpledialog packs its body without fill/expand before calling us.
        # Apply this only to runtime dialogs (also inherited by instantiation).
        content = self.output.master
        content.master.pack_configure(fill='both', expand=True)
        content.columnconfigure(1, weight=1)
        content.rowconfigure(int(self.output.grid_info()['row']), weight=1)
        self.output.grid_configure(sticky='nsew')
        self.output.rowconfigure(0, weight=1)
        actions = ttk.Frame(self, padding=(20, 4, 20, 16), style='SE.TFrame')
        actions.pack(side='bottom', fill='x')
        actions.grid_anchor('e')
        self.close_button = self._action_button(actions, 0, tr('Stop'), self.cancel, gap=8)
        self.close_button.configure(text=tr('Close'))
        self.apply_button = self._action_button(actions, 1, tr('Call'), self.ok)
        self.bind('<Return>', self.ok)
        self.bind('<KP_Enter>', self.ok)
        self.bind('<Escape>', self.cancel)
        self.arguments.set_callback(self.update_call_enabled)

    def update_call_enabled(self):
        valid = not self.arguments.invalid and not self.arguments.missing
        self.apply_button.configure(state='normal' if valid and not self.waiting else 'disabled')

    def ok(self, event=None):
        if self.waiting:
            return
        if not self.arguments.revalidate():
            return
        self.output.set()
        self.controller.call(self)

    def completed(self, response):
        self.clear_interrupt_help()
        self.waiting = False
        self.arguments.context = response.get('argument_context', self.arguments.context)
        self.arguments.revalidate()
        self.close_button.configure(text=tr('Close'))
        self.output.set(tr('Call failed. See the Python shell.') if 'error' in response else response['result'], failed='error' in response)

    def cancel(self, event=None):
        if self.waiting:
            runner = get_runner()
            if runner and runner.get_backend_proxy():
                if self.interrupt_timer is None and not self.stop_help.winfo_ismapped():
                    self.interrupt_timer = self.after(self.INTERRUPT_TIMEOUT_MS, self.show_interrupt_help)
                runner.get_backend_proxy().interrupt()
            return
        super().cancel(event)

    def show_interrupt_help(self):
        self.interrupt_timer = None
        if self.waiting:
            self.stop_help.grid()
            self.update_idletasks()
            # geometry() positions the window frame; winfo_root* describes its
            # client area. Account for native decoration instead of mixing them.
            x0, y0 = self.winfo_vrootx(), self.winfo_vrooty()
            border = max(0, self.winfo_rootx()-self.winfo_x())
            title = max(0, self.winfo_rooty()-self.winfo_y())
            frame_width = self.winfo_width()+2*border
            frame_height = self.winfo_height()+title+border
            x = max(x0, min(self.winfo_x(), x0+self.winfo_vrootwidth()-frame_width))
            y = max(y0, min(self.winfo_y(), y0+self.winfo_vrootheight()-frame_height))
            self.geometry(f'+{x}+{y}')

    def clear_interrupt_help(self):
        if self.interrupt_timer is not None:
            self.after_cancel(self.interrupt_timer)
            self.interrupt_timer = None
        self.stop_help.grid_remove()

    def end_session(self):
        if self.waiting:
            runner = get_runner()
            if runner and runner.get_backend_proxy():
                runner.cmd_stop_restart()

    def destroy(self):
        self.clear_interrupt_help()
        super().destroy()


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
            dialog.output.set(tr('Wait until the local Python interpreter is ready.'), failed=True)
            return
        dialog.output.set()
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
