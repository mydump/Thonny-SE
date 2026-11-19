# SPDX-FileCopyrightText: 2026 Sebastian Ladhoff
# SPDX-License-Identifier: GPL-3.0-only
# See LICENSE in the project root for the full license text.

"""Prepare explicit, unsaved diagram execution while retaining Python bodies."""
import ast
import copy
import hashlib
import json
from pathlib import Path

from .i18n import tr
from .uml_batch import TO_CODE, prepare, code_result
from .uml_code_update import changes_code


def diagram_fingerprint(document):
    """Only code-relevant structure; never positions, comments, IDs or view options."""
    cards = []
    names = {card['id']: card.get('header', {}).get('name', card['name']) for card in document['classes']}
    for card in document['classes']:
        attributes = {row['id']: row.get('attribute', {}).get('name', row.get('text', '')) for row in card['attributes']}
        state = dict(header=card.get('header', {'name':card['name'], 'bases':''}),
                     class_kind=card.get('class_kind', 'class'))
        for section in ('attributes', 'methods'):
            state[section] = []
            for row in card[section]:
                value = {key: item for key, item in row.items() if key != 'id' and not (key == 'abstract' and item is False)}
                if 'accessor' in value:
                    value['accessor'] = {**value['accessor'], 'attribute': attributes.get(value['accessor']['attribute'])}
                state[section].append(value)
        cards.append(state)
    bases = [(relation['kind'], names.get(relation['start']), names.get(relation['end']))
             for relation in document['relationships'] if relation['kind'] in ('inheritance', 'realization')]
    return hashlib.sha256(json.dumps((cards, bases), sort_keys=True).encode('utf-8')).hexdigest()


def module_source(path, text):
    path = Path(path).resolve()
    parts = [] if path.name == '__init__.py' else [path.stem]
    directory = path.parent
    while (directory/'__init__.py').is_file():
        parts.insert(0, directory.name)
        directory = directory.parent
    return dict(name='.'.join(parts), filename=str(path), text=text,
                package=path.name == '__init__.py', root=str(directory))


def prepare_execution(document, cid, read_source, *, token, label=None):
    """Return code snapshots and original texts; never mutate document or files."""
    from .uml_codegen import generate_diagram
    from .uml_relationships import synchronized_inheritance
    from .uml_review import review_rows
    effective = synchronized_inheritance(copy.deepcopy(document))
    linked = [card['id'] for card in [*effective['classes'], *effective.get('removed_classes', [])] if card.get('source')]
    def checked_source(path):
        text = read_source(path)
        compile(text, path, 'exec')
        return text
    batch = prepare(effective, TO_CODE, checked_source, cids=set(linked))
    choices = {}
    for entry in batch.entries:
        if entry.error:
            raise ValueError(entry.path+'\n'+entry.error)
        if entry.action == 'already_removed':
            continue
        if entry.action == 'delete_code':
            header, _ = review_rows(entry, TO_CODE)
            choices[entry.cid] = [header.key]
            continue
        wanted = [change for change in [entry.plan.header,*entry.plan.changes] if changes_code(change,entry.plan.source)]
        blocked = [change for change in wanted if not change.selectable]
        if blocked:
            raise ValueError(entry.card['name']+': '+(blocked[0].note or tr('Please resolve this change in Python before running.')))
        choices[entry.cid] = wanted
    texts, candidate = code_result(batch, choices)
    all_texts = {**batch.originals, **texts}
    sources = [module_source(batch.paths[key], text) for key, text in all_texts.items()]
    by_name = {item['name']: item for item in sources}
    if len(by_name) != len(sources):
        raise ValueError(tr('Two source files use the same Python module name. Use distinct module names.'))
    new_cards = [card for card in candidate['classes'] if not card.get('source')]
    generated_name = '_thonny_se_diagram_'+token
    if new_cards:
        from .uml_codegen import class_header
        names = {node.id for card in new_cards for node in ast.walk(ast.parse(class_header(card.get('header', {'name':card['name'],'bases':''}))+'\n    pass')) if isinstance(node,ast.Name)}
        # Known inheritance links can refer to an explicitly linked class.
        imports = []
        for card in candidate['classes']:
            source = card.get('source')
            if source and '.' not in source['class'] and source['class'] in names:
                module = module_source(source['path'], '')['name']
                imports.append('from '+module+' import '+source['class'])
        text = 'from __future__ import annotations\n'+'\n'.join(imports)+'\n'+generate_diagram(new_cards)
        sources.append(dict(name=generated_name, filename='<Thonny SE: '+(label or token)+'>', text=text, package=False, root=''))
    targets = {}
    for card in candidate['classes']:
        source = card.get('source')
        targets[card['id']] = dict(module=module_source(source['path'], '')['name'] if source else generated_name,
                                  identity=source['class'] if source else card.get('header', {}).get('name', card['name']))
    target = targets.get(cid, {})
    return dict(sources=sources, targets=targets, module=target.get('module'), identity=target.get('identity'),
                originals={batch.paths[key]: text for key, text in batch.originals.items()})
