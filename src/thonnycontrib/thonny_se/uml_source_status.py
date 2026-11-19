# SPDX-FileCopyrightText: 2026 Sebastian Ladhoff
# SPDX-License-Identifier: GPL-3.0-only
# See LICENSE in the project root for the full license text.

"""Cached per-class persistence indicators, independent of diagram rendering."""
import json
from pathlib import Path

from .i18n import tr
from .integration import read_python_source
from .uml_code_update import CodeSource, CodeUpdate, changes_code


MESSAGES = {
    'new': tr('This class has no Python file yet. Click to save its code.'),
    'changed': tr('The class and Python code differ. Diagram changes are only applied to the Python file when transferred. Click to review the transfer.'),
    'unsaved': tr('The Python code has not been saved. Click to save the file.'),
    'missing': tr('The Python source is unavailable. Click to relink the class.'),
}


class SourceStatus:
    def __init__(self, editor):
        self.editor = editor
        self.states = {}
        self.cache = {}
        self.files = {}
        self._effective_key = None
        self._effective_document = None
        self.job = self.poll_job = None
        editor.bind('<Destroy>', self.close, add=True)
        self.schedule()
        self.poll_job = editor.after(1000, self.poll)

    def schedule(self):
        if self.job is None:
            self.job = self.editor.after_idle(self.refresh)

    def poll(self):
        self.poll_job = None
        self.schedule()
        self.poll_job = self.editor.after(1000, self.poll)

    def _text(self, path):
        opened = self.editor.notebook.get_editor(path)
        if opened is not None:
            return opened.get_text_widget().get('1.0', 'end-1c'), opened.is_modified()
        stat = Path(path).stat()
        stamp = stat.st_mtime_ns, stat.st_size
        previous = self.files.get(path)
        if previous is None or previous[0] != stamp:
            self.files[path] = stamp, read_python_source(path)
        return self.files[path][1], False

    def _effective_classes(self):
        from .uml_relationships import BASE_RELATIONSHIPS, synchronized_inheritance
        document = self.editor.document
        semantic = {'classes': [{key: value for key, value in card.items() if key not in ('x', 'y')}
                                for card in document['classes']],
                    'relationships': [{key: relation[key] for key in ('start', 'end', 'kind')}
                                      for relation in document['relationships'] if relation['kind'] in BASE_RELATIONSHIPS]}
        key = json.dumps(semantic, sort_keys=True)
        if key != self._effective_key:
            try:
                self._effective_document = synchronized_inheritance(document)
            except (ValueError, RecursionError):
                # Per-class validation below still reports unavailable/invalid code.
                self._effective_document = document
            self._effective_key = key
        return self._effective_document['classes']

    def refresh(self):
        self.job = None
        states, read, analyses = {}, {}, {}
        used = set()
        for card in self._effective_classes():
            cid, source = card['id'], card.get('source')
            if not source:
                states[cid] = 'new'
                continue
            path = source['path']
            try:
                if path not in read:
                    read[path] = self._text(path)
                text, unsaved = read[path]
                semantic = {key: value for key, value in card.items() if key not in ('x', 'y')}
                key = json.dumps(semantic, sort_keys=True), text
                previous = self.cache.get(cid)
                if previous is None or previous[0] != key:
                    if path not in analyses:
                        analyses[path] = CodeSource(text)
                    plan = CodeUpdate(text, card, analysis=analyses[path])
                    differs = any(changes_code(change,text) for change in [plan.header,*plan.changes])
                    self.cache[cid] = key, differs
                states[cid] = 'changed' if self.cache[cid][1] else 'unsaved' if unsaved else ''
                used.add(cid)
            except (OSError, ValueError, RecursionError):
                states[cid] = 'changed' if path in read else 'missing'
        self.cache = {cid: value for cid, value in self.cache.items() if cid in used}
        if states != self.states:
            self.states = states
            self.editor.diagram.draw()

    def close(self, event):
        if event.widget is not self.editor:
            return
        for job in (self.job, self.poll_job):
            if job is not None:
                self.editor.after_cancel(job)
        self.job = self.poll_job = None
