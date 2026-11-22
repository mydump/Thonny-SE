# SPDX-FileCopyrightText: 2026 Sebastian Ladhoff
# SPDX-License-Identifier: GPL-3.0-only
# See LICENSE in the project root for the full license text.

"""Create real objects in Thonny's local CPython and track their source session."""
import keyword
from uuid import uuid4
import tkinter as tk
from tkinter import ttk

from thonny import get_runner
from thonny.common import InlineCommand

from .arguments import ArgumentFields
from .dialogs import EditDialog
from .i18n import tr
from .ui_style import ERROR


class InstantiationDialog(EditDialog):
    def __init__(self, session, owner, class_name, prepared):
        self.session, self.prepared = session, prepared
        self.class_name = class_name
        self.editor = owner
        self.values = {}
        self.waiting = False
        self.result = None
        super().__init__(owner, tr('Instantiate object …'))

    def build_body(self, master):
        self.session.dialog = self
        ttk.Label(master, text=self.class_name, font='TkHeadingFont').grid(row=0, column=0, columnspan=2, sticky='w', pady=(0, 8))
        ttk.Label(master, text=tr('Object name')).grid(row=1, column=0, sticky='w', padx=(0, 12))
        base = self.class_name.rsplit('.', 1)[-1]
        base = base[:1].lower() + base[1:]
        if not base.isidentifier() or keyword.iskeyword(base) or base.startswith('_'):
            base = 'obj'
        name = base + '1'
        index = 1
        while name in self.prepared['names']:
            index += 1
            name = base + str(index)
        self.object_name = tk.StringVar(self, value=name)
        first = ttk.Entry(master, textvariable=self.object_name, width=30, style='SE.TEntry')
        first.grid(row=1, column=1, sticky='ew', pady=4)
        self.arguments = ArgumentFields(master, self.prepared['parameters'], self.session.controller.objects, start=2)
        self.values = self.arguments.values
        row = self.arguments.next_row
        self.error = ttk.Label(master, foreground=ERROR, wraplength=450, justify='left')
        self.error.grid(row=row, column=0, columnspan=3, sticky='w')
        master.columnconfigure(1, weight=1)
        return first

    def buttonbox(self):
        super().buttonbox()
        self.apply_button.configure(text=tr('Instantiate'))
        self.apply_button.master.columnconfigure(1, minsize=150)

    def validate(self):
        name = self.object_name.get().strip()
        if not name.isidentifier() or keyword.iskeyword(name) or name.startswith('_'):
            self.error.configure(text=tr('Use a Python object name that does not start with an underscore.'))
            return False
        if name in self.prepared['names']:
            self.error.configure(text=tr('The name {name!r} is already in use.').format(name=name))
            return False
        error = self.arguments.validate()
        self.error.configure(text=error)
        return not error

    def ok(self, event=None):
        if self.waiting or not self.validate():
            return
        self.waiting = True
        self.apply_button.configure(state='disabled')
        self.session.create(self, self.object_name.get().strip(), {key: value.get() for key, value in self.values.items()})

    def completed(self, response):
        self.waiting = False
        if 'error' in response:
            self.error.configure(text=self.session.error_text(response))
            self.apply_button.configure(state='normal')
            return
        self.result = self.object_name.get().strip()
        self.cancel()

    def cancel(self, event=None):
        if self.waiting:
            return
        super().cancel(event)


