# SPDX-FileCopyrightText: 2026 Sebastian Ladhoff
# SPDX-License-Identifier: GPL-3.0-only
# See LICENSE in the project root for the full license text.

"""Plan explicit, selective updates of linked UML cards and Python files."""
import copy
from dataclasses import dataclass, field
from pathlib import Path

from .i18n import tr
from .uml_code_update import CodeSource, CodeUpdate
from .uml_import import parse_linked_class
from .uml_model import validate
from .uml_relationships import BASE_RELATIONSHIPS, base_relationship_kind, synchronized_inheritance, updated_inheritance
from .uml_source import plan_update, resolve_update

FROM_CODE = 'from_code'
TO_CODE = 'to_code'


def file_key(path):
    return str(Path(path).resolve())


@dataclass
class Entry:
    card: dict
    path: str = ''
    key: str = ''
    error: str = ''
    source: dict | None = None
    plan: object = None
    header: tuple | None = None
    action: str = ''
    file_error: bool = False

    @property
    def cid(self):
        return self.card['id']


@dataclass
class Batch:
    document: dict
    direction: str
    entries: list = field(default_factory=list)
    originals: dict = field(default_factory=dict)
    paths: dict = field(default_factory=dict)


def prepare(document, direction, read_source, *, cids=None):
    """Read each explicit linked file once; report unavailable cards individually."""
    if direction not in (FROM_CODE, TO_CODE):
        raise ValueError(direction)
    snapshot = copy.deepcopy(document)
    batch = Batch(snapshot, direction)
    effective = synchronized_inheritance(snapshot) if direction == TO_CODE else snapshot
    cards = {card['id']: card for card in effective['classes']}
    failures = {}
    analyses = {}
    for original in [*snapshot['classes'], *snapshot.get('removed_classes', [])]:
        if cids is not None and original['id'] not in cids:
            continue
        card = cards.get(original['id'], original)
        entry = Entry(card)
        batch.entries.append(entry)
        source = card.get('source')
        if source is None:
            entry.error = tr('No Python source file is linked to this class.')
            continue
        entry.path, entry.key = source['path'], file_key(source['path'])
        try:
            if entry.key in failures:
                raise ValueError(failures[entry.key])
            if entry.key not in batch.originals:
                try:
                    batch.originals[entry.key] = read_source(entry.path)
                    batch.paths[entry.key] = entry.path
                except (OSError, ValueError) as exc:
                    failures[entry.key] = str(exc)
                    raise
            text = batch.originals[entry.key]
            if entry.key not in analyses:
                analyses[entry.key] = CodeSource(text)
            analysis = analyses[entry.key]
            identities = {name for _, name in analysis.classes}
            removed = original['id'] not in cards
            if removed:
                if source['class'] not in identities:
                    entry.action = 'already_removed'
                    continue
                entry.source = analysis.linked(entry.path, source['class'])
                entry.action = 'delete_code' if direction == TO_CODE else 'restore_diagram'
            elif direction == FROM_CODE and source['class'] not in identities:
                entry.action = 'delete_diagram'
            elif direction == TO_CODE:
                entry.plan = CodeUpdate(text, card, analysis=analysis)
            else:
                incoming = analysis.linked(entry.path, source['class'])
                entry.source, entry.plan = plan_update(card, incoming)
                previous = source.get('header')
                current = card.get('header')
                previous_kind = source.get('class_kind', 'class')
                current_kind = card.get('class_kind', 'class')
                python_kind = incoming.get('class_kind', 'class')
                python = incoming['header']
                if (python, python_kind) != (current, current_kind):
                    conflict = (current is not None and (current, current_kind) != (previous, previous_kind)
                                and (python, python_kind) != (previous, previous_kind))
                    entry.header = ({**current, 'class_kind': current_kind} if current else None,
                                    {**python, 'class_kind': python_kind}, conflict)
        except (OSError, ValueError, RecursionError) as exc:
            entry.error = str(exc)
            entry.file_error = entry.key in failures
    return batch


def selected_entries(batch, choices):
    return [entry for entry in batch.entries if not entry.error and choices.get(entry.cid)]


