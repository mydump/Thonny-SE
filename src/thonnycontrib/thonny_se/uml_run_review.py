# SPDX-FileCopyrightText: 2026 Sebastian Ladhoff
# SPDX-License-Identifier: GPL-3.0-only
"""Explicit decisions before preparing a new diagram interpreter session."""
import copy
from collections import OrderedDict
from pathlib import Path
from tkinter import font, ttk

from .dialogs import EditDialog
from .i18n import tr
from .uml_batch import TO_CODE, file_key, prepare
from .uml_code_update import changes_code
from .uml_runtime import prepare_execution


def checked_document(document, reader, choose, reconcile):
    """Return a run-only document and source snapshot, or None on cancellation."""
    current = copy.deepcopy(document)
    texts, missing = {}, OrderedDict()
    for card in [*current['classes'], *current.get('removed_classes', [])]:
        source = card.get('source')
        if not source:
            continue
        path = source['path']
        key = file_key(path)
        if key in texts:
            continue
        if key in missing:
            missing[key][1].append(card['name'])
            continue
        try:
            texts[key] = reader(path)
        except (OSError, ValueError) as error:
            cause = error.__cause__ or error
            if not isinstance(cause, OSError):
                raise
            missing[key] = (path, [card['name']])
    if missing:
        if choose('missing', list(missing.values())) != 'model':
            return None
        for card in current['classes']:
            if card.get('source') and file_key(card['source']['path']) in missing:
                card.pop('source')
        current['removed_classes'] = [card for card in current.get('removed_classes', [])
                                     if not card.get('source') or file_key(card['source']['path']) not in missing]
    def snapshot(path):
        return texts[file_key(path)]
    linked = {card['id'] for card in [*current['classes'], *current.get('removed_classes', [])] if card.get('source')}
    from .uml_relationships import synchronized_inheritance
    batch = prepare(synchronized_inheritance(current), TO_CODE, snapshot, cids=linked)
    differences = OrderedDict()
    for entry in batch.entries:
        if entry.error:
            raise ValueError(entry.path+'\n'+entry.error)
        changed = entry.action not in ('', 'already_removed') or (entry.plan is not None and any(
            changes_code(change, entry.plan.source) for change in [entry.plan.header, *entry.plan.changes]))
        if changed:
            differences.setdefault(entry.key, (entry.path, []))[1].append(entry.card['name'])
    if differences:
        decision = choose('different', list(differences.values()))
        if decision == 'reconcile':
            return 'recheck' if reconcile() else None
        if decision != 'run':
            return None
    return current, snapshot


class RunReviewDialog(EditDialog):
    def __init__(self, parent, kind, files):
        self.kind, self.files, self.result = kind, files, None
        super().__init__(parent, tr('Run diagram'))

    def build_body(self, master):
        self.title_font = font.nametofont('TkDefaultFont').copy()
        self.title_font.configure(size=self.title_font.actual('size')+3,weight='bold')
        self.file_font = font.nametofont('TkDefaultFont').copy()
        self.file_font.configure(weight='bold')
        self.path_font = font.nametofont('TkDefaultFont').copy()
        self.path_font.configure(size=max(9,self.path_font.actual('size')-1))
        if self.kind == 'missing':
            heading = tr('Python files cannot be opened')
            explanation = tr('The following classes are linked to files that are no longer accessible:')
            consequence = tr('You can run these classes from the diagram for now. The code inside their Python methods will be missing. Their file links will stay unchanged.')
        else:
            heading = tr('Classes differ from the Python code')
            explanation = tr('The following classes do not match their Python files:')
            consequence = tr('Run anyway: use the classes as shown in the diagram, keeping the method code from the Python files. Or review and transfer the changes first. Running does not save changes to Python files.')
        ttk.Label(master,text=heading,font=self.title_font,wraplength=560,justify='left').pack(anchor='w',pady=(0,10))
        ttk.Label(master,text=explanation,wraplength=560,justify='left').pack(anchor='w',pady=(0,12))
        from thonny.ui_utils import VerticallyScrollableFrame
        from .scrolling import ScrollArea
        from .iconregistry import menu_icon
        from .tooltips import attach_tip
        from .ui_style import MUTED, ui_color
        from thonny import get_workbench
        area = VerticallyScrollableFrame(master)
        area.canvas.configure(width=560,height=min(260,max(95,len(self.files)*90)),
                              background=ttk.Style(self).lookup('TFrame','background'))
        area.pack(fill='both',expand=True)
        for index,(path,names) in enumerate(self.files):
            if index:
                ttk.Separator(area.interior).pack(fill='x',pady=(0,10))
            row=ttk.Frame(area.interior,padding=(0,0,8,12))
            row.pack(fill='x')
            icon=ttk.Label(row,image=menu_icon(get_workbench(),'document.python'))
            icon.grid(row=0,column=0,sticky='n',padx=(0,8),pady=2)
            ttk.Label(row,text=Path(path).name,font=self.file_font,wraplength=510,
                      justify='left').grid(row=0,column=1,sticky='w')
            ttk.Label(row,text=tr('Affected classes: {names}').format(names=', '.join(names)),
                      wraplength=510,justify='left').grid(row=1,column=1,sticky='w',pady=(4,3))
            folder=str(Path(path).parent)
            clipped=folder
            while clipped and self.path_font.measure(clipped)>510:
                clipped='…'+clipped[2:] if clipped.startswith('…') else '…'+clipped[1:]
            path_label=ttk.Label(row,text=clipped,font=self.path_font,foreground=ui_color(MUTED))
            path_label.grid(row=2,column=1,sticky='w')
            attach_tip(path_label,str(path))
        self.scrolling = ScrollArea(area.canvas,area,axes='y')
        ttk.Separator(master).pack(fill='x',pady=(12,10))
        ttk.Label(master,text=consequence,wraplength=560,justify='left').pack(anchor='w')

    def buttonbox(self):
        row=ttk.Frame(self,padding=(16,8,16,14));row.pack(fill='x')
        row.columnconfigure(0,weight=1)
        self._action_button(row,1,tr('Cancel'),self.cancel,gap=8)
        if self.kind == 'missing':
            self._action_button(row,2,tr('Use model'),lambda:self.accept('model'))
        else:
            self._action_button(row,2,tr('Review differences …'),lambda:self.accept('reconcile'),gap=8)
            self._action_button(row,3,tr('Run anyway'),lambda:self.accept('run'))
        self.bind('<Escape>',self.cancel)

    def accept(self,value):
        self.result=value
        self.cancel()


def reviewed_execution(editor, reader, *, token, label):
    from .uml_batch_actions import update
    while True:
        prepared=checked_document(editor.document,reader,
            lambda kind,files:RunReviewDialog(editor,kind,files).result,
            lambda:update(editor,TO_CODE))
        if prepared is None:
            return None
        if prepared == 'recheck':
            continue
        document,snapshot=prepared
        return prepare_execution(document,None,snapshot,token=token,label=label)
