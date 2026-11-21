# SPDX-FileCopyrightText: 2026 Sebastian Ladhoff
# SPDX-License-Identifier: GPL-3.0-only
# See LICENSE in the project root for the full license text.

"""Eingabedialoge für Bausteine; Änderungen erst nach Bestätigung übernehmen."""
from .i18n import tr
import copy
import tkinter as tk
from tkinter import font as tkfont, messagebox, simpledialog, ttk

from .model import LOOP_FIELDS
from .export_preferences import ExportOptions, load_options, save_options
from .ui_style import FIELD_BORDER, SELECT
from .diagram_preferences import relationship_count_label


class EditDialog(simpledialog.Dialog):
    """Gemeinsamer Aufbau mit einer ttk-Oberfläche und eindeutigen Aktionen."""
    def body(self, master):
        style = ttk.Style(self)
        background = style.lookup("TFrame", "background") or self.cget("background")
        foreground = style.lookup("TLabel", "foreground") or "#202020"
        # Nur Abstand und einheitliche Flächen anpassen; Thonnys Theme behalten.
        style.configure("SE.TFrame", background=background)
        style.configure("SE.TLabel", background=background, foreground=foreground)
        style.configure("SE.TRadiobutton", background=background, padding=(0, 6))
        style.map("SE.TRadiobutton", background=[("active", background), ("!active", background)])
        style.configure("SE.TButton", padding=(10, 6))
        style.configure("SE.TEntry", padding=4)
        style.configure("SE.TCombobox", padding=4)
        style.configure("SE.Treeview", rowheight=26)
        style.configure("SE.Treeview.Heading", padding=(8, 4))
        self.configure(background=background)
        master.configure(background=background)
        content = ttk.Frame(master, padding=(16, 12), style="SE.TFrame")
        content.pack(fill="both", expand=True)
        return self.build_body(content)

    def _action_button(self, parent, column, text, command, *, gap=0):
        style = "SE.TButton"
        button = ttk.Button(parent, style=style, text=text, command=command)
        face = ttk.Style(self).lookup(style, "font") or "TkDefaultFont"
        label_width = tkfont.Font(root=self, font=face).measure(text)
        # Native themes can report a fixed button width, even for longer labels.
        parent.columnconfigure(column, minsize=label_width+36+gap)
        button.grid(row=0, column=column, sticky="ew", padx=(0, gap))
        return button

    def buttonbox(self):
        actions = ttk.Frame(self, padding=(20, 4, 20, 16), style="SE.TFrame")
        actions.pack(fill="x")
        actions.grid_anchor("e")
        self._action_button(actions, 0, tr('Cancel'), self.cancel, gap=8)
        self.apply_button = self._action_button(actions, 1, tr('OK'), self.ok)
        self.bind("<Return>", self.ok)
        self.bind("<KP_Enter>", self.ok)
        self.bind("<Escape>", self.cancel)


class BlockTextDialog(EditDialog):
    def __init__(self, parent, node):
        self.node = node
        self.result = None
        super().__init__(parent, tr('Edit function call') if node["kind"] == "call" else tr('Edit statement') if node["kind"] == "statement" else tr('Edit condition'))

    def build_body(self, master):
        ttk.Label(master, style="SE.TLabel", text=tr('Function call:') if self.node["kind"] == "call" else tr('Statement:') if self.node["kind"] == "statement" else tr('Condition:')).pack(anchor="w")
        self.text = tk.Text(master, width=52, height=4, wrap="word", undo=True,
                            font="TkDefaultFont", relief="flat", borderwidth=0,
                            highlightthickness=1, highlightbackground=FIELD_BORDER,
                            highlightcolor=SELECT, padx=8, pady=8)
        self.text.pack(fill="both", expand=True, pady=6)
        self.text.insert("1.0", self.node["text"])
        self.text.tag_add("sel", "1.0", "end-1c")
        # Mehrzeilige Texte: Eingabetaste erzeugt eine neue Zeile.
        self.text.bind("<Return>", lambda event: self.text.insert("insert", "\n") or "break")
        self.text.bind("<KP_Enter>", lambda event: self.text.insert("insert", "\n") or "break")
        return self.text

    def validate(self):
        if len(self.text.get("1.0", "end-1c")) > 10000:
            messagebox.showerror(tr('Edit block'), tr('Please enter at most 10000 characters.'), parent=self)
            return False
        return True

    def apply(self):
        self.result = self.text.get("1.0", "end-1c")