class ObjectSession:
    def __init__(self, controller):
        from .execution_state import ExecutionState
        self.controller, self.workbench = controller, controller.workbench
        self.state = ExecutionState()
        self.classes = {}
        self.pending = self.dialog = self.run_request = None
        self.active = False
        self.files = {}  # Compatibility only; execution no longer polls or saves files.
        self.workbench.bind('CommandAccepted', self.command_accepted, True)
        for event, handler in (
                ('thonny_se_load_diagram_response', self.loaded),
                ('thonny_se_prepare_class_response', self.prepared),
                ('thonny_se_instantiate_response', self.created)):
            self.workbench.bind(event, handler, True)

    def available(self):
        from thonny.plugins.cpython_frontend.cp_front import LocalCPythonProxy
        runner = get_runner()
        return bool(runner and runner.is_waiting_toplevel_command()
                    and isinstance(runner.get_backend_proxy(), LocalCPythonProxy))

    def can_run(self):
        from thonny.plugins.cpython_frontend.cp_front import LocalCPythonProxy
        runner = get_runner()
        try:
            grab = self.workbench.grab_current()
            # A native dialog can restore a grab to the main window on Windows.
            # Only an actually visible popup/modal window should block Run.
            blocked = bool(grab is not None and grab.winfo_viewable()
                           and (isinstance(grab, tk.Menu) or grab.winfo_toplevel() is not self.workbench))
        except (tk.TclError, KeyError):
            blocked = False
        return bool(runner and isinstance(runner.get_backend_proxy(), LocalCPythonProxy)
                    and self.run_request is None and not blocked)

    def can_instantiate(self, editor, cid):
        if editor.diagram.editing is not None and editor.diagram.pending():
            return False
        return (self.available() and self.run_request is None and self.state.ready(editor)
                and self.classes.get(cid, {}).get('instantiable', False))

    def notify(self):
        for editor in self.workbench.get_editor_notebook().get_all_editors():
            if hasattr(editor, 'source_status'):
                editor.diagram._update_intro()
        view = self.controller.existing_view()
        if view is not None:
            view.draw()
        self.workbench._update_toolbar()

    def watch_diagram(self, editor):
        previous = self.state.stale
        self.state.changed(editor)
        if previous != self.state.stale:
            self.notify()

    def command_accepted(self, event):
        if event.command.get('name') not in ('Run', 'run', 'Debug', 'FastDebug'):
            return
        self.run_request = None
        self.classes = {}
        self.state.clear()
        self.pending = None
        self.active = False
        self.notify()

    def run_diagram(self, editor):
        if not editor.diagram.finish_edit():
            return
        from .integration import read_python_source
        from .uml_runtime import diagram_fingerprint
        from .uml_run_review import reviewed_execution
        request = dict(id=uuid4().hex, editor=editor,
                       fingerprint=diagram_fingerprint(editor.document), payload=None, error=None, restarting=True)
        try:
            request['payload'] = reviewed_execution(editor, read_python_source,
                token=str(editor.winfo_id()), label=editor.get_filename() or tr('New UML diagram'))
            if request['payload'] is None:
                return
            request['fingerprint'] = diagram_fingerprint(editor.document)
        except (OSError, ValueError, SyntaxError, RecursionError) as error:
            from .execution_errors import report_python_error
            report_python_error(error)
            return
        # Re-execution is the only operation which discards old objects/definitions.
        self.run_request = request
        self.controller.restart(None)
        editor.execution_hint_visible = False
        try:
            get_runner().restart_backend(clean=True, automatic=True)
        except Exception as error:
            self.run_request = None
            from .execution_errors import report_python_error
            report_python_error(error)
            self.notify()
            return
        request['restarting'] = False
        self.workbench.after(50, lambda: self.submit_run(request))
        self.notify()

    def submit_run(self, request, remaining=100):
        if self.run_request is not request:
            return
        editor = request['editor']
        if not editor.winfo_exists():
            self.run_request = None
            return
        if not self.available():
            if remaining:
                self.workbench.after(100, lambda: self.submit_run(request, remaining-1))
            else:
                self.run_request = None
                from .execution_errors import report_python_error
                report_python_error(RuntimeError(tr('The Python interpreter is not ready.')))
                self.notify()
            return
        if request['error'] is not None:
            self.run_request = None
            from .execution_errors import report_python_error
            report_python_error(request['error'])
            self.notify()
            return
        payload = request['payload']
        try:
            get_runner().send_command(InlineCommand('thonny_se_load_diagram', request_id=request['id'],
                sources=payload['sources'], targets=payload['targets']))
        except Exception as error:
            self.run_request = None
            from .execution_errors import report_python_error
            report_python_error(error)
            self.notify()

    def loaded(self, response):
        request = self.run_request
        if request is None or response.get('request_id') != request['id']:
            return
        self.run_request = None
        editor = request['editor']
        if not editor.winfo_exists():
            return
        if 'error' in response:
            self.workbench.show_view('ShellView', set_focus=False)
            self.state.clear()
            self.classes = {}
        else:
            self.classes = response['classes']
            self.active = True
            self.state.loaded(editor, request['fingerprint'])
            self.controller.received(response)
        self.notify()

    def instantiate(self, editor, cid):
        if self.pending is not None or not editor.diagram.finish_edit() or not self.can_instantiate(editor, cid):
            return
        request = uuid4().hex
        self.pending = request, editor, cid
        get_runner().send_command(InlineCommand('thonny_se_prepare_class', request_id=request,
            loaded_token=self.classes[cid]['token']))

    def prepared(self, response):
        if self.pending is None or response.get('request_id') != self.pending[0]:
            return
        request, editor, cid = self.pending
        if 'error' in response:
            self.pending = None
            self.workbench.show_view('ShellView', set_focus=False)
            return
        if not editor.winfo_exists() or not self.can_instantiate(editor, cid):
            self.pending = None
            return
        self.workbench.after_idle(lambda: self.show_dialog(request, editor, cid, response))

    def show_dialog(self, request, editor, cid, response):
        if self.pending is None or self.pending[0] != request or not self.can_instantiate(editor, cid):
            self.pending = None
            return
        self.pending = None
        self.dialog = None
        dialog = InstantiationDialog(self, editor, editor.card(cid)['name'], response)
        if self.dialog is dialog:
            self.dialog = None

    def create(self, dialog, name, values):
        if not self.available() or not self.state.ready(dialog.editor):
            dialog.waiting = False
            dialog.error.configure(text=tr('Run the current diagram before instantiating objects.'))
            dialog.apply_button.configure(state='normal')
            return
        self.dialog = dialog
        request = uuid4().hex
        self.pending = request, dialog
        get_runner().send_command(InlineCommand('thonny_se_instantiate', request_id=request,
            token=dialog.prepared['token'], object_name=name, values=values,
            expanded=list(self.controller.existing_view().expanded) if self.controller.existing_view() is not None else [],
            item_limits=self.controller.existing_view().item_limits if self.controller.existing_view() is not None else {},
            representation_error=tr('<Representation failed>')))

    def created(self, response):
        if 'error' in response:
            self.workbench.show_view('ShellView', set_focus=False)
        if self.pending is None or response.get('request_id') != self.pending[0]:
            return
        _, dialog = self.pending
        self.pending = None
        if not dialog.winfo_exists():
            return
        if 'error' not in response:
            self.controller.received(response)
        dialog.completed(response)

    def restarted(self):
        # Preserve only the restart initiated by this Run; Stop cancels pending loads.
        if self.run_request is not None and not self.run_request.get('restarting'):
            self.run_request = None
        self.state.clear()
        self.classes = {}
        self.pending = None
        self.active = False
        if self.dialog is not None and self.dialog.winfo_exists():
            self.dialog.waiting = False
            self.dialog.cancel()
        self.dialog = None

    @staticmethod
    def error_text(response):
        return tr('Instantiation failed: {type}: {error}').format(
            type=response.get('error_type', ''), error=response.get('error', ''))
