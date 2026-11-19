# SPDX-FileCopyrightText: 2026 Sebastian Ladhoff
# SPDX-License-Identifier: GPL-3.0-only
# See LICENSE in the project root for the full license text.

"""Alle Laufzeit-Anpassungen an Thonny 5.0 bleiben hier gebündelt.

Es werden keine Dateien der Thonny-Installation verändert. Reguläre Dateien
und Befehle verwenden die jeweils vorgefundenen Originalfunktionen.
"""
from .i18n import tr
from functools import wraps
from pathlib import Path
import sys
import tkinter as tk

from thonny import get_workbench
from thonny.common import is_remote_path
from thonny.editors import EditorCodeViewText, EditorNotebook
from thonny.running import Runner

from .editor import BLOCK_CLIPBOARD_PREFIX, StructogramEditor
from .uml_editor import UmlEditor
from .graphical_document import GraphicalDocument
from . import retina_icons, uml_storage
from .iconregistry import icon_path, install_theme_updates, menu_icon, update_tab_icon
from tkinter import ttk
from .storage import EXTENSION, is_model_path

_installed = False
_HISTORY_TOOLBAR_IDS = ("undo", "redo", "thonny_se_export_png", "thonny_se_export_svg", "thonny_se_export_webp")


def has_active_grab(widget):
    """Inspect Tcl's grab path without resolving native popup widgets in Python."""
    try:
        return bool(widget.tk.call("grab", "current", widget._w))
    except tk.TclError:
        # During destruction, do not dispatch history actions into dead widgets.
        return True


def active_structogram():
    workbench = get_workbench()
    notebook = workbench.get_editor_notebook()
    return notebook is not None and isinstance(notebook.get_current_editor(), StructogramEditor)


def active_graphical():
    notebook = get_workbench().get_editor_notebook()
    return notebook is not None and isinstance(notebook.get_current_editor(), GraphicalDocument)


def graphic_export_available():
    if not active_graphical():
        return False
    editor = get_workbench().get_editor_notebook().get_current_editor()
    return bool((editor.document["classes"] or editor.document["comments"]) if isinstance(editor, UmlEditor)
                else any(n.get("enabled",True) for n in editor.document["body"]))


def guard_current_document(original):
    @wraps(original)
    def guarded(*args, **kwargs):
        if active_graphical():
            return None
        return original(*args, **kwargs)
    return guarded


def run_current_document(original):
    @wraps(original)
    def guarded(*args, **kwargs):
        editor = get_workbench().get_editor_notebook().get_current_editor()
        if isinstance(editor, UmlEditor):
            command = args[1] if args and isinstance(args[0], Runner) and len(args)>1 else 'Run'
            if command in ('Run', 'run'):
                return editor.run_diagram()
            return None
        if isinstance(editor, GraphicalDocument):
            return None
        return original(*args, **kwargs)
    return guarded


def new_structogram(document=None, *, suggested_stem=None):
    return new_graphical(StructogramEditor, document, suggested_stem=suggested_stem)


def new_uml(document=None, *, suggested_stem=None):
    return new_graphical(UmlEditor, document, suggested_stem=suggested_stem)


def new_graphical(editor_class, document=None, *, suggested_stem=None):
    notebook = get_workbench().get_editor_notebook()
    editor = editor_class(notebook)
    if isinstance(editor, StructogramEditor) and document is None:
        editor.diagram.info_hint.show(tr('Drag or click to add a block'))
    if document is not None:
        editor.document = document
        if isinstance(editor, UmlEditor):
            editor.diagram.arrange_cards()
        editor._refresh()
    # Erst benennen und speichern, dann den Dokument-Tab sichtbar anlegen.
    try:
        if not editor.save_file(suggested_stem=suggested_stem):
            editor.destroy()
            return None
    except Exception:
        editor.destroy()
        raise
    notebook.add(editor, text=editor.get_title())
    notebook.select(editor)
    get_workbench().event_generate("NewFile", editor=editor)
    editor.focus_set()
    return editor


