# SPDX-FileCopyrightText: 2026 Sebastian Ladhoff
# SPDX-License-Identifier: GPL-3.0-only
# See LICENSE in the project root for the full license text.

"""Explicit whole-class deletion/restoration in the ordinary transfer preview."""
import ast
import copy

from .i18n import tr
from .uml_import import _classes, parse_tree
from .uml_methods import member_text, visible_methods


def class_review_rows(entry, direction):
    from .uml_batch import TO_CODE
    from .uml_code_update import Change
    from .uml_review import ReviewRow, header_text
    card = entry.source or entry.card
    if entry.action == 'already_removed':
        return ReviewRow(None, 'header', '', '', note=tr('The class has already been removed from the source.')), []
    restoring = entry.action == 'restore_diagram'
    kind = 'add' if restoring else 'delete'
    note = (tr('The class was removed from the diagram. Select it to restore it from Python.') if restoring else
            tr('This class is no longer in the diagram. Selecting its heading deletes the entire Python class and its implementation. Call sites are not changed.') if entry.action == 'delete_code' else
            tr('This class is no longer in the Python source. Selecting its heading removes the class card from the diagram.'))
    key = Change('class', header_text(card), patch=(0, 0, ''), note=note) if direction == TO_CODE else ('class', 0)
    header = ReviewRow(key, 'header', '' if restoring else header_text(card),
                       header_text(card) if restoring else '', kind, False, True, note=note)
    rows = []
    for section in ('attributes', 'methods'):
        members = visible_methods(card) if section == 'methods' else card[section]
        for row in members:
            text = member_text(row, card['name'])
            rows.append(ReviewRow(None, section, '' if restoring else text,
                                  text if restoring else '', kind, note=note))
    return header, rows


def apply_diagram_class_change(document, entry):
    if entry.action == 'restore_diagram':
        card = copy.deepcopy(entry.source)
        card.update(id=entry.cid, x=entry.card['x'], y=entry.card['y'])
        document['classes'].append(card)
        document['removed_classes'] = [item for item in document.get('removed_classes', []) if item['id'] != entry.cid]
    elif entry.action == 'delete_diagram':
        document['classes'] = [item for item in document['classes'] if item['id'] != entry.cid]
        document['relationships'] = [item for item in document['relationships']
                                     if entry.cid not in (item['start'], item['end'])]
        for note in document['comments']:
            if note['target'] == entry.cid:
                note['target'] = None


def delete_class_code(text, identity):
    """Remove exactly the linked AST definition, leaving enclosing suites valid."""
    tree = parse_tree(text)
    matches = [node for node, name in _classes(tree) if name == identity]
    if not matches:
        # A selected outer class may already have removed this nested class.
        return text
    if len(matches) != 1:
        raise ValueError(tr('The class is defined more than once. Please edit it directly in Python.'))
    node = matches[0]
    lines = text.splitlines(keepends=True)
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line))
    def offset(line, column):
        return offsets[line-1] + len(lines[line-1].encode('utf-8')[:column].decode('utf-8'))
    first = min([node, *node.decorator_list], key=lambda part: (part.lineno, part.col_offset))
    start = offset(first.lineno, node.col_offset)
    end = offset(node.end_lineno, node.end_col_offset)
    parent = next((part for part in ast.walk(tree)
                   if any(isinstance(value, list) and node in value for value in vars(part).values())), None)
    alone = parent is not None and not isinstance(parent, ast.Module) and any(
        isinstance(value, list) and value == [node] for value in vars(parent).values())
    replacement = 'pass' if alone else ''
    # Include decorator @, but leave comments and adjacent definitions untouched.
    result = text[:start] + replacement + text[end:]
    parse_tree(result)
    return result