class LoopFieldsDialog(EditDialog):
    """Schleifenparameter als einzelne, sprachunabhängige Eingabefelder."""
    def __init__(self, parent, node):
        self.node = node
        self.result = None
        self.variables = {}
        self.entries = {}
        super().__init__(parent, {"repeat": tr('Repeat n times'), "for": tr('Counting loop'),
                                  "foreach": tr('For each element')}[node["kind"]])

    def build_body(self, master):
        labels = {"count": tr('Count'), "variable": tr('Counter variable'), "start": tr('Initial value'),
                  "end": tr('Final value'), "step": tr('Step'), "element": tr('Element variable'),
                  "collection": tr('Collection'), "direction": tr('Direction')}
        for row, field in enumerate(LOOP_FIELDS[self.node["kind"]]):
            ttk.Label(master, style="SE.TLabel", text=labels[field]).grid(row=row, column=0, sticky="w", padx=(0, 12), pady=5)
            value = self.node[field]
            if field == "direction":
                value = tr('Down') if value == "down" else tr('Up')
            variable = tk.StringVar(master, value=value)
            self.variables[field] = variable
            if field == "direction":
                entry = ttk.Combobox(master, style="SE.TCombobox", textvariable=variable, state="readonly",
                                     values=(tr('Up'), tr('Down')), width=40)
            else:
                entry = ttk.Entry(master, style="SE.TEntry", textvariable=variable, width=42)
            entry.grid(row=row, column=1, sticky="ew", pady=5)
            self.entries[field] = entry
        ttk.Label(master, style="SE.TLabel", text=tr('Values, variables or expressions are accepted.\nEmpty fields appear as placeholders.')).grid(
            row=len(self.variables), column=0, columnspan=2, sticky="w", pady=(10, 0))
        first = next(iter(self.entries.values()))
        first.selection_range(0, "end")
        return first

    def validate(self):
        for field, variable in self.variables.items():
            if len(variable.get()) > 1000:
                messagebox.showerror(tr('Edit loop'), tr('Please enter at most 1000 characters per field.'), parent=self)
                self.entries[field].focus_set()
                return False
        return True

    def apply(self):
        self.result = {field: variable.get().strip() for field, variable in self.variables.items()}
        if "direction" in self.result:
            self.result["direction"] = "down" if self.result["direction"] == tr('Down') else "up"


class IfDialog(BlockTextDialog):
    def build_body(self, master):
        widget = super().build_body(master)
        self.with_else = tk.BooleanVar(master, value=self.node["kind"] == "if")
        ttk.Label(master, style="SE.TLabel", text=tr('Branches')).pack(anchor="w", pady=(12, 6))
        variants = ttk.Frame(master, style="SE.TFrame")
        variants.pack(fill="x")
        self.single_option = ttk.Radiobutton(variants, style="SE.TRadiobutton", text=tr('One-way'), variable=self.with_else, value=False)
        self.else_option = ttk.Radiobutton(variants, style="SE.TRadiobutton", text=tr('With else branch'), variable=self.with_else, value=True)
        self.single_option.pack(side="left", padx=(0, 20))
        self.else_option.pack(side="left")
        return widget

    def validate(self):
        if not super().validate():
            return False
        if not self.with_else.get() and self.node.get("else"):
            messagebox.showerror(tr('Change selection'), tr('The else branch contains blocks. Please move or remove them first.'), parent=self)
            return False
        return True

    def apply(self):
        self.result = {"text": self.text.get("1.0", "end-1c"), "with_else": self.with_else.get()}