def diagram_result(batch, choices, *, include_unchanged=False):
    """Build and validate the whole new diagram before changing the live tab."""
    result = copy.deepcopy(batch.document)
    changed = []
    entries = ([entry for entry in batch.entries if not entry.error and entry.cid in choices]
               if include_unchanged else selected_entries(batch, choices))
    for entry in entries:
        if entry.action:
            from .uml_class_changes import apply_diagram_class_change
            apply_diagram_class_change(result, entry)
            continue
        updated = resolve_update(entry.card, entry.source, entry.plan, choices[entry.cid])
        result['classes'] = [updated if card['id'] == entry.cid else card for card in result['classes']]
        changed.append((entry.card, updated))
    for previous, updated in changed:
        if updated.get('header') != previous.get('header'):
            old = previous.get('header', previous.get('source', {}).get('header', {})).get('bases', '')
            new = updated.get('header', {}).get('bases', '')
            result['relationships'] = updated_inheritance(result, updated['id'], old, new)
    for relation in result['relationships']:
        if relation['kind'] in BASE_RELATIONSHIPS:
            relation['kind'] = base_relationship_kind(result, relation['start'], relation['end'])
    return validate(result)


def change_key(change):
    return ('class',) if change.group == 'class' else ('header',) if change.group == 'header' else (
        change.section, change.row_id, change.group, change.old_name, change.new_name)


def _renamed(identity, renames):
    for before, after in renames:
        if identity == before or identity.startswith(before+'.'):
            identity = after+identity[len(before):]
    return identity


def code_result(batch, choices):
    """Replan selected edits on one evolving text per file, avoiding stale offsets.

    No live files are changed here. Standard-library imports are added only once.
    Parent class renames are applied before nested classes and their known links.
    """
    entries = selected_entries(batch, choices)
    bindings = set()
    for entry in entries:
        binding = entry.key, entry.card['source']['class']
        if binding in bindings:
            raise ValueError(tr('Several selected cards refer to the same Python class. Please select only one of them.'))
        bindings.add(binding)
    texts = {entry.key: batch.originals[entry.key] for entry in entries}
    result = copy.deepcopy(batch.document)
    cards = {card['id']: card for card in result['classes']}
    renames = {key: [] for key in texts}
    for entry in sorted(entries, key=lambda item: item.card['source']['class'].count('.')):
        if entry.action == 'delete_code':
            from .uml_class_changes import delete_class_code
            identity = _renamed(entry.card['source']['class'], renames[entry.key])
            texts[entry.key] = delete_class_code(texts[entry.key], identity)
            result['removed_classes'] = [card for card in result.get('removed_classes', []) if card['id'] != entry.cid]
            continue
        desired = copy.deepcopy(entry.card)
        desired['source']['class'] = _renamed(desired['source']['class'], renames[entry.key])
        plan = CodeUpdate(texts[entry.key], desired)
        available = {change_key(change): change for change in [plan.header, *plan.changes]}
        selected = []
        for preview in choices[entry.cid]:
            current = available.get(change_key(preview))
            if current is None or not current.selectable:
                raise ValueError(tr('These changes cannot be combined. Please update the affected classes separately.'))
            selected.append(current)
        text, _ = plan.apply(selected)
        source = plan.updated_source(text, selected)
        if source['class'] != desired['source']['class']:
            renames[entry.key].append((desired['source']['class'], source['class']))
        cards[entry.cid]['source'] = source
        texts[entry.key] = text
    for card in result['classes']:
        source = card.get('source')
        if source is not None and (key := file_key(source['path'])) in renames:
            source['class'] = _renamed(source['class'], renames[key])
    validate(result)
    return texts, result


def prepare_relink(document, path, text):
    """Match exact class identities in one explicit file, without changing code."""
    snapshot = copy.deepcopy(document)
    batch = Batch(snapshot, FROM_CODE)
    key = file_key(path)
    batch.originals[key], batch.paths[key] = text, path
    analysis = CodeSource(text)
    for card in snapshot['classes']:
        entry = Entry(card, path=path, key=key)
        batch.entries.append(entry)
        identity = card.get('header', {}).get('name', card['name'])
        try:
            incoming = analysis.linked(path, identity)
        except ValueError as exc:
            entry.error = str(exc)
            continue
        header = card.get('header', {'name': card['name'], 'bases': ''})
        card['source'] = {'path': path, 'class': identity, 'header': copy.deepcopy(header),
                          'baseline': {'attributes': [], 'methods': []}}
        if card.get('class_kind'):
            card['source']['class_kind'] = card['class_kind']
        entry.source, entry.plan = plan_update(card, incoming, first_link=True)
        current_kind = card.get('class_kind', 'class')
        incoming_kind = incoming.get('class_kind', 'class')
        if (header, current_kind) != (incoming['header'], incoming_kind):
            entry.header = ({**header, 'class_kind': current_kind},
                            {**incoming['header'], 'class_kind': incoming_kind}, True)
    return batch
