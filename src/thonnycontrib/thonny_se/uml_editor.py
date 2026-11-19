# SPDX-FileCopyrightText: 2026 Sebastian Ladhoff
# SPDX-License-Identifier: GPL-3.0-only
# See LICENSE in the project root for the full license text.

"""UML-Dokumenttab: Klassen direkt auf der Zeichenfläche bearbeiten."""
from .i18n import tr
import copy
import json
from uuid import uuid4
import tkinter as tk
from pathlib import Path
from tkinter import ttk, filedialog, messagebox
from .dialogs import ImageSizeDialog, RelationshipDialog
from .imageexport import export_image
from .storage import diagram_stem, is_diagram_path
from thonny import get_workbench
from .graphical_document import GraphicalDocument
from . import uml_model, uml_storage
from .uml_canvas import UmlCanvas


class UmlEditor(GraphicalDocument):
    document_model = uml_model
    file_codec = uml_storage
    document_label = tr('UML diagram')
    default_stem = "diagramm"
    untitled_label = tr('New UML diagram')

    def __init__(self, master):
        super().__init__(master)
        self.execution_hint_seen = False
        self.execution_hint_visible = False
        self.surface = ttk.Frame(self, padding=8)
        self.surface.home_widget = self
        self.maximizable_widget = self.surface
        self.surface.grid(row=0, column=0, sticky="nsew")
        self.surface.rowconfigure(0, weight=1)
        self.surface.columnconfigure(0, weight=1)
        self.diagram = UmlCanvas(self.surface, self)
        self.diagram.grid(row=0, column=0, sticky="nsew")
        self._bind_clipboard()
        self.zoom_bar = ttk.Frame(self.surface)
        self.zoom_bar.grid(row=1, column=0, sticky="e", pady=(6, 0))
        self.monochrome = tk.BooleanVar(self,value=False)
        style=ttk.Style(self)
        background=style.lookup('TFrame','background') or '#ececec'
        style.configure('SE.Monochrome.TCheckbutton',background=background)
        style.map('SE.Monochrome.TCheckbutton',background=[('active',background),('!active',background)])
        self.monochrome_button=ttk.Checkbutton(self.zoom_bar,text=tr('Monochrome'),variable=self.monochrome,
            style='SE.Monochrome.TCheckbutton',command=self._set_monochrome)
        self.monochrome_button.pack(side='left',padx=(0,28))
        self._build_zoom_controls()
        from .diagram_preferences import UML_GRID
        self.grid_choices = {'none': tr('No grid'), 'visual': tr('Simple grid'), 'magnetic': tr('Magnetic grid')}
        self.grid_value = tk.StringVar(self, value=self.grid_choices[self.diagram.grid_mode])
        self.grid_picker = ttk.Combobox(self.zoom_bar, textvariable=self.grid_value,
            values=tuple(self.grid_choices.values()), state='readonly', width=19, style='SE.TCombobox')
        self.grid_picker.pack(side='left', before=self.monochrome_button, padx=(0, 16))
        self.grid_picker.bind('<<ComboboxSelected>>', self._grid_selected)
        self._refresh()

        from .uml_source_status import SourceStatus
        self.source_status = SourceStatus(self)

    def selected_class_ids(self):
        ids = {c['id'] for c in self.document['classes']}
        multi = getattr(self,'_multi_selection',set())
        return (multi & ids) if self.selection in multi else ({self.selection} & ids)

    def select_all(self):
        if not self.diagram.finish_edit():return "break"
        self._multi_selection = {c['id'] for c in self.document['classes']}
        self.selection = self.document['classes'][0]['id'] if self.document['classes'] else None
        self.diagram.draw()
        self.diagram.canvas.focus_set()
        return "break"

    def _bind_clipboard(self):
        # Canvas has no native text undo; dispatch directly to diagram history.
        for action, sequences in (
                (self.undo, ("<<Undo>>", "<Control-z>", "<Command-z>")),
                (self.redo, ("<<Redo>>", "<Control-y>", "<Command-y>",
                             "<Control-Shift-Z>", "<Command-Shift-Z>"))):
            for sequence in sequences:
                self.diagram.canvas.bind(sequence, lambda event, action=action: (action(), "break")[1])
        for sequence in ("<<SelectAll>>","<Control-a>","<Command-a>"):
            self.diagram.canvas.bind(sequence,lambda event:self.select_all())
        for name,letter,action in (("Copy","c",self.copy_class),("Cut","x",self.cut_class),("Paste","v",self.paste_class)):
            for sequence in (f"<<{name}>>",f"<Control-{letter}>",f"<Command-{letter}>"):
                self.diagram.canvas.bind(sequence,lambda event,action=action: (action(),"break")[1])

    def copy_class(self):
        from .uml_clipboard import PREFIX, class_packet
        if not self.diagram.finish_edit():
            return False
        try:
            packet = class_packet(self.document,self.selected_class_ids())
            self.clipboard_clear()
            self.clipboard_append(PREFIX+json.dumps(packet,ensure_ascii=False))
            return True
        except (tk.TclError,ValueError):
            return False

    def cut_class(self):
        if self.copy_class():
            self.delete_class()

    def _clipboard_insertion(self,position=None):
        from .uml_clipboard import PREFIX, insert_packet
        text = self.clipboard_get()
        if not text.startswith(PREFIX) or len(text)>64_000_000:
            raise ValueError(tr('No UML class in the clipboard.'))
        packet = json.loads(text[len(PREFIX):])
        if not isinstance(packet,dict):
            raise ValueError(tr('No UML class in the clipboard.'))
        return insert_packet(self.document,packet,position)

    def paste_class(self,position=None):
        if not self.diagram.finish_edit():
            return
        try:
            candidate,cid = self._clipboard_insertion(position)
        except (tk.TclError,ValueError,RecursionError,TypeError,KeyError):
            self.bell()
            return
        before = self._snapshot()
        self._multi_selection = {c["id"] for c in candidate["classes"]} - {c["id"] for c in self.document["classes"]}
        self.document,self.selection = candidate,cid
        self._record(before)

    def _set_monochrome(self):
        self.diagram.monochrome=self.monochrome.get()
        self.diagram.draw()

    def _grid_selected(self, event=None):
        from .diagram_preferences import UML_GRID
        from thonny import get_workbench
        mode = next(key for key, value in self.grid_choices.items() if value == self.grid_value.get())
        get_workbench().set_option(UML_GRID, mode)
        self.diagram.grid_mode = mode
        self.diagram._draw_grid()

    def export_graphic(self, kind):
        if not self.document["classes"] and not self.document["comments"]:
            return
        try:
            if not self.diagram.finish_edit():
                return
            scene = self.diagram.snapshot()
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

    def card(self, cid):
        return next(c for c in self.document["classes"] if c["id"] == cid)

    def go_to_code(self, cid, section='name', row_id=None):
        from .integration import read_python_source
        from .uml_navigation import code_location
        card = self.card(cid)
        if not card.get('source'):
            return
        try:
            path = card['source']['path']
            line,column = code_location(read_python_source(path),card,section,row_id)
            target = self.notebook.show_file(path)
            if target is not None:
                target.select_line(line,column)
                target.get_text_widget().focus_set()
        except (OSError, ValueError, RecursionError) as exc:
            messagebox.showinfo(tr('Go to code'),str(exc),parent=self)

    def new_class(self, x=40, y=40):
        if not self.diagram.finish_edit() or len(self.document["classes"]) >= 200:
            return
        before = self._snapshot()
        names = {c["name"] for c in self.document["classes"]}
        name, index = tr('Class'), 2
        while name in names:
            name, index = tr('Class')+str(index), index+1
        x,y = self.diagram.snap_position(max(8,x),max(8,y))
        card = uml_model.new_class(name,x,y)
        self.document["classes"].append(card)
        self.selection = card["id"]
        self.diagram.draw()
        self.diagram.begin_edit(card["id"], before=before)
        self.update_title()
        return card

    def add_imported_classes(self, cards):
        bottom = max((bounds[3] for bounds in self.diagram.cards.values()), default=0)
        self.diagram.arrange_cards(cards, y=bottom + 24)
        document = {**self.document, "classes": self.document["classes"] + cards}
        if 'removed_classes' in document:
            from .uml_batch import file_key
            imported = {(file_key(card['source']['path']), card['source']['class']) for card in cards if 'source' in card}
            document['removed_classes'] = [card for card in document['removed_classes']
                if (file_key(card['source']['path']), card['source']['class']) not in imported]
        uml_model.validate(document)
        before = self._snapshot()
        self.document = document
        self.selection = cards[0]["id"]
        self._record(before)

        canvas = self.diagram.canvas
        y = cards[0]["y"] * self.diagram.zoom
        if y >= canvas.canvasy(canvas.winfo_height()) or y < canvas.canvasy(0):
            region_height = float(canvas.cget("scrollregion").split()[3])
            canvas.yview_moveto(max(0, y - 16) / region_height)
        canvas.xview_moveto(0)

    def export_python_code(self, cid=None):
        from .storage import write_new_text
        from .uml_codegen import generate_diagram

        if not self.diagram.finish_edit():
            return
        from .uml_relationships import synchronized_inheritance
        try:
            effective_document = synchronized_inheritance(self.document)
        except ValueError as exc:
            messagebox.showerror(tr('Code from diagram'), str(exc), parent=self)
            return
        cards = effective_document["classes"]
        if not cards:
            return
        label = tr('Code from diagram') if cid is None else tr('Code from class')
        source = Path(self.get_filename()) if self.get_filename() else None
        try:
            if cid is None:
                code = generate_diagram(cards)
                stem = diagram_stem(source) if source else self.default_stem
            else:
                card = next(card for card in cards if card["id"] == cid)
                code = generate_diagram([card])
                stem = card["name"]
            filename = filedialog.asksaveasfilename(
                parent=self, title=label, initialdir=str(source.parent) if source else None,
                initialfile=stem + ".py", defaultextension=".py",
                filetypes=[(tr('Python files'), "*.py")],
            )
            if not filename:
                return
            if Path(filename).suffix.lower() != ".py":
                raise ValueError(tr('Please choose a filename ending in .py.'))
            if self.notebook.get_editor(filename) is not None:
                raise ValueError(tr('The target file is already open in Thonny.'))
            write_new_text(filename, code)
        except FileExistsError:
            messagebox.showinfo(label, tr('This file already exists. Please choose a new filename.'), parent=self)
            return
        except (OSError, ValueError, RecursionError) as exc:
            messagebox.showerror(label, str(exc), parent=self)
            return

        try:
            self.notebook.show_file(filename)
        except (OSError, tk.TclError) as exc:
            messagebox.showerror(label, tr('The file was saved but could not be opened.\n{p0}').format(p0=exc), parent=self)
        return filename

    def persist_class(self, cid):
        if not self.diagram.finish_edit():
            return
        card = self.card(cid)
        source = card.get('source')
        if source is None:
            filename = self.export_python_code(cid)
            if not filename:
                return
            from .uml_source import attach_source
            from .uml_python_semantics import generated_header
            before = self._snapshot()
            card['header'] = generated_header(card)
            attach_source(card, filename, card['header']['name'])
            self._record(before)
        elif self.source_status.states.get(cid) == 'unsaved':
            target = self.notebook.show_file(source['path'])
            if target is not None:
                target.save_file()
        elif self.source_status.states.get(cid) == 'missing':
            self.update_from_python(cid, reassign=True)
        else:
            self.update_python_code(cid)
        self.source_status.schedule()

    def run_diagram(self):
        get_workbench()._thonny_se_objects.session.run_diagram(self)

    def _record(self, before):
        from .uml_runtime import diagram_fingerprint
        if (self.document['classes'] and not self.execution_hint_seen
                and diagram_fingerprint(before[0]) != diagram_fingerprint(self.document)):
            self.execution_hint_seen = True
            self.execution_hint_visible = True
        super()._record(before)

    def instantiate_class(self, cid):
        get_workbench()._thonny_se_objects.session.instantiate(self, cid)

    def edit_class_header(self, cid):
        self.diagram.begin_edit(cid)

    def class_header_settings(self, cid):
        from .integration import read_python_source
        from .uml_codegen import header_data
        from .uml_import import linked_class_node, parse_tree

        from .uml_relationships import synchronized_inheritance
        card = next(card for card in synchronized_inheritance(self.document)["classes"] if card["id"] == cid)
        if "header" in card:
            return card["header"], None
        source = card.get("source")
        if source:
            try:
                tree = parse_tree(read_python_source(source["path"]))
                baseline = header_data(linked_class_node(tree, source["class"]))
                return baseline, baseline
            except (ValueError, RecursionError, OSError):
                pass
        return {"name": card["name"], "bases": ""}, None

    def changed_class_header(self, cid, name, header, baseline, bases, kind):
        import ast
        from .uml_codegen import class_header, header_data
        from .uml_relationships import updated_inheritance, synchronized_inheritance, renamed_class

        card = self.card(cid)
        candidate = renamed_class(synchronized_inheritance(self.document), cid, name)
        updated = next(item for item in candidate["classes"] if item["id"] == cid)
        updated["name"] = uml_model.class_name(name)
        if (bases, kind) == (header["bases"], card.get("class_kind", "class")):
            return candidate
        updated_header = header
        if bases != header["bases"]:
            python_name = header["name"] if "source" in card else updated["name"]
            declaration = class_header({"name": python_name, "bases": bases})
            updated_header = header_data(ast.parse(declaration + "\n    pass").body[0])
        relations = updated_inheritance(candidate, cid, header['bases'], updated_header['bases'])
        if bases != header["bases"]:
            if baseline and "header" not in updated["source"]:
                updated["source"]["header"] = baseline
            updated["header"] = updated_header
        if kind == "class":
            updated.pop("class_kind", None)
            if card.get('class_kind') in ('abstract','interface'):
                for row in updated['methods']:
                    row['abstract'] = False
        else:
            updated["class_kind"] = kind
        candidate["relationships"] = relations
        return synchronized_inheritance(candidate)

    def link_diagram_source(self):
        from .uml_batch_actions import relink
        relink(self)

    def update_classes_from_code(self):
        from .uml_batch import FROM_CODE
        from .uml_batch_actions import update
        update(self, FROM_CODE)

    def update_code_from_classes(self):
        from .uml_batch import TO_CODE
        from .uml_batch_actions import update
        update(self, TO_CODE)

    def update_python_code(self, cid):
        from .uml_batch import TO_CODE
        from .uml_batch_actions import update
        update(self, TO_CODE, cids={cid})

    def update_from_python(self, cid, *, reassign=False):
        if not reassign:
            from .uml_batch import FROM_CODE
            from .uml_batch_actions import update
            update(self, FROM_CODE, cids={cid})
            return
        from thonny.ui_utils import askopenfilename
        from .integration import read_python_source
        from .uml_import import parse_linked_class
        from .uml_source import SECTIONS, plan_update, resolve_update
        from .uml_update_dialog import UPDATE_CLASS_LABEL, UmlUpdateDialog

        if not self.diagram.finish_edit():
            return
        card = self.card(cid)
        source = card.get("source")
        path = source["path"] if source else self.get_filename()
        label = UPDATE_CLASS_LABEL
        if reassign:
            path = askopenfilename(
                parent=self, title=tr('Relink Python source file') if source else tr('Link Python source file'),
                initialdir=str(Path(path).parent) if path else None, filetypes=[(tr('Python files'), ".py")],
            )
            if not path:
                return
        elif source is None:
            return
        first_link = source is None
        if first_link:
            name = card.get("header", {}).get("name", card["name"])
            header = card.get("header", {"name": name, "bases": ""})
            source = {"path": "", "class": name, "header": header,
                      "baseline": {section: [] for section in SECTIONS}}
            card = {**card, "source": source}
        try:
            incoming = parse_linked_class(read_python_source(path), path, source["class"])
            baseline, plan = plan_update(card, incoming, first_link=first_link)
            if baseline == source:
                messagebox.showinfo(label, tr('The Python class definition has not changed since the last import.'), parent=self)
                return
            current_header = card.get("header")
            if first_link and current_header is None:
                current_header = {"name": source["class"], "bases": ""}
            previous_header = source.get("header")
            python_header = incoming["header"]
            previous_kind = source.get('class_kind','class')
            python_kind = baseline.get('class_kind','class')
            current_kind = card.get('class_kind','class')
            header_change = ((python_header,python_kind) != (previous_header,previous_kind)
                             and (python_header,python_kind) != (current_header,current_kind))
            header_conflict = current_header is not None and (current_header,current_kind) != (previous_header,previous_kind) and not first_link
            dialog = UmlUpdateDialog(
                self, card, baseline, plan,
                header=({**current_header, 'class_kind':current_kind} if current_header else None,
                        {**python_header,'class_kind':python_kind},header_conflict) if header_change else None,
                reassign=reassign, first_link=first_link,
            )
            if dialog.result is None:
                return
            updated = resolve_update(card, baseline, plan, dialog.result)
            document = {**self.document, "classes": [
                updated if item["id"] == cid else item for item in self.document["classes"]
            ]}
            if updated.get('header') != card.get('header'):
                from .uml_relationships import updated_inheritance
                old_bases = card.get('header', source.get('header', {})).get('bases', '')
                new_bases = updated.get('header', {}).get('bases', '')
                document['relationships'] = updated_inheritance(document, cid, old_bases, new_bases)
            uml_model.validate(document)
        except (ValueError, RecursionError) as exc:
            messagebox.showinfo(label, str(exc), parent=self)
            return
        before = self._snapshot()
        self.document = document
        self.selection = cid
        self._record(before)

    def validate_text(self, cid, section, text):
        if section == "name":
            name = uml_model.class_name(text)
            if any(c["name"] == name and c["id"] != cid for c in self.document["classes"]):
                raise ValueError(tr('This class name already exists.'))
        elif len(text) > 500 or "\n" in text or "\r" in text:
            raise ValueError(tr('Please enter a single line of at most 500 characters.'))
        elif self.diagram.editing[2] is None and text and sum(len(c[s]) for c in self.document["classes"] for s in ("attributes", "methods")) >= 1000:
            raise ValueError(tr('The diagram already contains 1000 entries.'))

    def edit_relationship(self, start, end, *, relation=None):
        from .uml_relationships import new_relationship

        relation = new_relationship(start, end) if relation is None else dict(relation)

        def apply_changes(result):
            from .uml_relationships import synchronized_inheritance

            updated = {**relation, **result}
            relations = self.document["relationships"]
            exists = any(item["id"] == relation["id"] for item in relations)
            proposed = ([updated if item["id"] == relation["id"] else item for item in relations]
                        if exists else [*relations, updated])
            candidate = synchronized_inheritance(self.document, proposed)
            if candidate == self.document:
                return
            before = self._snapshot()
            self.document = candidate
            self.selection = relation["id"]
            self._record(before)

        RelationshipDialog(self, self.card(start)["name"], self.card(end)["name"], relation,
                           on_apply=apply_changes)

    def detect_relationships(self):
        from .uml_relationships import infer_relationships

        if not self.diagram.finish_edit():
            return
        label = tr('Detect relationships automatically')
        from .integration import read_python_source
        inferred = infer_relationships(self.document, read_source=read_python_source)
        if not inferred:
            messagebox.showinfo(label, tr('No new unambiguous relationships found from base classes or attribute types.'), parent=self)
            return
        candidate = {**self.document, "relationships": self.document["relationships"] + inferred}
        try:
            uml_model.validate(candidate)
        except ValueError as exc:
            messagebox.showerror(label, str(exc), parent=self)
            return
        before = self._snapshot()
        self.document = candidate
        self._record(before)
        messagebox.showinfo(label, tr('Relationships added: {p0}').format(p0=len(inferred)), parent=self)

    def edit_comment(self, x=0, y=0, *, target=None, note=None):
        new = note is None
        if new:
            if len(self.document["comments"]) >= 200:
                return
            note = dict(id=uuid4().hex, x=min(1_000_000, max(8, x)),
                        y=min(1_000_000, max(8, y)), text="", target=target)
        self.diagram.begin_comment(note, new=new)

    def delete_selection(self):
        note = next((item for item in self.document["comments"] if item["id"] == self.selection), None)
        if note is not None:
            before = self._snapshot()
            self.document["comments"].remove(note)
            self.selection = None
            self._record(before)
            return
        relation = next((item for item in self.document["relationships"] if item["id"] == self.selection), None)
        if relation is None:
            self.delete_class()
            return
        from .uml_relationships import synchronized_inheritance
        candidate = synchronized_inheritance(self.document,
            [item for item in self.document['relationships'] if item['id'] != relation['id']])
        before = self._snapshot()
        self.document = candidate
        self.selection = None
        self._record(before)

    def delete_class(self):
        if self.diagram.finish_edit() and self.selection:
            selected = self.selected_class_ids()
            if not selected:return
            before = self._snapshot()
            from .uml_relationships import synchronized_inheritance
            remaining = [relation for relation in self.document["relationships"]
                         if not selected.intersection((relation["start"], relation["end"]))]
            self.document = synchronized_inheritance(self.document, remaining)
            for deleted in self.document["classes"]:
                if deleted['id'] in selected and 'source' in deleted:
                    self.document.setdefault('removed_classes',[]).append(copy.deepcopy(deleted))
            self.document['classes'] = [c for c in self.document['classes'] if c['id'] not in selected]
            for note in self.document['comments']:
                if note['target'] in selected:note['target']=None
            self._multi_selection = set()
            self.selection = None
            self._record(before)

    def is_modified(self):
        return super().is_modified() or (hasattr(self, "diagram") and self.diagram.pending())

    def is_text_editing(self, focus):
        return focus is not None and hasattr(self, "diagram") and (
            focus is self.diagram.comment_input
            or (self.diagram.input is not None and str(focus).startswith(str(self.diagram.input_frame)+"."))
            or (self.diagram.member_editor is not None and
            str(focus).startswith(str(self.diagram.member_editor)+".")))

    def _before_replace(self):
        self.diagram.finish_edit(cancel=True)
        self.diagram.relationship_origin = None

    def _prepare_save(self):
        return self.diagram.finish_edit()

    def undo(self):
        if self.diagram.finish_edit():
            self._multi_selection = set()
            super().undo()

    def redo(self):
        if self.diagram.finish_edit():
            self._multi_selection = set()
            super().redo()

    def _refresh(self):
        if hasattr(self, "source_status"):
            self.source_status.schedule()
        controller = getattr(get_workbench(), '_thonny_se_objects', None)
        if controller is not None:
            controller.session.watch_diagram(self)
        if hasattr(self, "diagram"):
            self.diagram.draw()
        self.update_title()
        get_workbench().update_title()
        get_workbench()._update_toolbar()