class CaseDialog(EditDialog):
    def __init__(self, parent, node):
        self.working = copy.deepcopy(node)
        self.result = None
        self.active_case = 0
        self._updating = False
        super().__init__(parent, tr('Edit multiway selection'))

    def build_body(self, master):
        ttk.Label(master, style="SE.TLabel", text=tr('Selection expression')).pack(anchor="w")
        self.selector = tk.StringVar(master, value=self.working["text"])
        selector_entry = ttk.Entry(master, style="SE.TEntry", textvariable=self.selector, width=54)
        selector_entry.pack(fill="x", pady=(4, 10))
        self.cases = ttk.Treeview(master, style="SE.Treeview", columns=("value", "size"), show="headings", height=6, selectmode="browse")
        self.cases.heading("value", text=tr('Case value'))
        self.cases.heading("size", text=tr('Blocks'))
        self.cases.column("value", width=260)
        self.cases.column("size", width=100, anchor="center")
        self.cases.pack(fill="both", expand=True)
        self.cases.bind("<<TreeviewSelect>>", self.select_case)
        self.value = tk.StringVar(master)
        ttk.Label(master, style="SE.TLabel", text=tr('Case value')).pack(anchor="w", pady=(10, 0))
        ttk.Entry(master, style="SE.TEntry", textvariable=self.value).pack(fill="x", pady=4)
        self.value.trace_add("write", self.change_value)
        actions = ttk.Frame(master, style="SE.TFrame")
        actions.pack(fill="x", pady=6)
        for index, (text, command) in enumerate((
            (tr('Add case'), self.add_case), (tr('Remove case'), self.remove_case),
            (tr('Move up'), lambda: self.move_case(-1)), (tr('Move down'), lambda: self.move_case(1)),
        )):
            self._action_button(actions, index, text, command, gap=4)
        ttk.Label(master, style="SE.TLabel", text=tr('The else branch remains as the last section.')).pack(anchor="w")
        self.refresh_cases()
        return selector_entry

    def refresh_cases(self):
        self._updating = True
        self.cases.delete(*self.cases.get_children())
        for index, case in enumerate(self.working["cases"]):
            self.cases.insert("", "end", iid=str(index), values=(case["value"] or tr('Case'), len(case["body"])))
        self.cases.selection_set(str(self.active_case))
        self.cases.see(str(self.active_case))
        self.value.set(self.working["cases"][self.active_case]["value"])
        self._updating = False

    def select_case(self, event=None):
        selected = self.cases.selection()
        if self._updating or not selected:
            return
        self.active_case = int(selected[0])
        self._updating = True
        self.value.set(self.working["cases"][self.active_case]["value"])
        self._updating = False

    def change_value(self, *_):
        if not self._updating:
            case = self.working["cases"][self.active_case]
            case["value"] = self.value.get()
            self.cases.item(str(self.active_case), values=(case["value"] or tr('Case'), len(case["body"])))

    def add_case(self):
        if len(self.working["cases"]) >= 32:
            messagebox.showinfo(tr('Multiway selection'), tr('At most 32 cases are supported.'), parent=self)
            return
        self.working["cases"].append({"value": str(len(self.working["cases"])+1), "body": []})
        self.active_case = len(self.working["cases"])-1
        self.refresh_cases()

    def remove_case(self):
        if len(self.working["cases"]) == 1:
            return
        if self.working["cases"][self.active_case]["body"] and not messagebox.askyesno(
            tr('Remove case'), tr('Remove this case and all blocks it contains?'), parent=self
        ):
            return
        self.working["cases"].pop(self.active_case)
        self.active_case = min(self.active_case, len(self.working["cases"])-1)
        self.refresh_cases()

    def move_case(self, delta):
        target = self.active_case + delta
        cases = self.working["cases"]
        if 0 <= target < len(cases):
            cases[self.active_case], cases[target] = cases[target], cases[self.active_case]
            self.active_case = target
            self.refresh_cases()

    def validate(self):
        if len(self.selector.get()) > 10000 or any(len(case["value"]) > 1000 for case in self.working["cases"]):
            messagebox.showerror(tr('Multiway selection'), tr('Selector: at most 10000 characters; case value: at most 1000 characters.'), parent=self)
            return False
        return True

    def apply(self):
        self.working["text"] = self.selector.get()
        self.result = self.working




