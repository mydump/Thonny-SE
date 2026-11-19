# SPDX-FileCopyrightText: 2026 Sebastian Ladhoff
# SPDX-License-Identifier: GPL-3.0-only
# See LICENSE in the project root for the full license text.

"""Ein grafisches Dokument mit Thonnys Editor-Lebenszyklus.

Die geerbte, leere CodeView bleibt als Kompatibilitätsobjekt für Thonnys
eingebaute Plugins erhalten. Sie speichert weder Modell noch Python-Code.
"""
from .i18n import tr
import copy
import json
import os
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from thonny import get_workbench
from thonny.common import is_remote_path, normpath_with_actual_case
from .graphical_document import GraphicalDocument
from . import model as structogram_model, storage as structogram_storage

from .canvas import StructogramCanvas
from .codegen import generate_python
from .iconregistry import menu_icon
from . import retina_icons
from .imageexport import snapshot, export_image
from .palette import ElementPalette
from .interaction import DiagramInteraction
from .dialogs import BlockTextDialog, LoopFieldsDialog, IfDialog, CaseDialog, ImageSizeDialog
from .model import (IF_KINDS, LOOP_FIELDS, Selection, body_at, child_bodies, delete_node, insert_copies, insert_node, move_node, parent_selection, set_if_variant,
                    new_document, selected_node, selected_nodes, move_selection)
from .storage import diagram_stem, dumps, is_model_path, read_document, write_document, write_text, is_diagram_path


BLOCK_CLIPBOARD_PREFIX = "THONNY_SE_BLOCK\n"