def active_python():
    editor = get_workbench().get_editor_notebook().get_current_editor()
    return (editor is not None and not isinstance(editor, GraphicalDocument)
            and getattr(editor.get_text_widget(), "file_type", "python") == "python")


def import_python(selection=False):
    from tkinter import messagebox
    from .codeimport import parse_python
    if not active_python():
        return
    editor = get_workbench().get_editor_notebook().get_current_editor()
    widget = editor.get_text_widget()
    label = tr('Structogram from selection') if selection else tr('Structogram from file')
    if selection and not widget.tag_ranges("sel"):
        messagebox.showinfo(label, tr('Please select Python statements first.'), parent=editor)
        return
    source = widget.get("1.0", "end-1c")
    if selection:
        source = widget.get("sel.first", "sel.last")
        prefix = widget.get("sel.first linestart", "sel.first")
        if not prefix.strip():
            source = prefix + source
    try:
        document, warnings = parse_python(source, selection=selection, strict=True)
    except (ValueError, RecursionError) as exc:
        messagebox.showinfo(label, str(exc), parent=editor)
        return
    if not document["body"]:
        messagebox.showinfo(label, tr('The code contains no statements that can be displayed.'), parent=editor)
        return
    if warnings:
        messagebox.showinfo(label, tr('Import notes:\n\n') + "\n".join(warnings[:12]), parent=editor)
    filename = editor.get_filename()
    return new_structogram(document, suggested_stem=Path(filename).stem if filename else None)


_UML_IMPORT_LABEL = tr('UML diagram from Python code')


def import_python_uml(class_line=None):
    from tkinter import messagebox
    from .uml_import import parse_python_class, parse_python_classes

    if not active_python():
        return
    editor = get_workbench().get_editor_notebook().get_current_editor()
    label = tr('UML diagram from class') if class_line is not None else tr('UML diagram from file')
    try:
        source = editor.get_text_widget().get("1.0", "end-1c")
        filename = editor.get_filename()
        path = filename if filename and not is_remote_path(filename) else None
        if class_line is None:
            document = parse_python_classes(source, path=path)
            suggested_stem = Path(filename).stem if filename else None
        else:
            document, suggested_stem = parse_python_class(source, class_line, path=path)
    except (ValueError, RecursionError) as exc:
        messagebox.showinfo(label, str(exc), parent=editor)
        return
    if not document["classes"]:
        messagebox.showinfo(label, tr('The current Python tab contains no class definitions.'), parent=editor)
        return
    return new_uml(document, suggested_stem=suggested_stem)


UML_FILES_LABEL = tr('Classes from the file system …')


def import_python_uml_files(editor):
    from tkinter import messagebox
    from thonny.ui_utils import askopenfilenames

    if not editor.diagram.finish_edit():
        return
    paths = askopenfilenames(
        parent=editor, title=UML_FILES_LABEL, initialdir=str(Path(editor.get_filename()).parent),
        filetypes=[(tr('Python files'), ".py")],
    )
    paths = dict.fromkeys(Path(path) for path in paths if path)
    if not paths:
        return

    reserved = {card["name"] for card in editor.document["classes"]}
    document = _read_uml_paths(paths, UML_FILES_LABEL, editor, reserved_names=reserved)
    if document is not None:
        try:
            editor.add_imported_classes(document["classes"])
        except ValueError as exc:
            messagebox.showinfo(UML_FILES_LABEL, str(exc), parent=editor)


def import_python_uml_folder():
    from tkinter import messagebox

    workbench = get_workbench()
    editor = workbench.get_editor_notebook().get_current_editor()
    filename = editor.get_filename()
    label = tr('UML diagram from folder')
    if not filename or is_remote_path(filename):
        messagebox.showinfo(label, tr('Please open a locally saved Python file.'), parent=editor)
        return
    folder = Path(filename).parent
    try:
        paths = sorted(path for path in folder.iterdir() if path.suffix.lower() == ".py" and path.is_file())
    except OSError as exc:
        messagebox.showinfo(label, str(exc), parent=editor)
        return
    document = _read_uml_paths(paths, label, editor)
    if document is not None:
        return new_uml(document, suggested_stem=folder.name)