class ImageSizeDialog(EditDialog):
    def __init__(self, parent, width, height, kind="PNG"):
        self.aspect = width/height
        self._updating_size = False
        self.kind = kind
        factor = max(32/min(width, height), min(1, 2048/max(width, height)))
        self.initial_size = round(width*factor), round(height*factor)
        if kind.upper() != "SVG" and max(self.initial_size) > 8192:
            raise ValueError(tr('The diagram is too narrow or too long for a proportional export with 32–8192 pixels per side.'))
        self.result = None
        self.options = None
        super().__init__(parent, tr('Export {format}').format(format=kind))

    def build_body(self, master):
        self.width_value = tk.StringVar(self, value=str(self.initial_size[0]))
        self.height_value = tk.StringVar(self, value=str(self.initial_size[1]))
        self.width_value.trace_add("write", lambda *_: self._sync_size("width"))
        self.height_value.trace_add("write", lambda *_: self._sync_size("height"))
        first = None
        row = 0
        if self.kind.upper() != 'SVG':
            for label, variable in ((tr('Width (pixels)'), self.width_value), (tr('Height (pixels)'), self.height_value)):
                ttk.Label(master, text=label).grid(row=row, column=0, sticky="w", padx=(0, 12), pady=6)
                entry = ttk.Entry(master, textvariable=variable, width=12, style='SE.TEntry')
                entry.grid(row=row, column=1, pady=6)
                first = first or entry
                row += 1
            ttk.Separator(master).grid(row=row, column=0, columnspan=2, sticky='ew', pady=8)
            row += 1
        previous = load_options()
        self.export_choices = {}
        for key, label in (('transparent_background', tr('Transparent background')),
                           ('transparent_models', tr('Transparent models')), ('monochrome', tr('Monochrome'))):
            variable = tk.BooleanVar(self, value=getattr(previous, key))
            self.export_choices[key] = variable
            checkbox = ttk.Checkbutton(master, text=label, variable=variable)
            checkbox.grid(row=row, column=0, columnspan=2, sticky='w', pady=4)
            first = first or checkbox
            row += 1
        return first

    def _sync_size(self, changed):
        if self._updating_size:
            return
        source, target = (self.width_value, self.height_value) if changed == "width" else (self.height_value, self.width_value)
        try:
            value = int(source.get())
            if not 0 < value <= 8192:
                return
        except ValueError:
            return
        self._updating_size = True
        try:
            target.set(str(max(1, round(value/self.aspect if changed=="width" else value*self.aspect))))
        finally:
            self._updating_size = False

    def validate(self):
        if self.kind.upper() == 'SVG':
            return True
        try:
            w, h = int(self.width_value.get()), int(self.height_value.get())
            if not (32 <= w <= 8192 and 32 <= h <= 8192 and w*h <= 24_000_000):
                raise ValueError
        except ValueError:
            messagebox.showerror(tr('{format} resolution').format(format=self.kind), tr('32–8192 pixels per side; at most 24 megapixels in total.'), parent=self)
            return False
        return True

    def apply(self):
        self.options = ExportOptions(**{key: value.get() for key, value in self.export_choices.items()})
        save_options(self.options)
        self.result = () if self.kind.upper() == 'SVG' else (int(self.width_value.get()), int(self.height_value.get()))


