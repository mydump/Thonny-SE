# SPDX-FileCopyrightText: 2026 Sebastian Ladhoff
# SPDX-License-Identifier: GPL-3.0-only
# See LICENSE in the project root for the full license text.

"""A magnified UML row with all controls in one horizontal strip."""
from .scrolling import ScrollArea
from .i18n import tr
import copy
import tkinter as tk
from tkinter import ttk
from uuid import uuid4
from thonny import get_workbench
from thonny.ui_utils import create_tooltip
from .ui_style import UML_SECTION_FILLS, DISABLED, ERROR, FIELD_BORDER, INK, MUTED, SELECT, SELECTION_FILL
from .uml_edit_panel import DELETE_FILL, PANEL_INSET, DeleteButton, delete_switch, edit_panel, panel_badge, picker
from .field_feedback import FieldFeedback
from .diagram_preferences import UML_CHECK_TYPES, enabled
from .uml_type_validation import TypeContext, member_type_fields, type_error, validate_member_types
from .uml_accessors import accessor_kinds, set_accessors, manual_accessor_kinds
from .uml_row_grip import RowGrip
from .iconregistry import draw_visibility_icon, icon_path, paper_icon, menu_icon
from . import retina_icons
from .uml_methods import (VISIBILITIES, attribute_draft, display_member_name, draft_from_row,
                          member_visibility, validate_attribute, validate_method, is_constructor, method_suggestions, canonical_method_name, hidden_constructor)


ACCESSOR_STYLE = "SE.Accessor.TCheckbutton"