def read_python_source(path):
    from tokenize import open as open_python

    notebook = get_workbench().get_editor_notebook()
    opened = notebook.get_editor(str(path))
    if opened is not None:
        return opened.get_text_widget().get("1.0", "end-1c")
    try:
        with open_python(path) as source:
            return source.read()
    except (OSError, UnicodeError, SyntaxError) as exc:
        raise ValueError(tr('{p0}\nCould not read file: {p1}').format(p0=path, p1=exc)) from exc


def _read_uml_paths(paths, label, parent, *, reserved_names=()):
    from tkinter import messagebox
    from .uml_import import parse_python_files

    try:
        document = parse_python_files(((path, read_python_source(path)) for path in paths), reserved_names=reserved_names)
    except ValueError as exc:
        messagebox.showinfo(label, str(exc), parent=parent)
        return
    if not document["classes"]:
        messagebox.showinfo(label, tr('The selected files contain no class definitions.'), parent=parent)
        return
    return document


def python_context_menu(widget, class_line):
    menu = tk.Menu(widget, tearoff=False)
    workbench = get_workbench()

    def command(label, action, role):
        menu.add_command(label=label, command=action, image=menu_icon(workbench, role), compound="left")

    for label, action in ((tr('Copy'), "Copy"), (tr('Cut'), "Cut")):
        command(label, lambda action=action: widget.event_generate(f"<<{action}>>"), "edit." + action.lower())
    if not widget.is_read_only():
        try:
            text = widget.clipboard_get()
        except tk.TclError:
            text = ""
        if text and not text.startswith(BLOCK_CLIPBOARD_PREFIX):
            command(tr('Paste'), lambda: widget.event_generate("<<Paste>>"), "edit.paste")
    menu.add_separator()
    command(tr('Structogram from file'), import_python, "document.structogram")
    command(tr('Structogram from selection'), lambda: import_python(selection=True), "document.structogram")
    menu.add_separator()
    command(tr('UML diagram from class'), lambda: import_python_uml(class_line), "document.uml")
    command(tr('UML diagram from file'), import_python_uml, "document.uml")
    command(tr('UML diagram from folder'), import_python_uml_folder, "document.uml")
    retina_icons.decorate_menu(menu)
    return menu


