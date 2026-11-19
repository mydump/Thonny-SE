# SPDX-FileCopyrightText: 2026 Sebastian Ladhoff
# SPDX-License-Identifier: GPL-3.0-only
# See LICENSE in the project root for the full license text.

"""Resolve a card's original source identity to a current Python text position."""
import ast

from .i18n import tr
from .uml_import import parse_tree, linked_class_node, constructor_receiver, instance_assignments
from .uml_methods import attribute_draft, draft_from_row, is_constructor
from .uml_codegen import _member_name


def code_location(source, card, section='name', row_id=None):
    node = linked_class_node(parse_tree(source), card['source']['class'])
    if section in ('attributes', 'methods'):
        row = next((row for row in card[section] if row['id'] == row_id), None)
        if row is None:
            raise ValueError(tr('This element has no corresponding source location yet.'))
        baseline = next((entry for entry in card['source'].get('baseline', {}).get(section, [])
                         if entry['id'] == row_id), {})
        names = [baseline['name']] if baseline.get('name') else []
        try:
            if section == 'methods' and is_constructor(row):
                name = '__init__'
            else:
                data = attribute_draft(row) if section == 'attributes' else draft_from_row(row)[0]
                name = _member_name(data)
            if name not in names:
                names.append(name)
        except ValueError:
            if not names:
                raise
        target = None
        for name in names:
            if section == 'methods':
                matches = [member for member in node.body
                           if isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef)) and member.name == name]
                if len(matches) > 1:
                    raise ValueError(tr('This method is defined more than once in the source.'))
            else:
                matches = []
                for member in node.body:
                    receiver = constructor_receiver(member)
                    if receiver is not None:
                        matches.extend(attribute for _,attribute in instance_assignments(member.body, receiver)
                                       if attribute.attr == name)
            if matches:
                target = min(matches,key=lambda item:(item.lineno,item.col_offset))
                break
        if target is None:
            raise ValueError(tr('This element was not found in the linked Python class. Transfer the changes or check the source link.'))
        node = target
    # AST columns count UTF-8 bytes, whereas Tk's insertion positions count characters.
    line = source.splitlines()[node.lineno-1]
    column = len(line.encode('utf-8')[:node.col_offset].decode('utf-8'))
    return node.lineno, column
