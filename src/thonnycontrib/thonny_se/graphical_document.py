# SPDX-FileCopyrightText: 2026 Sebastian Ladhoff
# SPDX-License-Identifier: GPL-3.0-only
# See LICENSE in the project root for the full license text.

"""Gemeinsamer Datei- und History-Lebenszyklus grafischer Thonny-Dokumente."""
from .i18n import tr
import copy
import os
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from thonny import get_workbench
from thonny.common import is_remote_path, normpath_with_actual_case
from thonny.editors import Editor


class GraphicalDocument(Editor):
    """Unterklassen stellen Modell, Codec, Auswahl und Darstellung bereit."""
    def __init__(self, master):
        self.document = self.document_model.new_document()
        self._saved_document = copy.deepcopy(self.document)
        self._missing_file = False
        self.selection = self._initial_selection()
        self._selection_anchor = None
        self.undo_stack, self.redo_stack = [], []
        super().__init__(master)
        self._code_view.grid_remove()
        self.get_text_widget().set_read_only(True)

    def _build_zoom_controls(self):
        self._build_scale_preview()
        self.zoom_controls = ttk.Frame(self.zoom_bar)
        self.zoom_controls.pack(side="right")
        self.zoom_text = tk.StringVar(self, value="100 %")
        self.zoom_value = tk.DoubleVar(self, value=100)
        self._updating_zoom = False
        from .tooltips import attach_tip
        self.zoom_out_button = ttk.Button(self.zoom_controls, style="Toolbutton", width=2,
                                          command=lambda: self._step_zoom(-10), takefocus=True)
        self.zoom_out_button.pack(side="left", padx=(0, 3))
        self.zoom_slider = ttk.Scale(self.zoom_controls, from_=50, to=200, length=140,
                                    variable=self.zoom_value, command=self._slide_zoom)
        self.zoom_slider.pack(side="left")
        self.zoom_in_button = ttk.Button(self.zoom_controls, style="Toolbutton", width=2,
                                         command=lambda: self._step_zoom(10), takefocus=True)
        self.zoom_in_button.pack(side="left", padx=(3, 0))
        self.zoom_label = ttk.Label(self.zoom_controls, textvariable=self.zoom_text, width=7, anchor="w")
        self.zoom_label.pack(side="left", padx=(4, 0))
        scalable = hasattr(self.diagram, 'request_diagram_scale')
        for button, text in ((self.scale_down_button, tr('More spacing and lighter contours (also applies to exports)') if scalable else tr('Decrease diagram scale (preview; no effect yet)')),
                             (self.scale_up_button, tr('Less spacing and stronger contours (also applies to exports)') if scalable else tr('Increase diagram scale (preview; no effect yet)')),
                             (self.zoom_out_button, tr('Zoom out (view only)')),
                             (self.zoom_in_button, tr('Zoom in (view only)'))):
            attach_tip(button, text)
            for sequence in ('<Return>', '<KP_Enter>'):
                button.bind(sequence, lambda event, button=button: (button.invoke(), "break")[1])
        self._refresh_zoom_icons()
        self.zoom_bar.bind('<<ThemeChanged>>', lambda event: self._refresh_zoom_icons(), add=True)
        self.diagram.on_zoom = self._zoom_changed

    def _build_scale_preview(self):
        # Tab-local appearance; UML remains a UI prototype. No file-format fields.
        self.scale_controls = ttk.Frame(self.zoom_bar)
        self.scale_controls.pack(side="left", before=self.monochrome_button)
        self.scale_preview_value = tk.DoubleVar(self, value=100)
        self.scale_preview_text = tk.StringVar(self, value="100 %")
        self.scale_down_button = ttk.Button(self.scale_controls, style="Toolbutton", width=2,
            command=lambda: self._scale_preview_changed(self.scale_preview_value.get()-10), takefocus=True)
        self.scale_down_button.pack(side="left", padx=(0, 3))
        self.scale_slider = ttk.Scale(self.scale_controls, from_=50, to=200, length=140,
            variable=self.scale_preview_value, command=self._scale_preview_changed)
        self.scale_slider.pack(side="left")
        self.scale_up_button = ttk.Button(self.scale_controls, style="Toolbutton", width=2,
            command=lambda: self._scale_preview_changed(self.scale_preview_value.get()+10), takefocus=True)
        self.scale_up_button.pack(side="left", padx=(3, 0))
        self.scale_label = ttk.Label(self.scale_controls, textvariable=self.scale_preview_text, width=7, anchor="w")
        self.scale_label.pack(side="left", padx=(4, 0))

    def _scale_preview_changed(self, value):
        value = max(50, min(200, float(value)))
        self.scale_preview_value.set(value)
        self.scale_preview_text.set(f"{round(value)} %")
        self.scale_down_button.state(['disabled'] if value <= 50 else ['!disabled'])
        self.scale_up_button.state(['disabled'] if value >= 200 else ['!disabled'])
        if hasattr(self.diagram, 'request_diagram_scale'):
            self.diagram.request_diagram_scale(value / 100)

    def _refresh_zoom_icons(self):
        from . import retina_icons
        from .iconregistry import menu_icon
        for button, role in ((self.scale_down_button, 'diagram.expand'),
                             (self.scale_up_button, 'diagram.shrink'),
                             (self.zoom_out_button, 'view.zoom_out'),
                             (self.zoom_in_button, 'view.zoom_in')):
            # Inherit Thonny's Toolbutton layout and all interaction colors.
            if not retina_icons.toolbar(button, role):
                button.configure(style='Toolbutton', image=menu_icon(get_workbench(), role), text='')

    def _step_zoom(self, amount):
        # The variable includes pending slider requests, so rapid clicks accumulate.
        self._slide_zoom(max(50, min(200, self.zoom_value.get()+amount)))

    def _zoom_changed(self, value):
        self._updating_zoom = True
        try:
            label=f"{round(value*100)} %"
            if self.zoom_text.get()!=label:self.zoom_text.set(label)
            if self.zoom_value.get()!=value*100:self.zoom_value.set(value*100)
            self.zoom_out_button.state(['disabled'] if value <= .5 else ['!disabled'])
            self.zoom_in_button.state(['disabled'] if value >= 2 else ['!disabled'])
        finally:
            self._updating_zoom = False

    def _slide_zoom(self, value):
        if not self._updating_zoom:
            getattr(self.diagram,"request_zoom",self.diagram.set_zoom)(float(value)/100)

    def _initial_selection(self):
        return None

    def _before_replace(self):
        pass

    def _prepare_save(self):
        return True

    def is_text_editing(self, focus):
        return False

    def _snapshot(self):
        return copy.deepcopy(self.document), self.selection

    def _record(self, before):
        if before[0] != self.document:
            self.undo_stack.append(before)
            self.undo_stack = self.undo_stack[-100:]
            self.redo_stack.clear()
        self._refresh()

    def undo(self):
        self._history(self.undo_stack, self.redo_stack)

    def redo(self):
        self._history(self.redo_stack, self.undo_stack)

    def _history(self, source, target):
        if not source:
            return
        target.append(self._snapshot())
        self.document, self.selection = source.pop()
        self._refresh()

    def is_modified(self):
        # Toolbar and tab-title checks are frequent. Compare the saved model
        # directly instead of validating and serializing it on every query.
        return self._missing_file or self.document != self._saved_document

    def get_title(self):
        name = Path(self._filename).name if self._filename else self.untitled_label
        return name + (" *" if self.is_modified() else "")

    def get_long_description(self):
        return self._filename or self.untitled_label+" · Thonny SE"

    def get_content(self):
        # Nur als Kompatibilität für textorientierte Plugins.
        # Das Modell wird nie als ausführbarer Quelltext ausgegeben.
        return ""

    def focus_set(self):
        if hasattr(self, "diagram"):
            self.diagram.canvas.focus_set()

    def is_focused(self):
        widget = self.focus_displayof()
        return widget is not None and str(widget).startswith(str(self) + ".")

    def _listen_for_toplevel_response(self, event):
        self.get_text_widget().set_read_only(True)

    def _load_file(self, filename, keep_undo=False):
        if is_remote_path(filename):
            messagebox.showerror(tr('Open {document}').format(document=self.document_label), tr('Diagrams currently support local files only.'), parent=self)
            return False
        try:
            document = self.file_codec.read_document(filename)
            mtime = os.path.getmtime(filename)
        except (OSError, ValueError) as exc:
            messagebox.showerror(tr('Open {document}').format(document=self.document_label), str(exc), parent=self)
            return False
        # Erst nach vollständiger Prüfung das bestehende Dokument ersetzen.
        self._before_replace()
        self.document = document
        self.selection = self._initial_selection()
        self._selection_anchor = None
        self.undo_stack.clear()
        self.redo_stack.clear()
        self._filename = normpath_with_actual_case(os.path.abspath(filename))
        self._last_known_mtime = mtime
        self._missing_file = False
        self._saved_document = copy.deepcopy(document)
        self.notebook.remember_recent_file(self._filename)
        self._refresh()
        get_workbench().event_generate("Open", editor=self, filename=self._filename)
        return True

    def save_file(self, ask_filename=False, save_copy=False, node=None, *, suggested_stem=None):
        if not self._prepare_save():
            return None
        if node not in (None, "local"):
            messagebox.showerror(tr('Save {document}').format(document=self.document_label), tr('Please use a local save location.'), parent=self)
            return None
        path = self._filename
        if ask_filename or not path:
            path = filedialog.asksaveasfilename(
                parent=self, title=tr('Save {document}').format(document=self.document_label), defaultextension=self.file_codec.EXTENSION,
                initialdir=str(Path(self._filename).parent) if self._filename else get_workbench().get_local_cwd(),
                initialfile=Path(self._filename).name if self._filename else (suggested_stem or self.default_stem) + self.file_codec.EXTENSION,
                # Use the final suffix consistently with the Open dialog. Native
                # providers differ in their handling of compound-extension filters.
                filetypes=[(self.document_label, ".json"), (tr('All files'), "*")],
            )
        if not path:
            return None
        path = os.path.abspath(path)
        if not self.file_codec.is_model_path(path):
            messagebox.showerror(tr('Save {document}').format(document=self.document_label), tr('Please use the file extension {extension}.').format(extension=self.file_codec.EXTENSION), parent=self)
            return None
        other = self.notebook.get_editor(path)
        if other is not None and other is not self:
            messagebox.showerror(tr('Save {document}').format(document=self.document_label), tr('This file is already open in another tab.'), parent=self)
            return None
        try:
            self.file_codec.write_document(path, self.document)
        except (OSError, ValueError) as exc:
            messagebox.showerror(tr('Save {document}').format(document=self.document_label), str(exc), parent=self)
            return None
        # Speichern einer Kopie unter einem anderen Namen verändert das Dokument nicht.
        same_file = self._filename and Path(path).resolve() == Path(self._filename).resolve()
        if not save_copy or same_file:
            self._filename = normpath_with_actual_case(path)
            self._last_known_mtime = os.path.getmtime(path)
            self._missing_file = False
            self._saved_document = copy.deepcopy(self.document)
        self.notebook.remember_recent_file(path)
        self._refresh()
        get_workbench().event_generate("LocalFileOperation", path=path, operation="save")
        return path

    def check_for_external_changes(self):
        if not self._filename:
            return
        try:
            mtime = os.path.getmtime(self._filename)
        except FileNotFoundError:
            self._last_known_mtime = None
            if not self._missing_file:
                self._missing_file = True
                self._refresh()
            return
        if mtime == self._last_known_mtime:
            return
        reload_automatically = not self.is_modified() and get_workbench().get_option("edit.auto_refresh_saved_files")
        if reload_automatically or messagebox.askyesno(
            tr('Externally changed {document}').format(document=self.document_label), tr('The file was changed outside Thonny.\nDiscard the current document and reload?'), parent=self
        ):
            if not self._load_file(self._filename):
                self._last_known_mtime = mtime
                self._missing_file = True
                self._refresh()
        else:
            # Abgelehnte externe Änderungen bei nächstem Speichern bewusst ersetzen.
            self._last_known_mtime = mtime
            self._missing_file = True
            self._refresh()