class InlineMemberEditor(tk.Frame):
    def __init__(self, diagram, cid, section, row_id):
        super().__init__(diagram, background="white", borderwidth=0,
                         highlightthickness=2, highlightbackground=SELECT, highlightcolor=SELECT)
        self.diagram, self.editor, self.cid, self.section, self.row_id = diagram, diagram.editor, cid, section, row_id
        self.fill = UML_SECTION_FILLS[section]
        self.ready, self.dirty = False, False
        self.reorder_mode = False
        self.reorder_anchor = None
        self.invalid_field = None
        self.input_fields = {}
        self.parameters = []
        card = self.editor.card(cid)
        row = next((r for r in card[section] if r["id"]==row_id), None)
        self.original = copy.deepcopy(row)
        data = attribute_draft(row) if section=="attributes" else draft_from_row(row)[0]
        self.visibility = tk.StringVar(self, value=data["visibility"])
        self.original_name = data["name"]
        self.original_visibility = data["visibility"]
        self.display_name = "__init__" if section == "methods" and data["kind"] == "constructor" else display_member_name(self.original_name, self.original_visibility)
        self.suggested_accessor = None
        self._syncing_method = False
        self.name = tk.StringVar(self, value=self.display_name)
        self.typename = tk.StringVar(self, value=data.get("type", data.get("return_type", "")))
        self.kind = tk.StringVar(self, value=data.get("kind", "procedure"))
        self.default = tk.StringVar(self, value=data.get("default", ""))
        self._automatic_list_default = False
        self._setting_list_default = False
        self.default.trace_add("write", self._list_default_edited)
        self.typename.trace_add("write", self._update_list_default)
        self.accessors = {}
        if section == "attributes":
            existing = accessor_kinds(card, row_id)
            self.accessors = {kind: tk.BooleanVar(self, value=kind in existing) for kind in ("get", "set")}
        self.initial_accessors = self._checked_accessors()
        for value in data.get("parameters", []):
            self.parameters.append(self._parameter_vars(value))
        from .integration import read_python_source
        self.type_context = TypeContext(self.editor.document, card, read_python_source)
        self.initial = copy.deepcopy(self.payload())
        for variable in (self.visibility, self.name, self.typename, self.kind, self.default, *self.accessors.values()):
            variable.trace_add("write", self._changed)
        self.build_row()
        self.ready = True
        self._refresh_type_feedback()

    def _list_default_edited(self, *args):
        if not self._setting_list_default:
            self._automatic_list_default = False

    def _update_list_default(self, *args):
        # Defaults belong to instance attributes, never mutable parameter defaults.
        if self.section != "attributes":
            return
        typename = self.typename.get().strip()
        is_list = typename == "list" or typename.startswith("list[")
        value = self.default.get()
        self._setting_list_default = True
        try:
            if is_list and not value.strip():
                self.default.set("[]")
                self._automatic_list_default = True
            elif not is_list and self._automatic_list_default:
                self.default.set("")
                self._automatic_list_default = False
        finally:
            self._setting_list_default = False

    @property
    def font(self):
        return self.diagram.display_normal

    def _parameter_vars(self, data):
        result = {key: tk.StringVar(self, value=data.get(key, "")) for key in ("name", "type", "default")}
        if "kind" in data:
            result["kind"] = tk.StringVar(self, value=data["kind"])
        for variable in result.values():
            variable.trace_add("write", self._changed)
        return result

    def payload(self):
        name = self.name.get().strip()
        visibility = self.visibility.get()
        if name == self.display_name and visibility == self.original_visibility:
            name = self.original_name
        if self.section == "attributes":
            return dict(name=name, visibility=visibility, type=self.typename.get().strip(), default=self.default.get().strip())
        name = canonical_method_name(self.editor.card(self.cid), name)
        kind = "constructor" if name == "__init__" else self.kind.get()
        return dict(kind=kind, name="__init__" if kind == "constructor" else name, visibility="public" if kind == "constructor" else visibility,
                    return_type=self.typename.get().strip() if kind=="function" else "",
                    parameters=[{key: value.get().strip() for key,value in row.items()} for row in self.parameters])

    def _checked_accessors(self):
        return {kind for kind, enabled in self.accessors.items() if enabled.get()}

    def _changed(self, *args):
        if not self.ready:
            return
        if self.section == "methods" and not self._syncing_method:
            self._update_method_kind()
        self.dirty = self.payload() != self.initial or self._checked_accessors() != self.initial_accessors
        if self.invalid_field is not None:
            self.invalid_field.set_error()
            self.invalid_field = None
        self._refresh_type_feedback()
        self.editor.update_title()

    def _refresh_type_feedback(self):
        if not self.ready:
            return
        for field, text in member_type_fields(self.payload(), self.section):
            variable = self.parameters[field[0]][field[1]] if isinstance(field, tuple) else self.typename
            feedback = self.input_fields.get(str(variable))
            if feedback is not None:
                feedback.set_error(type_error(text) if enabled(UML_CHECK_TYPES) and not self.type_context.check(text) else "")

    def _label(self, parent, text, color=INK):
        return tk.Label(parent, text=text, background=self.fill, foreground=color, font=self.font, borderwidth=0, padx=0, pady=0)

    def _entry(self, parent, variable, width, tooltip, *, border=None):
        entry = tk.Entry(parent, textvariable=variable, font=self.font, width=width, relief="flat", borderwidth=0,
                         background="white", foreground=INK, insertbackground=INK, cursor="xterm",
                         highlightthickness=0 if border is not None else 1)
        self.diagram.bind_row_navigation(entry)
        entry.bind("<Escape>", lambda e: self._cancel())
        entry.bind("<Return>", lambda e: self._accept(repeat=True))
        entry.bind("<KP_Enter>", lambda e: self._accept(repeat=True))
        entry.bind("<Control-Return>", lambda e: self._accept())
        entry.bind("<Control-KP_Enter>", lambda e: self._accept())
        entry.bind("<Tab>", lambda e, widget=entry: self._tab(widget, 1))
        entry.bind("<Shift-Tab>", lambda e, widget=entry: self._tab(widget, -1))
        entry.bind("<ISO_Left_Tab>", lambda e, widget=entry: self._tab(widget, -1))
        self.input_fields[str(variable)] = FieldFeedback(entry, tooltip, border=border)
        entry.bind("<Destroy>", lambda event: self.input_fields.pop(str(variable), None), add=True)
        return entry

    def _button(self, parent, text, command, width=None, *, tooltip=None):
        # Native macOS buttons keep a bezel even with relief=flat. A focusable
        # label provides the deliberately unobtrusive action inside the text row.
        options = dict(text=text, font=self.font, relief="flat", borderwidth=0, highlightthickness=1,
                       highlightbackground=self.fill, highlightcolor=FIELD_BORDER, background=self.fill,
                       foreground=MUTED, disabledforeground=DISABLED, cursor="arrow", padx=2, pady=0, takefocus=1)
        if width is not None:
            options['width'] = width
        button = tk.Label(parent, **options)
        button.inline_action = True
        self.diagram.bind_row_navigation(button)
        def activate(event):
            if button.cget("state") != "disabled":
                command()
            return "break"

        button.bind("<ButtonRelease-1>", lambda e: activate(e) if 0<=e.x<button.winfo_width() and 0<=e.y<button.winfo_height() else None)
        button.bind("<Return>", activate)
        button.bind("<KP_Enter>", activate)
        button.bind("<space>", activate)
        if tooltip:
            create_tooltip(button, tooltip)
        button.bind("<Enter>", lambda e: button.configure(background="#dceaff"), add=True)
        button.bind("<Leave>", lambda e: button.configure(background=self.fill), add=True)
        button.bind("<Escape>", lambda e: self._cancel())
        button.bind("<Tab>", lambda e, widget=button: self._tab(widget, 1))
        button.bind("<Shift-Tab>", lambda e, widget=button: self._tab(widget, -1))
        button.bind("<ISO_Left_Tab>", lambda e, widget=button: self._tab(widget, -1))
        return button

    def _type(self, parent, variable, *, result=False, inline=False):
        frame = tk.Frame(parent, background=self.fill)
        if inline:
            self._label(frame, ": ", MUTED).pack(side="left")
        element_types = list(dict.fromkeys(["int", "float", "str", "bool", "dict"]
                                           + [c["name"] for c in self.editor.document["classes"]]))
        values = ["", *element_types, "list",
                  *(f"list[{name}]" for name in [*element_types, "list"])]

        def choose(value):
            variable.set(value)
            if result:
                self.kind.set("function" if value else "procedure")
            entry.focus_set()

        tooltip = tr('Return type') if result else tr('Type')
        empty_label = tr('No return value (procedure)') if result else tr('No type annotation')
        control, entry = picker(frame, lambda border: self._entry(border, variable, 7, tooltip, border=border),
                                ((value, value or empty_label) for value in dict.fromkeys(values)), choose)
        control.pack(side="left", fill="x", expand=True)
        frame.entry = entry
        if result:
            def typed(*args):
                if self.kind.get() != "constructor":
                    target = "function" if variable.get().strip() else "procedure"
                    if self.kind.get() != target:
                        self.kind.set(target)
            token = variable.trace_add("write", typed)
            frame.bind("<Destroy>", lambda e: variable.trace_remove("write", token) if e.widget is frame else None, add=True)
        return frame

    def _cell(self, widget, column):
        widget.grid(row=0, column=column, padx=2, sticky="ew")

    def _trash(self, parent, command, tooltip):
        button = self._button(parent, "", command, tooltip=tooltip)
        if retina_icons.enabled(self):
            button.configure(text=retina_icons.glyph("edit.delete"),
                             font=retina_icons.font_for(self, self.font), foreground=MUTED)
        else:
            button.configure(image=get_workbench().get_image(icon_path("edit.delete", size=16)))
        return button

    def build_row(self):
        self.panel = edit_panel(self,section=self.section)
        self.up_arrow = self.diagram.navigation_arrow(self.panel, -1)
        self.up_arrow.pack(side="top")
        self.down_arrow = self.diagram.navigation_arrow(self.panel, 1)
        self.down_arrow.pack(side="bottom")
        strip = self.strip = tk.Frame(self.panel, background=self.fill)
        strip.pack(fill="both", expand=True)
        self.form_canvas = tk.Canvas(strip, background=self.fill, highlightthickness=0, width=1, height=1,
                                     xscrollincrement=12)
        self.form_canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar = ttk.Scrollbar(self, orient="horizontal", command=self.form_canvas.xview)
        self.vertical_scrollbar = ttk.Scrollbar(strip, orient="vertical", command=self.form_canvas.yview)
        self.form_canvas.configure(xscrollcommand=self.scrollbar.set, yscrollcommand=self.vertical_scrollbar.set)
        self.form = tk.Frame(self.form_canvas, background=self.fill, padx=5, pady=2)
        self.form_window = self.form_canvas.create_window(0, 0, anchor="nw", window=self.form)
        self.form_canvas.bind("<Configure>", self._center_form)
        self.form.bind("<Configure>", self._resize_form)

        self.visibility_button = self._button(self.form, "", self.open_visibility, tooltip=tr('Visibility'))
        self._cell(self.visibility_button, 0)
        self._sync_visibility_icon()
        if self.section == 'methods':
            self.name_control, self.name_entry = picker(self.form,
                lambda border: self._entry(border, self.name, 12, tr('Name'), border=border),
                ((name, name) for name in method_suggestions(self.editor.card(self.cid), self.row_id)),
                self.choose_method)
            self._cell(self.name_control, 1)
        else:
            self.name_entry = self._entry(self.form, self.name, 12, tr('Name'))
            self._cell(self.name_entry, 1)
        column = 2
        if self.section == "methods":
            opening = self._label(self.form, "(")
            self._cell(opening, column)
            for widget in (self.visibility_button, self.name_control, opening):
                widget.grid_configure(sticky="new")
            self.parameter_group = tk.Frame(self.form, background=self.fill)
            self.parameter_group.grid(row=0, column=column+1)
            self.add_button = self._button(self.form, "+", self.add_parameter, tooltip=tr('Add parameter'))
            self._cell(self.add_button, column+2)
            closing = self._label(self.form, ")")
            self._cell(closing, column+3)
            for widget in (self.add_button, closing):
                widget.grid_configure(sticky="sew")
            self.rebuild_parameters()
            column += 4
        self.type_control = self._type(self.form, self.typename, result=self.section == "methods", inline=True)
        self._cell(self.type_control, column)
        if self.section == "methods":
            self.type_control.grid_configure(sticky="sew")
        if self.section == "attributes":
            self._cell(self._label(self.form, " = ", MUTED), column+1)
            self.default_entry = self._entry(self.form, self.default, 9, tr('Initial value'))
            self._cell(self.default_entry, column+2)
            style = ttk.Style(self)
            style.configure(ACCESSOR_STYLE, background=self.fill, foreground=INK)
            style.map(ACCESSOR_STYLE, background=[("active", self.fill), ("!active", self.fill)],
                      foreground=[("active", INK), ("!active", INK)])
            for offset, (kind, label) in enumerate((("get", "Getter"), ("set", "Setter")), start=3):
                checkbox = ttk.Checkbutton(self.form, text=label, variable=self.accessors[kind],
                                           style=ACCESSOR_STYLE)
                checkbox.inline_action = True
                self.diagram.bind_row_navigation(checkbox)
                checkbox.bind("<Escape>", lambda event: self._cancel())
                checkbox.bind("<Return>", lambda event: self._accept(repeat=True))
                checkbox.bind("<KP_Enter>", lambda event: self._accept(repeat=True))
                checkbox.bind("<Tab>", lambda event, widget=checkbox: self._tab(widget, 1))
                checkbox.bind("<Shift-Tab>", lambda event, widget=checkbox: self._tab(widget, -1))
                if kind in manual_accessor_kinds(self.editor.card(self.cid), self.row_id):
                    checkbox.state(['disabled'])
                    create_tooltip(checkbox, tr('This method already exists. Edit or delete it in the methods section.'))
                else:
                    create_tooltip(checkbox, tr("Generate {label} method").format(label=label))
                self._cell(checkbox, column+offset)

        if self.row_id is not None:
            self.grip = RowGrip(strip, self)
            badge = self.grip
        else:
            badge = panel_badge(strip, self.section, self.diagram.display_bold)
        badge.pack(side="left", before=self.form_canvas, padx=(2, 8))
        self.section_badge = badge

        actions = tk.Frame(strip, background=self.fill, padx=4, pady=2)
        actions.pack(side="right")
        self.action_font = self.diagram.action_font()
        self.apply_button = self._button(actions, "✓", self._accept, tooltip=tr('Apply (Enter)'))
        self.apply_button.configure(foreground='#28794e',font=self.action_font,padx=4,pady=1)
        self._cell(self.apply_button, 0)
        self.cancel_button = self._button(actions, "×", self._cancel, tooltip=tr('Cancel (Esc)'))
        self.cancel_button.configure(foreground=ERROR,font=self.action_font,padx=4,pady=1)
        self._cell(self.cancel_button, 1)
        if self.row_id is not None:
            self.trash_button = delete_switch(actions, False, self.diagram.toggle_delete_mode,background=self.fill)
            self.trash_button.inline_action = True
            self.diagram.bind_row_navigation(self.trash_button)
            self.trash_button.bind("<Escape>", lambda event: self._cancel())
            self.trash_button.bind("<Tab>", lambda event: self._tab(self.trash_button, 1))
            self.trash_button.bind("<Shift-Tab>", lambda event: self._tab(self.trash_button, -1))
            self._cell(self.trash_button, 2)
        self.actions = actions
        if self.section == "methods":
            self._update_method_kind()
        self.scrolling = ScrollArea(self.form_canvas, self, fallback_x=True)
        self._bind_scroll(self)
        if self.row_id is not None:
            self._bind_drag_surface(self)

    def set_reorder_mode(self, enabled):
        if self.reorder_mode == enabled:
            return
        self.reorder_mode = enabled
        if enabled:
            canvas = self.diagram.canvas
            self.reorder_anchor = (self.grip.winfo_rootx()-canvas.winfo_rootx()-PANEL_INSET,
                                   self.grip.winfo_rooty()-canvas.winfo_rooty()-4)
            for widget in (self.up_arrow, self.down_arrow, self.form_canvas, self.actions, self.scrollbar, self.vertical_scrollbar):
                widget.pack_forget()
            self.grip.pack_configure(padx=0)
        else:
            self.reorder_anchor = None
            self.up_arrow.pack(side="top", before=self.strip)
            self.down_arrow.pack(side="bottom", before=self.strip)
            self.grip.pack_configure(padx=(2, 8))
            self.form_canvas.pack(side="left", fill="both", expand=True)
            self.actions.pack(side="right")

    def _bind_drag_surface(self, widget):
        if isinstance(widget, (tk.Menu, tk.Toplevel)):
            return
        self.grip.bind_surface(widget)
        for child in widget.winfo_children():
            self._bind_drag_surface(child)

    def _bind_scroll(self, widget):
        if isinstance(widget, tk.Menu):
            return
        self.scrolling.bind(widget)
        if isinstance(widget, tk.Entry) or getattr(widget, "inline_action", False):
            widget.bind("<FocusIn>", lambda e: self.diagram.after_idle(self._reveal_field, e.widget), add=True)
        for child in widget.winfo_children():
            self._bind_scroll(child)

    def _center_form(self, event=None):
        top = max(0, (self.form_canvas.winfo_height() - self.form.winfo_reqheight())/2)
        if self.form_canvas.coords(self.form_window) != [0.0,top]:
            self.form_canvas.coords(self.form_window,0,top)

    def _resize_form(self, event=None):
        self._center_form()
        size=(self.form.winfo_reqwidth(),self.form.winfo_reqheight())
        if getattr(self,"_form_size",None) != size:
            self._form_size=size
            self.form_canvas.configure(scrollregion=(0,0,*size))
        self.diagram._position_member()

    def natural_width(self):
        width = self.form.winfo_reqwidth() + self.actions.winfo_reqwidth() + 2*PANEL_INSET + 4
        return width + self.section_badge.winfo_reqwidth() + 10

    def preferred_size(self, max_width, minimum_width, max_height):
        natural = self.natural_width()
        width = min(max_width, max(minimum_width, natural))
        arrows_height = self.up_arrow.winfo_reqheight() + self.down_arrow.winfo_reqheight()
        grip_height = self.section_badge.winfo_reqheight()
        height = max(self.form.winfo_reqheight(), self.actions.winfo_reqheight(), grip_height) + arrows_height + 8
        if natural > width:
            if self.scrollbar.winfo_manager() != "pack":
                self.scrollbar.pack(side="bottom",fill="x",before=self.form_canvas.master)
            height += self.scrollbar.winfo_reqheight()
        else:
            if self.scrollbar.winfo_manager():self.scrollbar.pack_forget()
            if self.form_canvas.xview()[0]:self.form_canvas.xview_moveto(0)
        if height > max_height:
            if self.vertical_scrollbar.winfo_manager() != "pack":
                self.vertical_scrollbar.pack(side="right",fill="y",before=self.form_canvas)
        else:
            if self.vertical_scrollbar.winfo_manager():self.vertical_scrollbar.pack_forget()
            if self.form_canvas.yview()[0]:self.form_canvas.yview_moveto(0)
        return width, height

    def _mark_invalid(self, error):
        field = getattr(error, "field", "name")
        if isinstance(field, tuple):
            index, key = field
            variable = self.parameters[index][key]
        else:
            variable = {"name": self.name, "type": self.typename, "default": self.default}.get(field, self.name)
        if self.invalid_field is not None:
            self.invalid_field.set_error()
        self.invalid_field = self.input_fields[str(variable)]
        self.invalid_field.set_error(str(error))
        self.invalid_field.widget.focus_set()

    def rebuild_parameters(self, focus_parameter=None):
        for child in self.parameter_group.winfo_children():
            child.destroy()
        entries = []
        if self.parameters:
            self.parameter_group.grid()
        else:
            self.parameter_group.grid_remove()
        for row in self.parameters:
            block = tk.Frame(self.parameter_group, background=self.fill)
            block.pack(side="top", anchor="w")
            block.grid_columnconfigure(0, minsize=self.font.measure("**")+4)
            if row.get('kind') is not None and row['kind'].get() in ('vararg','kwarg'):
                self._cell(self._label(block, '*' if row['kind'].get() == 'vararg' else '**'), 0)
            name = self._entry(block, row["name"], 12, tr('Parameter name'))
            self._cell(name, 1)
            entries.append(name)
            self._cell(self._type(block, row["type"], inline=True), 2)
            self._cell(self._label(block, " = ", MUTED), 3)
            self._cell(self._entry(block, row["default"], 7, tr('Default value')), 4)
            self._cell(self._trash(block, lambda row=row: self.remove_parameter(row), tr('Remove parameter')), 5)
            if self.ready:
                self._bind_scroll(block)
                if hasattr(self, "grip"):
                    self._bind_drag_surface(block)
        self._refresh_type_feedback()
        if focus_parameter is not None:
            entry = entries[focus_parameter]
            self.diagram.after_idle(lambda: entry.focus_set() if entry.winfo_exists() else None)

    def _reveal_field(self, widget):
        if not self.winfo_exists() or not widget.winfo_exists():
            return
        width = self.form_canvas.winfo_width()
        left = self.form_canvas.canvasx(0)
        offset = widget.winfo_rootx() - self.form.winfo_rootx()
        right = offset + widget.winfo_width()
        total = max(1, self.form.winfo_width())
        if offset < left:
            self.form_canvas.xview_moveto(max(0, offset-8) / total)
        elif right > left + width:
            self.form_canvas.xview_moveto((right - width + 8) / total)
        top = self.form_canvas.canvasy(0)
        height = self.form_canvas.winfo_height()
        offset = widget.winfo_rooty() - self.form.winfo_rooty()
        bottom = offset + widget.winfo_height()
        total = max(1, self.form.winfo_height())
        if offset < top:
            self.form_canvas.yview_moveto(max(0, offset-4) / total)
        elif bottom > top + height:
            self.form_canvas.yview_moveto((bottom-height+4) / total)

    def _update_method_kind(self):
        self._syncing_method = True
        try:
            constructor = canonical_method_name(self.editor.card(self.cid), self.name.get().strip()) == '__init__'
            target = 'constructor' if constructor else 'function' if self.typename.get().strip() else 'procedure'
            if self.kind.get() != target:
                self.kind.set(target)
            if constructor:
                self.visibility.set('public')
                self.typename.set('')
            if hasattr(self, 'type_control'):
                if constructor:
                    self.type_control.grid_remove()
                else:
                    self.type_control.grid()
            self._sync_visibility_icon()
        finally:
            self._syncing_method = False

    def choose_method(self, name):
        proposal = method_suggestions(self.editor.card(self.cid), self.row_id).get(name)
        if proposal is None:
            return
        if proposal.get('existing_id') is not None and self.row_id is None:
            diagram, cid, row_id = self.diagram, self.cid, proposal['existing_id']
            self.close(refresh=False)
            diagram.begin_edit(cid, 'methods', row_id)
            return
        data = proposal['method']
        self.suggested_accessor = copy.deepcopy(proposal.get('accessor'))
        self.name.set(name)
        self.visibility.set(data['visibility'])
        self.kind.set(data['kind'])
        self.typename.set(data['return_type'])
        self.parameters = [self._parameter_vars(param) for param in data['parameters']]
        self.rebuild_parameters()
        self._update_method_kind()
        self._changed()
        self.name_entry.focus_set()

    def _sync_visibility_icon(self):
        if self.section == 'methods' and canonical_method_name(self.editor.card(self.cid), self.name.get().strip()) == '__init__':
            self.visibility_button.configure(image='', text='c', font=self.font, foreground=MUTED, disabledforeground=MUTED, state="disabled", takefocus=0, width=0)
            return
        self.visibility_button.configure(state="normal", takefocus=1)
        if retina_icons.enabled(self):
            self.visibility_button.configure(image="", text=retina_icons.glyph("visibility." + self.visibility.get()),
                                             font=retina_icons.font_for(self, self.font), foreground=MUTED, width=0)
        else:
            self.visibility_button.configure(image=paper_icon(self, self.visibility.get(), 16), text="", width=0)

    def _focusables(self):
        def children(widget):
            result = []
            for child in widget.winfo_children():
                if (isinstance(child, tk.Entry) or getattr(child, "inline_action", False)) and child.winfo_ismapped() and str(child.cget('state'))!='disabled':
                    result.append(child)
                else:
                    result.extend(children(child))
            return result
        return children(self)

    def _tab(self, widget, direction):
        fields = self._focusables()
        if widget not in fields:
            return "break"
        index = fields.index(widget)+direction
        if 0 <= index < len(fields):
            fields[index].focus_set()
        else:
            self.diagram._tab(direction)
        return "break"

    def open_visibility(self):
        if self.section == "methods" and self.name.get().strip() == "__init__":
            return
        menu = tk.Menu(self, tearoff=False)
        for value, label in (("public", tr('Public')), ("private", tr('Private')), ("protected", tr('Protected'))):
            menu.add_command(label=label, image=menu_icon(get_workbench(), "visibility."+value), compound="left",
                             command=lambda value=value: self.set_visibility(value))
        self._popup(menu, self.visibility_button)

    def set_visibility(self, value):
        self.visibility.set(value)
        self._sync_visibility_icon()

    def _popup(self, menu, widget):
        retina_icons.decorate_menu(menu)
        if hasattr(self, "popup_menu"):
            self.popup_menu.destroy()
        self.popup_menu = menu
        menu.tk_popup(widget.winfo_rootx(), widget.winfo_rooty()+widget.winfo_height())

    def add_parameter(self, data=None, focus=True):
        if len(self.parameters)>=100:
            self._mark_invalid(ValueError(tr('At most 100 parameters.')))
            return
        self.parameters.append(self._parameter_vars(data or {}))
        self._changed()
        self.rebuild_parameters(len(self.parameters)-1 if focus else None)

    def remove_parameter(self, row):
        index = self.parameters.index(row)
        self.parameters.remove(row)
        self._changed()
        self.rebuild_parameters(min(index, len(self.parameters)-1) if self.parameters else None)
        if not self.parameters:
            self.add_button.focus_set()

    def _accept(self, *, repeat=False):
        if self.commit(explicit=True):
            if repeat and self.row_id is None:
                self.diagram.begin_edit(self.cid, self.section)
            else:
                self.diagram.canvas.focus_set()
        return "break"

    def _cancel(self):
        self.commit(cancel=True)
        self.diagram.canvas.focus_set()
        return "break"

    def commit(self, explicit=False, cancel=False):
        if cancel or (not explicit and not self.dirty):
            self.close()
            return True
        value = self.payload()
        row_id, original = self.row_id, self.original
        if self.section == 'methods' and value['kind'] == 'constructor' and row_id is None:
            existing = hidden_constructor(self.editor.card(self.cid))
            if existing is not None:
                row_id, original = existing['id'], existing
        try:
            if self.section == 'methods' and value['name'] == '__new__':
                raise ValueError(tr('__new__ must be edited directly in Python.'))
            (validate_attribute if self.section=="attributes" else validate_method)(value)
            if enabled(UML_CHECK_TYPES):
                from .integration import read_python_source
                self.type_context = TypeContext(self.editor.document, self.editor.card(self.cid), read_python_source)
                validate_member_types(value, self.section, self.type_context)
            if self.section == "methods" and value["kind"]=="constructor" and any(r["id"]!=row_id and is_constructor(r) for r in self.editor.card(self.cid)["methods"]):
                raise ValueError(tr('This class already has a constructor.'))
            if self.section == 'methods' and any(r['id'] != row_id and
                    ('__init__' if is_constructor(r) else draft_from_row(r)[0]['name']) == value['name']
                    for r in self.editor.card(self.cid)['methods']):
                raise ValueError(tr('The class member {p0!r} occurs more than once.').format(p0=value['name']))
            candidate = copy.deepcopy(self.editor.document)
            card = next(c for c in candidate["classes"] if c["id"]==self.cid)
            key = "attribute" if self.section=="attributes" else "method"
            row = dict(id=row_id or uuid4().hex, **{key:value})
            if self.section == 'methods' and original and 'abstract' in original:
                row['abstract'] = original['abstract']
            if self.section == "methods":
                proposal = method_suggestions(card, self.row_id).get(value['name'], {})
                if self.suggested_accessor and proposal.get('accessor') == self.suggested_accessor:
                    row['accessor'] = copy.deepcopy(self.suggested_accessor)
                elif self.original and 'accessor' in self.original and value == self.original['method']:
                    row['accessor'] = self.original['accessor']
            if row_id is None:
                card[self.section].append(row)
            else:
                card[self.section] = [row if r["id"]==row_id else r for r in card[self.section]]
            if self.section == "attributes":
                set_accessors(card, row, self._checked_accessors())
            from .uml_model import validate
            validate(candidate)
        except ValueError as exc:
            self._mark_invalid(exc)
            return False
        before = self.editor._snapshot()
        self.close(refresh=False)
        self.editor.document = candidate
        self.editor._record(before)
        return True

    def can_reorder(self):
        return not (self.section == "methods" and
                    (self.kind.get() == "constructor" or self.original is not None and is_constructor(self.original)))

    def visible_row_ids(self):
        card = self.editor.card(self.cid)
        rows = self.diagram._methods(card) if self.section == "methods" else card[self.section]
        return [row["id"] for row in rows if self.section != "methods" or not is_constructor(row)]

    def move_to(self, target_id):
        if not self.can_reorder():
            return
        visible = self.visible_row_ids()
        if self.row_id not in visible or target_id not in visible:
            return
        start, target = visible.index(self.row_id), visible.index(target_id)
        if start == target:
            return
        visible.insert(target, visible.pop(start))
        card = self.editor.card(self.cid)
        rows = card[self.section]
        by_id = {row["id"]: row for row in rows}
        ordered = iter(by_id[row_id] for row_id in visible)
        movable = set(visible)
        before = self.editor._snapshot()
        card[self.section] = [next(ordered) if row["id"] in movable else row for row in rows]
        self.editor._record(before)

    def close(self, refresh=True):
        diagram = self.diagram
        diagram.canvas.delete("member-drag-preview")
        self.place_forget()
        diagram.member_editor, diagram.editing = None, None
        self.destroy()
        diagram.repaint_after_overlay()
        if refresh:
            self.editor._refresh()