class StructogramEditor(GraphicalDocument):
    document_model = structogram_model
    file_codec = structogram_storage
    document_label = tr('Structogram')
    default_stem = "struktogramm"
    untitled_label = tr('New structogram')

    def _initial_selection(self):
        return Selection()

    def __init__(self, master):
        super().__init__(master)

        self.surface = ttk.Frame(self, padding=8)
        self.surface.grid(row=0, column=0, sticky="nsew")
        self.surface.home_widget = self
        self.maximizable_widget = self.surface
        self.zoom_bar = ttk.Frame(self.surface)
        self.zoom_bar.pack(side="bottom", anchor="e", pady=(6, 0))
        main = ttk.Frame(self.surface)
        main.pack(fill="both", expand=True)
        main.rowconfigure(0, weight=1)
        main.columnconfigure(1, weight=1)
        self.palette_mode = tk.StringVar(self, value="Einfach")
        self.palette = ElementPalette(main, self.palette_mode, self.insert_block)
        self.palette.grid(row=0, column=0, sticky="ns")
        self.palette_buttons = self.palette.buttons
        for widget in (self.palette.disclosure, self.palette.canvas, *self.palette_buttons.values()):
            self._bind_history(widget)
        self.diagram = StructogramCanvas(main, self.select_region, self.edit_block)
        self.diagram.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        self.monochrome = tk.BooleanVar(self, value=False)
        style = ttk.Style(self)
        background = style.lookup("TFrame", "background") or "#ececec"
        style.configure("SE.Monochrome.TCheckbutton", background=background)
        style.map("SE.Monochrome.TCheckbutton", background=[("active", background), ("!active", background)])
        self.monochrome_button = ttk.Checkbutton(self.zoom_bar, text=tr('Monochrome'), variable=self.monochrome,
                                                 style="SE.Monochrome.TCheckbutton",
                                                 command=self._set_monochrome)
        self.monochrome_button.pack(side="left", padx=(0, 28))
        self._build_zoom_controls()
        self._bind_history(self.diagram.canvas)
        self.diagram.canvas.bind("<Delete>", lambda event: self.delete_block() or "break")
        self.diagram.canvas.bind("<BackSpace>", lambda event: self.delete_block() or "break")
        self.diagram.canvas.bind("<Return>", lambda event: self.edit_block() or "break")
        self.diagram.canvas.bind("<KP_Enter>", lambda event: self.edit_block() or "break")
        self.diagram.canvas.bind("<Control-Tab>", self._control_tab)
        for key, command in (("<Up>", lambda: self.navigate(-1)), ("<Down>", lambda: self.navigate(1)),
                             ("<Left>", self.navigate_parent), ("<Right>", self.navigate_inside),
                             ("<Alt-Left>", lambda: self.navigate_sibling_body(-1)),
                             ("<Alt-Right>", lambda: self.navigate_sibling_body(1)),
                             ("<Alt-Up>", lambda: self.move_block(-1)), ("<Alt-Down>", lambda: self.move_block(1))):
            self.diagram.canvas.bind(key, lambda event, command=command: command() or "break")
        self.diagram.canvas.bind("<Button-3>", self.context_menu)
        self.diagram.canvas.bind("<Button-2>", self.context_menu)
        for widget in (self, self.surface,
                       self.zoom_bar, self.zoom_label, self.zoom_slider, self.monochrome_button):
            self._bind_history(widget)
        self.interaction = DiagramInteraction(self)
        self._refresh()

    def _set_monochrome(self):
        self.diagram.monochrome = self.monochrome.get()
        self.diagram.draw()

    def export_graphic(self, kind):
        if not any(n.get("enabled",True) for n in self.document["body"]):
            return
        try:
            scene = snapshot(self.diagram, monochrome=False)
            width, height = scene[:2]
            dialog = ImageSizeDialog(self, width, height, kind=kind.upper())
            if dialog.result is None:
                return
            size = dialog.result if kind in ("png", "webp") else None
            source = Path(self._filename) if self._filename else None
            stem = (diagram_stem(source) if source else "") or self.default_stem
            filename = filedialog.asksaveasfilename(parent=self, title=tr('Export {format}').format(format=kind.upper()),
                       initialdir=str(source.parent) if source else None, initialfile=stem+"."+kind,
                       defaultextension="."+kind, filetypes=[(tr('{format} files').format(format=kind.upper()), "*."+kind)])
            if not filename:
                return
            if is_diagram_path(filename) or (source and Path(filename).resolve()==source.resolve()):
                raise ValueError(tr('Please choose a separate image file.'))
            export_image(filename, scene, size, kind=kind, options=dialog.options)
        except (OSError, ValueError, ImportError) as exc:
            messagebox.showerror(tr('Export image'), str(exc), parent=self)

    def _bind_history(self, widget):
        for sequence in ("<<SelectAll>>", "<Control-a>", "<Command-a>"):
            widget.bind(sequence,lambda event:self.select_all())
        def dispatch(command):
            def handler(event):
                command()
                return "break"
            return handler
        for sequence in ("<<Undo>>", "<Control-z>", "<Command-z>"):
            widget.bind(sequence, dispatch(self.undo))
        for sequence in ("<<Redo>>", "<Control-y>", "<Command-y>", "<Control-Shift-Z>", "<Command-Shift-Z>"):
            widget.bind(sequence, dispatch(self.redo))
        for name, letter, command in (("Cut", "x", self.cut_block), ("Copy", "c", self.copy_block), ("Paste", "v", self.paste_block)):
            for sequence in (f"<<{name}>>", f"<Control-{letter}>", f"<Command-{letter}>"):
                widget.bind(sequence, dispatch(command))

    def select_all(self):
        count = len(self.document['body'])
        self.select_region(Selection(index=0,end_index=count-1 if count>1 else None) if count else Selection())
        self.diagram.canvas.focus_set()
        return "break"

    def copy_block(self):
        nodes = selected_nodes(self.document, self.selection)
        if not nodes:
            return False
        try:
            self.clipboard_clear()
            self.clipboard_append(BLOCK_CLIPBOARD_PREFIX + json.dumps(nodes[0] if len(nodes)==1 else nodes, ensure_ascii=False))
            return True
        except tk.TclError:
            return False

    def cut_block(self):
        if self.copy_block():
            before = self._snapshot()
            self.selection = delete_node(self.document, self.selection)
            self._record(before)

    def _clipboard_insertion(self):
        text = self.clipboard_get()
        if not text.startswith(BLOCK_CLIPBOARD_PREFIX) or len(text) > 64_000_000:
            raise ValueError(tr('No structogram blocks in the clipboard.'))
        node = json.loads(text[len(BLOCK_CLIPBOARD_PREFIX):])
        nodes = node if isinstance(node, list) else [node]
        if not nodes:
            raise ValueError(tr('The clipboard is empty.'))
        candidate = copy.deepcopy(self.document)
        selection = insert_copies(candidate, self.selection, nodes)
        return candidate, selection

    def paste_block(self):
        try:
            candidate, selection = self._clipboard_insertion()
        except (tk.TclError, ValueError, RecursionError):
            self.bell()
            return
        before = self._snapshot()
        self.document = candidate
        self.selection = selection
        self._record(before)
        self.diagram.reveal_selection()

    def select_start(self):
        self.select_region(Selection(self.selection.path, at_start=True))
        self.diagram.reveal_selection()

    def navigate(self, delta):
        body = body_at(self.document, self.selection.path)
        if body:
            index = (0 if delta > 0 else len(body)-1) if self.selection.index is None else max(0, min(len(body)-1, self.selection.index+delta))
            self.select_region(Selection(self.selection.path, index))
            self.diagram.reveal_selection()

    def navigate_parent(self):
        self.select_region(parent_selection(self.selection) if len(self.selection.path) > 1 else Selection())
        self.diagram.reveal_selection()

    def navigate_inside(self):
        node = selected_node(self.document, self.selection)
        if node is None:
            self.navigate(1)
        elif child_bodies(node):
            relative, _, _ = child_bodies(node)[0]
            self.select_region(Selection(self.selection.path+(self.selection.index,)+relative))
            self.diagram.reveal_selection()

    def navigate_sibling_body(self, delta):
        if len(self.selection.path) == 1:
            return
        parent = parent_selection(self.selection)
        node = selected_node(self.document, parent)
        prefix = parent.path+(parent.index,)
        bodies = child_bodies(node)
        current = self.selection.path[len(prefix):]
        index = next((i for i, (relative, _, _) in enumerate(bodies) if relative == current), 0)
        target = bodies[(index+delta) % len(bodies)][0]
        self.select_region(Selection(prefix+target))
        self.diagram.reveal_selection()

    def set_blocks_enabled(self, enabled):
        from .model import set_selected_enabled
        before = self._snapshot()
        set_selected_enabled(self.document, self.selection, enabled)
        self._record(before)

    def create_context_menu(self):
        if hasattr(self, "_context_menu"):
            self._context_menu.destroy()
        menu = self._context_menu = tk.Menu(self, tearoff=False)
        selected = self.selection.index is not None
        nodes = selected_nodes(self.document, self.selection)
        body = body_at(self.document, self.selection.path)
        last = self.selection.end_index if self.selection.end_index is not None else self.selection.index

        def command(target, label, handler, enabled=True, role=None):
            options = {"image": menu_icon(get_workbench(), role), "compound": "left"} if role else {}
            target.add_command(label=label, command=handler, state="normal" if enabled else "disabled", **options)

        insert_menu = tk.Menu(menu, tearoff=False)
        for kind, label in self.palette.entries():
            command(insert_menu, label, lambda kind=kind: self.insert_block(kind))
        menu.add_cascade(label=tr('Insert block'), menu=insert_menu, image=menu_icon(get_workbench(), "edit.add"), compound="left")
        arrange = tk.Menu(menu, tearoff=False)
        command(arrange, tr('At the beginning of this section'), self.select_start)
        command(arrange, tr('Move up'), lambda: self.move_block(-1), selected and self.selection.index>0)
        command(arrange, tr('Move down'), lambda: self.move_block(1), selected and last<len(body)-1)
        menu.add_cascade(label=tr('Arrange'), menu=arrange)
        command(menu, tr('Activate'), lambda: self.set_blocks_enabled(True),
                any(not node.get('enabled',True) for node in nodes))
        command(menu, tr('Deactivate'), lambda: self.set_blocks_enabled(False),
                any(node.get('enabled',True) for node in nodes))
        menu.add_separator()
        command(menu, tr('Edit'), self.edit_block, len(nodes)==1, role="edit.rename")
        command(menu, tr('Delete'), self.delete_block, selected, role="edit.delete")
        command(menu, tr('Cut'), self.cut_block, selected, role="edit.cut")
        command(menu, tr('Copy'), self.copy_block, selected, role="edit.copy")
        try:
            self._clipboard_insertion()
        except (tk.TclError, ValueError, RecursionError):
            pass
        else:
            command(menu, tr('Paste'), self.paste_block, role="edit.paste")
        menu.add_separator()
        command(menu, tr('Code from structogram'), self.export_python, any(n.get("enabled",True) for n in self.document["body"]), role="export.python")
        from .model import selection_enabled
        command(menu, tr('Code from selection'), lambda: self.export_python(True), selection_enabled(self.document,self.selection) and any(n.get('enabled',True) for n in (nodes if selected else body)), role="export.python_selection")
        retina_icons.decorate_menu(menu)
        return menu

    def export_python(self, only_selection=False):
        try:
            content = generate_python(self.document, self.selection if only_selection else None)
        except (ValueError, RecursionError) as exc:
            messagebox.showerror(tr('Generate Python code'), str(exc), parent=self)
            return
        source = Path(self._filename) if self._filename else None
        stem = (diagram_stem(source) if source else "") or self.default_stem
        filename = filedialog.asksaveasfilename(parent=self, title=tr('Save Python code'),
                    initialdir=str(source.parent) if source else None,
                    initialfile=stem+".py",
                    defaultextension=".py", filetypes=[(tr('Python files'), "*.py")])
        if not filename:
            return
        if is_diagram_path(filename) or (source and Path(filename).resolve() == source.resolve()):
            messagebox.showerror(tr('Save Python code'), tr('Please choose a separate Python file.'), parent=self)
            return
        try:
            write_text(filename, content)
        except OSError as exc:
            messagebox.showerror(tr('Save Python code'), str(exc), parent=self)
            return
        try:
            exported = get_workbench().get_editor_notebook().show_file(filename)
            if exported is not None:
                exported.check_for_external_changes()
        except (OSError, tk.TclError) as exc:
            messagebox.showerror(tr('Open Python file'),
                                 tr('The file was saved but could not be opened:\n{p0}').format(p0=exc), parent=self)

    def context_menu(self, event):
        canvas = self.diagram.canvas
        selection = self.diagram.region_at(canvas.canvasx(event.x), canvas.canvasy(event.y))
        canvas.focus_set()
        if selection is None or selection.path != self.selection.path or selection.index is None or not (
                self.selection.index is not None and self.selection.index <= selection.index <= (
                    self.selection.end_index if self.selection.end_index is not None else self.selection.index)):
            self.select_region(selection if selection is not None else Selection())
        menu = self.create_context_menu()
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()
        return "break"

    def _snapshot(self):
        return copy.deepcopy(self.document), self.selection

    def _record(self, before):
        self._selection_anchor = Selection(self.selection.path, self.selection.index) if self.selection.index is not None else None
        if before[0] != self.document:
            self.undo_stack.append(before)
            self.undo_stack = self.undo_stack[-100:]
            self.redo_stack.clear()
        self._refresh()

    def select_region(self, selection):
        self.selection = selection
        self._selection_anchor = Selection(selection.path, selection.index) if selection.index is not None else None
        self._refresh()

    def extend_selection(self, selection):
        anchor = self._selection_anchor
        if anchor is None or selection.index is None or anchor.path != selection.path:
            self.select_region(selection)
            return
        low, high = sorted((anchor.index, selection.index))
        self.selection = Selection(selection.path, low, end_index=high if high != low else None)
        self._refresh()

    def drop_blocks(self, target, kind=None):
        before = self._snapshot()
        try:
            self.selection = (insert_node(self.document, target, kind) if kind is not None
                              else move_selection(self.document, self.selection, target))
        except ValueError as exc:
            messagebox.showerror(tr('Move blocks'), str(exc), parent=self)
            return
        self._selection_anchor = Selection(self.selection.path, self.selection.index)
        self._record(before)
        self.diagram.reveal_selection()

    def insert_block(self, kind):
        before = self._snapshot()
        try:
            self.selection = insert_node(self.document, self.selection, kind)
        except ValueError as exc:
            messagebox.showerror(tr('Insert block'), str(exc), parent=self)
            return
        self._record(before)
        self.diagram.reveal_selection()

    def edit_block(self):
        if len(selected_nodes(self.document, self.selection)) > 1:
            return
        node = selected_node(self.document, self.selection)
        if node is None:
            return
        if node['kind']=='try':
            from .exception_dialog import ExceptionDialog
            dialog=ExceptionDialog(self,node)
        elif node["kind"] in IF_KINDS:
            dialog = IfDialog(self, node)
        elif node["kind"] == "switch":
            dialog = CaseDialog(self, node)
        else:
            dialog = LoopFieldsDialog(self, node) if node["kind"] in LOOP_FIELDS else BlockTextDialog(self, node)
        if dialog.result is not None:
            before = self._snapshot()
            if node["kind"] in IF_KINDS:
                try:
                    set_if_variant(node, dialog.result["with_else"])
                except ValueError as exc:
                    messagebox.showerror(tr('Change selection'), str(exc), parent=self)
                    return
                changes = {"text": dialog.result["text"]}
            else:
                changes = dialog.result if node["kind"] in LOOP_FIELDS or node["kind"] in ("switch","try") else {"text": dialog.result}
            node.update(changes)
            self._record(before)

    def delete_block(self):
        node = selected_node(self.document, self.selection)
        if node is None:
            return
        nodes = selected_nodes(self.document, self.selection)
        has_children = any(body for node in nodes for _, body, _ in child_bodies(node))
        if has_children and not messagebox.askyesno(
            tr('Delete block'), tr('Delete the selection and all blocks it contains?'), parent=self
        ):
            return
        before = self._snapshot()
        self.selection = delete_node(self.document, self.selection)
        self._record(before)

    def move_block(self, delta):
        before = self._snapshot()
        self.selection = move_node(self.document, self.selection, delta)
        self._record(before)
        self.diagram.reveal_selection()

    def undo(self):
        self._history(self.undo_stack, self.redo_stack)

    def redo(self):
        self._history(self.redo_stack, self.undo_stack)

    def _history(self, source, target):
        if not source:
            return
        target.append(self._snapshot())
        self.document, self.selection = source.pop()
        self._selection_anchor = Selection(self.selection.path, self.selection.index) if self.selection.index is not None else None
        self._refresh()
        self.diagram.reveal_selection()

    def _refresh(self):
        get_workbench()._update_toolbar()
        self.diagram.show(self.document, self.selection)
        self.update_title()
        get_workbench().update_title()