def install():
    global _installed
    if _installed:
        return
    workbench = get_workbench()
    original_secondary_click = EditorCodeViewText.on_secondary_click
    original_bind_mouse = EditorCodeViewText._bind_mouse_aids

    def secondary_click(widget, event):
        if not active_python() or workbench.get_editor_notebook().get_current_editor().get_text_widget() is not widget:
            if sys.platform == "darwin" and event.num == 3:
                return
            return original_secondary_click(widget, event)

        from thonny.plugins.debugger import get_current_debugger
        if get_current_debugger() is not None:
            return original_secondary_click(widget, event)

        position = widget.index(f"@{event.x},{event.y}")
        widget.focus_set()
        if not widget.tag_ranges("sel"):
            widget.mark_set("insert", position)
        if hasattr(widget, "_se_context_menu"):
            widget._se_context_menu.destroy()
        widget._se_context_menu = python_context_menu(widget, int(position.split(".")[0]))
        widget._se_context_menu.tk_popup(event.x_root, event.y_root)
        return "break"

    def bind_mouse(widget):
        original_bind_mouse(widget)
        if sys.platform == "darwin":
            # Remote clients can deliver the secondary click as Button-3.
            widget.bind("<Button-3>", widget.on_secondary_click)

    EditorCodeViewText.on_secondary_click = secondary_click
    EditorCodeViewText._bind_mouse_aids = bind_mouse

    original_add = EditorNotebook.add
    original_update_title = EditorNotebook.update_editor_title

    @wraps(original_add)
    def add_tab(notebook, editor, **options):
        result = original_add(notebook, editor, **options)
        update_tab_icon(notebook, editor)
        return result

    @wraps(original_update_title)
    def update_title(notebook, editor):
        result = original_update_title(notebook, editor)
        update_tab_icon(notebook, editor)
        return result

    EditorNotebook.add = add_tab
    EditorNotebook.update_editor_title = update_title

    original_open = EditorNotebook._open_file

    @wraps(original_open)
    def open_file(notebook, filename):
        if not (is_model_path(filename) or uml_storage.is_model_path(filename)):
            return original_open(notebook, filename)
        editor = (UmlEditor if uml_storage.is_model_path(filename) else StructogramEditor)(notebook)
        try:
            if editor._load_file(filename):
                notebook.add(editor, text=editor.get_title())
                return editor
        except Exception:
            editor.destroy()
            raise
        editor.destroy()
        return None

    EditorNotebook._open_file = open_file
    # Diese Methoden werden von Run, Debug und Terminal-Run aufgerufen.
    Runner.execute_current = run_current_document(Runner.execute_current)
    for name in ("execute_editor_content", "_cmd_run_current_script_in_terminal"):
        setattr(Runner, name, guard_current_document(getattr(Runner, name)))

    # Bereits registrierte Befehle haben gebundene Handler/Tester. Daher deren
    # Verfügbarkeit und direkten Aufruf vor der Veröffentlichung ergänzen.
    for command in workbench._commands:
        if command["command_id"] in {
            "run_current_script", "run_current_script_in_terminal", "runresume",
            "debug_preferred", "debug_nicer", "debug_faster", "run_to_cursor",
            "goto_source_line",
        }:
            original_tester = command["tester"]

            is_run = command['command_id'] in ('run_current_script', 'runresume')
            def enabled(tester=original_tester, is_run=is_run):
                editor = workbench.get_editor_notebook().get_current_editor()
                if isinstance(editor, UmlEditor) and is_run:
                    return workbench._thonny_se_objects.session.can_run()
                return not active_graphical() and (tester is None or tester())

            command["tester"] = enabled
            command["handler"] = (run_current_document if is_run else guard_current_document)(command["handler"])

    def toolbar_history_available(action):
        editor = workbench.get_editor_notebook().get_current_editor()
        if editor is None or has_active_grab(workbench):
            return False
        if isinstance(editor, GraphicalDocument):
            return bool(getattr(editor, action + "_stack"))
        widget = editor.get_text_widget()
        return widget.tk.getboolean(widget.tk.call(widget._w, "edit", "can" + action))

    def toolbar_history(action):
        if not toolbar_history_available(action):
            return
        editor = workbench.get_editor_notebook().get_current_editor()
        if isinstance(editor, GraphicalDocument):
            getattr(editor, action)()
        else:
            editor.get_text_widget().event_generate("<<Undo>>" if action == "undo" else "<<Redo>>")

    # Thonnys vorhandene Menü-/Shortcut-Befehle verwenden denselben Verlauf.
    # Dialogfelder und Shell behalten ihre normalen Textaktionen.
    for command in workbench._commands:
        command_id = command["command_id"]
        if command_id in ("undo", "redo"):
            original = command["handler"]

            def history_dispatch(original=original, action=command_id):
                notebook = workbench.get_editor_notebook()
                editor = notebook.get_current_editor()
                focus = workbench.focus_get()
                in_editor = focus is None or focus in (workbench, notebook, editor) or (
                    editor is not None and str(focus).startswith(str(editor)+"."))
                toolbar_buttons = [workbench._toolbar_buttons.get(key) for key in _HISTORY_TOOLBAR_IDS]
                in_toolbar = focus is not None and focus in toolbar_buttons
                if isinstance(editor, GraphicalDocument) and not editor.is_text_editing(focus) and (in_editor or in_toolbar) and not has_active_grab(workbench):
                    getattr(editor, action)()
                elif in_toolbar and editor is not None and not has_active_grab(workbench):
                    editor.get_text_widget().event_generate("<<Undo>>" if action=="undo" else "<<Redo>>")
                else:
                    return original()

            original_tester = command["tester"]

            def history_available(action=command_id, original=original_tester):
                notebook = workbench.get_editor_notebook()
                editor = notebook.get_current_editor() if notebook else None
                if isinstance(editor, GraphicalDocument) and not has_active_grab(workbench):
                    focus = workbench.focus_get()
                    if editor.is_text_editing(focus):
                        return True
                    # Native Textaktionen bei Shell-Fokus nicht deaktivieren.
                    if focus is not None and not str(focus).startswith(str(editor)) and focus not in (
                            workbench, notebook, *(workbench._toolbar_buttons.get(key) for key in _HISTORY_TOOLBAR_IDS)):
                        return original is None or original()
                    return bool(editor.undo_stack if action=="undo" else editor.redo_stack)
                return original is None or original()

            command["handler"] = history_dispatch
            command["tester"] = history_available
            command["include_in_toolbar"] = True
            command["caption"] = command["command_label"]
            command["image"] = icon_path("edit."+command_id, size=16)

    # Nur den Öffnen-Dialog erweitern: Thonny verwendet seine Filterliste auch
    # beim Speichern von Python. Native macOS-Dialoge filtern nach .json statt
    # nach der zusammengesetzten Endung .tse.json.
    import thonny.editors
    original_open_dialog = thonny.editors.askopenfilename

    @wraps(original_open_dialog)
    def open_dialog(**options):
        original_types = list(options.get("filetypes", thonny.editors._dialog_filetypes))
        options["filetypes"] = [
            (tr('Python and diagrams'), ".py .pyw .pyi .pyde .pyx .json"),
            (tr('Structograms (*.nsd.json; legacy *.tse.json)'), ".json"),
            (tr('Thonny SE UML diagrams (*.uml.json)'), ".json"),
            *original_types,
        ]
        return original_open_dialog(**options)

    thonny.editors.askopenfilename = open_dialog

    workbench.add_command("thonny_se_new", "file", tr('New structogram'), new_structogram, group=10,
                          caption=tr('Structogram'), include_in_toolbar=True, image=icon_path("document.structogram", size=16))
    workbench.add_command("thonny_se_new_uml", "file", tr('New UML diagram'), new_uml, group=10,
                          caption="UML", include_in_toolbar=True, image=icon_path("document.uml", size=16))
    workbench.add_command("thonny_se_from_python", "edit", tr('Structogram from Python code'),
                          import_python, tester=active_python, group=90, image=icon_path("import.python", size=16))
    workbench.add_command("thonny_se_uml_from_python", "edit", _UML_IMPORT_LABEL,
                          import_python_uml, tester=active_python, group=90, image=icon_path("import.python", size=16))
    graphics = tk.Menu(workbench, tearoff=False)

    def update_graphic_menu():
        for index in range(3):
            graphics.entryconfigure(index, state="normal" if graphic_export_available() else "disabled")

    graphics.configure(postcommand=update_graphic_menu)
    for kind in ("png", "svg", "webp"):
        def export(kind=kind):
            editor = workbench.get_editor_notebook().get_current_editor()
            if isinstance(editor, GraphicalDocument) and graphic_export_available():
                editor.export_graphic(kind)
        graphics.add_command(label=kind.upper()+" …", command=export)
        workbench.add_command("thonny_se_export_"+kind, "file", tr('Export {format}').format(format=kind.upper()), export,
                              tester=graphic_export_available, include_in_menu=False, include_in_toolbar=True,
                              caption="WebP" if kind=="webp" else kind.upper(), image=icon_path("export."+kind, size=16))
    workbench.add_command("thonny_se_graphics", "file", tr('Export image as …'), handler=None,
                          submenu=graphics, tester=graphic_export_available, group=30, image=icon_path("export.image", size=16))
    # EditorNotebook registriert Neu erst nach dem Laden der Plugins.
    # Deshalb die Reihenfolge unmittelbar vor der Menüveröffentlichung festlegen.
    original_publish = workbench._publish_commands

    @wraps(original_publish)
    def publish_commands():
        new_command = next(c for c in workbench._commands if c["command_id"] == "thonny_se_new")
        workbench._commands.remove(new_command)
        position = next(i for i,c in enumerate(workbench._commands) if c["command_id"] == "new_file")
        workbench._commands.insert(position+1, new_command)
        uml_command = next(c for c in workbench._commands if c["command_id"] == "thonny_se_new_uml")
        workbench._commands.remove(uml_command)
        position = workbench._commands.index(new_command)
        workbench._commands.insert(position+1, uml_command)
        workbench._publish_commands = original_publish
        original_add_toolbar_button = workbench._add_toolbar_button
        deferred_history = []
        deferred_exports = []
        normal_groups = []

        @wraps(original_add_toolbar_button)
        def add_toolbar_button(command_id, image, disabled_image, command_label, caption,
                               alternative_caption, accelerator, handler, tester, toolbar_group):
            args = (command_id, image, disabled_image, command_label, caption,
                    alternative_caption, accelerator, handler, tester, toolbar_group)
            if command_id in ("undo", "redo"):
                deferred_history.append(args)
                return
            if command_id.startswith("thonny_se_export_"):
                deferred_exports.append(args)
                return
            normal_groups.append(toolbar_group)
            return original_add_toolbar_button(*args)

        workbench._add_toolbar_button = add_toolbar_button
        try:
            result = original_publish()
        finally:
            workbench._add_toolbar_button = original_add_toolbar_button
        toolbar = workbench._toolbar
        history_group = max(normal_groups, default=0)+2
        for args in deferred_history:
            action = args[0]
            original_add_toolbar_button(
                *args[:7], lambda action=action: toolbar_history(action),
                lambda action=action: toolbar_history_available(action), history_group
            )
        ttk.Separator(toolbar, orient="vertical").grid(row=0, column=history_group-1, sticky="ns", padx=(4, 6), pady=3)
        export_group = history_group+2
        ttk.Separator(toolbar, orient="vertical").grid(row=0, column=export_group-1, sticky="ns", padx=(4, 6), pady=3)
        for args in deferred_exports:
            original_add_toolbar_button(*args[:-1], export_group)
            workbench.get_toolbar_button(args[0]).configure(compound="left", width=0)
        install_theme_updates(workbench, graphics)
        # Tk updates the text undo stacks while processing these events.
        def refresh_text_history(event):
            workbench.after_idle(workbench._update_toolbar)

        for sequence in ("<<TextChange>>", "<<Undo>>", "<<Redo>>"):
            workbench.bind_class("EditorCodeViewText", sequence, refresh_text_history, True)

        # Auch mit Fokus auf der Hauptleiste bleiben die nativen Kürzel nutzbar.
        for key in _HISTORY_TOOLBAR_IDS:
            button = workbench.get_toolbar_button(key)
            for action, sequences in (
                    ("undo", ("<<Undo>>", "<Control-z>", "<Command-z>")),
                    ("redo", ("<<Redo>>", "<Control-y>", "<Command-y>", "<Control-Shift-Z>", "<Command-Shift-Z>"))):
                command = next(c for c in workbench._commands if c["command_id"] == action)
                def dispatch(event, command=command):
                    if command["tester"] is None or command["tester"]():
                        command["handler"]()
                    workbench._update_toolbar()
                    return "break"
                for sequence in sequences:
                    button.bind(sequence, dispatch)
        return result

    workbench._publish_commands = publish_commands
    _installed = True