class DeleteMemberPanel(tk.Frame):
    """Show the saved member signature with a separate deletion action."""

    dirty = False

    def __init__(self, diagram, cid, section, row_id):
        super().__init__(diagram, borderwidth=0)
        self.diagram = diagram
        panel = edit_panel(self, deleting=True)
        self.diagram.navigation_arrow(panel, -1).pack(side="top")
        self.diagram.navigation_arrow(panel, 1).pack(side="bottom")
        row = tk.Frame(panel, background=DELETE_FILL)
        row.pack(fill="both", expand=True)
        card = diagram.editor.card(cid)
        member = next(item for item in card[section] if item["id"] == row_id)
        visibility = member_visibility(member, section)
        self.switch = delete_switch(row, True, diagram.toggle_delete_mode)
        self.switch.pack(side="right", padx=(5, 0))
        button = DeleteButton(row, diagram.display_normal, diagram.delete_current_member)
        button.pack(side="right", padx=4)
        panel_badge(row, section, diagram.display_bold, deleting=True).pack(side="left", padx=(2, 3))
        self.delete_button = button
        size = max(22, diagram.display_normal.metrics("linespace")+4)
        mark = tk.Canvas(row, width=size, height=size, background=DELETE_FILL, highlightthickness=0)
        if section == "methods" and is_constructor(member):
            mark.create_text(size/2,size/2,text="c",font=diagram.display_normal,fill=MUTED)
        else:
            draw_visibility_icon(mark, size/2, size/2, visibility, diagram.display_normal, diagram.zoom)
        mark.pack(side="left")
        self.signature = tk.Label(row, text=diagram._member_signature(member, section),
                                  justify="left", anchor="w", padx=5, background=DELETE_FILL,
                                  foreground=ERROR, font=diagram.display_normal)
        self.signature.pack(side="left", fill="both", expand=True)
        for widget in (button, self.switch):
            diagram.bind_row_navigation(widget)
            widget.bind("<Return>", lambda event: diagram.delete_current_member() or "break")
            widget.bind("<KP_Enter>", lambda event: diagram.delete_current_member() or "break")
            widget.bind("<Escape>", lambda event: diagram.toggle_delete_mode() or "break")

    def preferred_size(self, max_width, minimum_width, max_height):
        text_width = self.diagram.display_normal.measure(self.signature.cget("text")) + 32
        controls_width = self.switch.winfo_reqwidth() + self.delete_button.winfo_reqwidth() + 2*PANEL_INSET + 78
        width = min(max_width, max(minimum_width, text_width + controls_width))
        self.signature.configure(wraplength=max(10, width-controls_width))
        return width, self.winfo_reqheight()

    def commit(self, cancel=False):
        self.diagram.member_editor = self.diagram.editing = None
        self.destroy()
        self.diagram.repaint_after_overlay()
        return True