class RelationshipDialog(EditDialog):
    def __init__(self, parent, start, end, relation, *, on_apply=None):
        self.on_apply = on_apply
        self.self_relationship = relation['start'] == relation['end']
        self.names = ((f"{start} · {tr('Upper connection')}", f"{end} · {tr('Lower connection')}")
                      if self.self_relationship else (start, end))
        self.relation = relation
        self.result = None
        super().__init__(parent, tr('Edit relationship'))

    def buttonbox(self):
        actions = ttk.Frame(self, padding=(20, 4, 20, 16), style="SE.TFrame")
        actions.pack(fill="x")
        actions.grid_anchor("e")
        self._action_button(actions, 0, tr('Cancel'), self.cancel, gap=8)
        self.apply_button = self._action_button(actions, 1, tr('Apply'), self.apply_changes, gap=8)
        self.ok_button = self._action_button(actions, 2, tr('OK'), self.ok)
        self.bind("<Return>", self.ok)
        self.bind("<KP_Enter>", self.ok)
        self.bind("<Escape>", self.cancel)

    def apply_changes(self):
        if not self.validate():
            return False
        try:
            if self.on_apply is not None:
                self.on_apply(self.result)
        except (ValueError, RecursionError) as exc:
            messagebox.showerror(self.title(), str(exc), parent=self)
            return False
        return True

    def ok(self, event=None):
        if self.apply_changes():
            self.cancel()

    def build_body(self, master):
        from .uml_relationships import RELATIONSHIP_KINDS

        self.relationship_kinds = {key: tr(label) for key,label in RELATIONSHIP_KINDS.items()
                                   if not self.self_relationship or key not in ('inheritance','realization')}
        self.kind = tk.StringVar(self, value=self.relationship_kinds[self.relation["kind"]])
        ttk.Label(master, text=tr('Relationship kind')).grid(row=0, column=0, sticky="w")
        kind_row = ttk.Frame(master)
        kind_row.grid(row=0, column=1, columnspan=2, sticky="ew")
        picker = ttk.Combobox(kind_row, textvariable=self.kind, values=tuple(self.relationship_kinds.values()),
                              state="readonly", width=18, style="SE.TCombobox")
        picker.pack(side="left")
        self.preview_scale = max(1, tkfont.nametofont('TkDefaultFont').metrics('linespace')/17)
        self.relationship_preview = tk.Canvas(kind_row, width=round(96*self.preview_scale),
            height=round(30*self.preview_scale), highlightthickness=0, borderwidth=0,
            takefocus=False)
        self.relationship_preview.pack(side="right", padx=(12, 0))
        self.hint = ttk.Label(master, wraplength=420)
        self.hint.grid(row=1, column=0, columnspan=3, sticky="w", pady=(7, 10))
        ttk.Label(master, text=tr('Relationship name')).grid(row=2, column=0, sticky="w")
        self.label = ttk.Entry(master, style="SE.TEntry")
        self.label.insert(0, self.relation["label"])
        self.label.grid(row=2, column=1, columnspan=2, sticky="ew", pady=(0, 8))
        start, end = self.names
        self.directions = dict(zip(("", "end", "start", "both"),
                                   (tr('Undirected'), f"{start} → {end}", f"{end} → {start}", tr('Both directions'))))
        ttk.Label(master, text=tr('Direction')).grid(row=3, column=0, sticky="w")
        self.direction = ttk.Combobox(master, values=tuple(self.directions.values()),
                                      state="readonly", width=26, style="SE.TCombobox")
        self.direction.set(self.directions[self.relation["direction"]])
        self.direction.grid(row=3, column=1, columnspan=2, sticky="ew", pady=(0, 8))
        for column, label in ((1, tr('Role')), (2, relationship_count_label())):
            ttk.Label(master, text=label).grid(row=4, column=column, sticky="w", padx=(0, 7))
        self.entries = {}
        for row, (end, name) in enumerate(zip(("start", "end"), self.names), start=5):
            ttk.Label(master, text=name, wraplength=165).grid(row=row, column=0, sticky="w", padx=(0, 12), pady=4)
            role = ttk.Entry(master, width=18, style="SE.TEntry")
            role.grid(row=row, column=1, sticky="ew", padx=(0, 7), pady=4)
            count = ttk.Combobox(master, values=("", "1", "0..1", "0..*", "1..*", "*", "n"),
                                 width=10, style="SE.TCombobox")
            count.grid(row=row, column=2, sticky="ew", pady=4)
            role.insert(0, self.relation[end+"_role"])
            count.set(self.relation[end+"_multiplicity"])
            self.entries[end+"_role"] = role
            self.entries[end+"_multiplicity"] = count
        picker.bind("<<ComboboxSelected>>", self._update_kind)
        self.direction.bind("<<ComboboxSelected>>", self._update_kind)
        self._update_kind()
        return picker

    def _update_kind(self, event=None):
        start, end = self.names
        kind = self.kind.get()
        if kind != tr('Association') and self.direction.get() == self.directions['start']:
            start, end = end, start
        if kind == tr('Realization'):
            text = tr('{start} implements the interface {end}.').format(start=start, end=end)
        elif kind == tr('Inheritance'):
            text = tr("{start} inherits from {end}.").format(start=start, end=end)
        elif kind == tr('Aggregation'):
            text = tr('{p0} contains {p1}. A part can also exist independently.').format(p0=start, p1=end)
        elif kind == tr('Composition'):
            text = tr('{p0} owns {p1} as an integral part. Its lifecycle depends on the whole.').format(p0=start, p1=end)
        else:
            text = tr('Objects of {p0} and {p1} are related. An arrow shows which class can be reached from the other.').format(p0=start, p1=end)
        self.hint.configure(text=text)
        association = kind == tr('Association')
        keys = ("", "end", "start", "both") if association else ("end", "start")
        self.direction.configure(state="readonly", values=tuple(self.directions[key] for key in keys))
        if self.direction.get() not in self.direction.cget('values'):
            self.direction.set(self.directions['end'])
        for entry in self.entries.values():
            entry.configure(state="disabled" if kind in (tr('Inheritance'), tr('Realization')) else "normal")
        self._draw_relationship_preview()

    def _draw_relationship_preview(self):
        from .uml_relationships import endpoint_symbol, association_arrow
        canvas = self.relationship_preview
        style = ttk.Style(self)
        background = style.lookup('TFrame', 'background') or self.cget('background')
        ink = style.lookup('TLabel', 'foreground') or '#20252a'
        canvas.configure(background=background)
        canvas.delete('all')
        kind = next(key for key, label in self.relationship_kinds.items() if label == self.kind.get())
        direction = next(key for key, label in self.directions.items() if label == self.direction.get())
        first, last = (8, 15), (88, 15)
        if kind != 'association' and direction == 'start':
            first, last = last, first
        canvas.create_line(*first, *last, fill=ink, width=1.5,
                           dash=(5, 3) if kind == 'realization' else ())
        if kind == 'association':
            for key, point, other in (('start', first, last), ('end', last, first)):
                if direction in (key, 'both'):
                    canvas.create_line(*association_arrow(point, other), fill=ink, width=1.5)
        else:
            point, other = (last, first) if kind in ('inheritance', 'realization') else (first, last)
            canvas.create_polygon(*endpoint_symbol(kind, point, other),
                fill=ink if kind == 'composition' else background, outline=ink, width=1.5)
        canvas.scale('all', 0, 0, self.preview_scale, self.preview_scale)

    def validate(self):
        from .uml_relationships import RELATIONSHIP_KINDS, multiplicity, role_name

        kind = next(key for key, label in self.relationship_kinds.items() if label == self.kind.get())
        direction = next(key for key, label in self.directions.items() if label == self.direction.get())
        result = {"kind": kind, "direction": direction if kind == "association" else ""}
        try:
            result["label"] = role_name(self.label.get())
        except ValueError as exc:
            messagebox.showerror(self.title(), str(exc), parent=self)
            self.label.focus_set()
            return False
        for key, entry in self.entries.items():
            validator = role_name if key.endswith("_role") else multiplicity
            try:
                result[key] = "" if kind in ("inheritance", "realization") else validator(entry.get())
            except ValueError as exc:
                messagebox.showerror(self.title(), str(exc), parent=self)
                entry.focus_set()
                return False
        if kind != 'association' and direction == 'start':
            result['start'], result['end'] = self.relation['end'], self.relation['start']
            for suffix in ('role', 'multiplicity'):
                result['start_'+suffix], result['end_'+suffix] = result['end_'+suffix], result['start_'+suffix]
            if self.relation.get('bend') and not self.self_relationship:
                result['bend'] = -self.relation['bend']
        self.result = result
        return True
