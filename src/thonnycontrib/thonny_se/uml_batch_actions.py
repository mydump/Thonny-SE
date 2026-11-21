# SPDX-FileCopyrightText: 2026 Sebastian Ladhoff
# SPDX-License-Identifier: GPL-3.0-only
# See LICENSE in the project root for the full license text.

"""Apply a confirmed batch to one UML undo step or native Python editor tabs."""
from difflib import SequenceMatcher
import tkinter as tk
from pathlib import Path
from tkinter import messagebox

from .i18n import tr
from .integration import read_python_source
from .uml_batch import FROM_CODE, TO_CODE, code_result, diagram_result, prepare, selected_entries
from .uml_batch_dialog import BatchUpdateDialog, title


def _patch_widget(widget, original, result):
    """Use one native undo group, preserving unchanged text and editor markings."""
    if original == result:
        return
    patches = [(start,end,result[new_start:new_end])
               for kind,start,end,new_start,new_end in SequenceMatcher(None,original,result,autojunk=False).get_opcodes()
               if kind != 'equal']

    def index(offset):
        line = original.count('\n',0,offset)+1
        prefix = original[original.rfind('\n',0,offset)+1:offset]
        return f"{line}.{widget.tk.call('string','length',prefix)}"

    autoseparators,suppress = widget.cget('autoseparators'),widget._suppress_events
    widget.edit_separator()
    widget.configure(autoseparators=False)
    widget._suppress_events = True
    try:
        for start,end,text in reversed(patches):
            first,last = index(start),index(end)
            if first != last:
                widget.direct_delete(first,last)
            if text:
                widget.direct_insert(first,text)
        if widget.get('1.0','end-1c') != result:
            raise ValueError(tr('The changes could not be fully applied in the editor.'))
    except (ValueError,tk.TclError):
        if widget.get('1.0','end-1c') != original:
            widget.edit_undo()
        raise
    finally:
        widget._suppress_events = suppress
        widget.configure(autoseparators=autoseparators)
        widget.edit_separator()


def apply_python_tabs(editor, batch, texts):
    """Check every target before editing any; roll back this batch on failure."""
    targets = []
    for key,result in texts.items():
        original = batch.originals[key]
        if result == original:
            continue
        target = editor.notebook.show_file(batch.paths[key])
        if target is None:
            raise ValueError(batch.paths[key]+'\n'+tr('Could not open the Python file.'))
        widget = target.get_text_widget()
        if widget.is_read_only():
            raise ValueError(batch.paths[key]+'\n'+tr('The Python file is read-only in the editor.'))
        if widget.get('1.0','end-1c') != original:
            raise ValueError(batch.paths[key]+'\n'+tr('The Python file has changed since the preview. Please reopen the preview.'))
        targets.append((target,widget,original,result))
    applied = []
    try:
        for target,widget,original,result in targets:
            _patch_widget(widget,original,result)
            applied.append((target,widget,original))
    except (ValueError,tk.TclError):
        for target,widget,original in reversed(applied):
            suppress = widget._suppress_events
            widget._suppress_events = True
            try:
                widget.edit_undo()
                target.update_title()
            finally:
                widget._suppress_events = suppress
        raise
    for target,widget,original in applied:
        widget.event_generate('<<TextChange>>')
        target.update_title()


def ensure_source_files(editor, cids=None):
    """A named, unsaved buffer is not yet a persistent source link."""
    checked = set()
    for card in [*editor.document['classes'], *editor.document.get('removed_classes', [])]:
        source = card.get('source')
        if not source or cids is not None and card['id'] not in cids:
            continue
        path = source['path']
        if path in checked:
            continue
        checked.add(path)
        opened = editor.notebook.get_editor(path)
        if opened is None or Path(path).is_file():
            continue
        if not messagebox.askokcancel(tr('Save Python source'),
                tr('The linked Python file does not exist on disk yet. Save it before reviewing changes?')+'\n'+path,
                parent=editor):
            return False
        editor.notebook.select(opened)
        opened.save_file()
        if not Path(path).is_file():
            return False
    return True


def update(editor, direction, *, cids=None):
    if not editor.diagram.finish_edit():
        return
    before = editor._snapshot()
    try:
        if not ensure_source_files(editor, cids):
            return
        batch = prepare(editor.document,direction,read_python_source,cids=cids)
        dialog = BatchUpdateDialog(editor,batch)
        if dialog.relink_cids is not None:
            if relink(editor, cids=dialog.relink_cids):
                update(editor, direction, cids=cids)
            return
        choices = dialog.result
        if choices is None or not selected_entries(batch,choices):
            return
        if editor.document != before[0]:
            raise ValueError(tr('The diagram has changed since the preview. Please reopen the preview.'))
        keys = {entry.key for entry in selected_entries(batch,choices)}
        for key in keys:
            if read_python_source(batch.paths[key]) != batch.originals[key]:
                raise ValueError(batch.paths[key]+'\n'+tr('The Python file has changed since the preview. Please reopen the preview.'))
        if direction == FROM_CODE:
            candidate = diagram_result(batch,choices)
        else:
            texts,candidate = code_result(batch,choices)
            apply_python_tabs(editor,batch,texts)
        editor.document = candidate
        editor._record(before)
    except (OSError,ValueError,RecursionError,tk.TclError) as exc:
        messagebox.showerror(title(direction),str(exc),parent=editor)


def relink(editor, *, cids=None):
    """Link matching diagram cards to one chosen file after explicit review."""
    from tkinter import filedialog
    from .uml_batch import prepare_relink
    label = tr('Assign Python source file to diagram')
    if not editor.diagram.finish_edit():
        return
    path = filedialog.askopenfilename(parent=editor, title=label,
        initialdir=str(Path(editor.get_filename()).parent) if editor.get_filename() else None,
        filetypes=[(tr('Python files'), '*.py')])
    if not path:
        return
    before = editor._snapshot()
    try:
        text = read_python_source(path)
        batch = prepare_relink(editor.document, path, text)
        if cids is not None:
            batch.entries = [entry for entry in batch.entries if entry.cid in cids]
        if not any(not entry.error for entry in batch.entries):
            errors = '\n'.join(entry.error for entry in batch.entries)
            raise ValueError(tr('No diagram classes could be matched in this Python file.')+'\n'+errors)
        choices = BatchUpdateDialog(editor, batch, caption=label, allow_empty=True, full=True).result
        if choices is None:
            return
        if editor.document != before[0]:
            raise ValueError(tr('The diagram has changed since the preview. Please reopen the preview.'))
        if read_python_source(path) != text:
            raise ValueError(tr('The Python file has changed since the preview. Please reopen the preview.'))
        candidate = diagram_result(batch, choices, include_unchanged=True)
        editor.document = candidate
        editor._record(before)
        editor.source_status.schedule()
        return True
    except (OSError, ValueError, RecursionError, tk.TclError) as exc:
        messagebox.showerror(label, str(exc), parent=editor)
