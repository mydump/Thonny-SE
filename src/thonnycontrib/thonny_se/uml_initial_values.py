# SPDX-FileCopyrightText: 2026 Sebastian Ladhoff
# SPDX-License-Identifier: GPL-3.0-only
"""Bounded static checking of initial values; never execute student expressions."""
import ast
from .i18n import tr
from .uml_methods import MemberFieldError

DEFAULTS = {'str': '""', 'int': '0', 'float': '0.0', 'bool': 'False',
            'dict': '{}', 'list': '[]', 'tuple': '()', 'set': 'set()',
            'frozenset': 'frozenset()', 'bytes': 'b""', 'complex': '0j'}


def initial_value_for_type(typename):
    return DEFAULTS.get(typename.strip().split('[', 1)[0])


def _name(node):
    return ast.unparse(node).strip()


def _matches(annotation, expression, assignable):
    if isinstance(annotation, ast.Constant) and isinstance(annotation.value, str):
        return _matches(ast.parse(annotation.value, mode='eval').body, expression, assignable)
    if isinstance(annotation, ast.BinOp) and isinstance(annotation.op, ast.BitOr):
        return _matches(annotation.left, expression, assignable) or _matches(annotation.right, expression, assignable)
    if isinstance(annotation, ast.Subscript):
        name = _name(annotation.value).removeprefix('typing.')
        args = list(annotation.slice.elts) if isinstance(annotation.slice, ast.Tuple) else [annotation.slice]
        if name in ('Optional', 'Union'):
            return ((name == 'Optional' and isinstance(expression, ast.Constant) and expression.value is None)
                    or any(_matches(arg, expression, assignable) for arg in args))
        aliases = {'List': 'list', 'Dict': 'dict', 'Tuple': 'tuple', 'Set': 'set', 'FrozenSet': 'frozenset'}
        name = aliases.get(name, name)
        if not _matches(ast.Name(id=name), expression, assignable):
            return False
        if isinstance(expression, (ast.List, ast.Tuple, ast.Set)):
            if name == 'tuple' and len(args) == 2 and isinstance(args[1], ast.Constant) and args[1].value is Ellipsis:
                return all(_matches(args[0], item, assignable) for item in expression.elts)
            if name == 'tuple':
                return len(args) == len(expression.elts) and all(_matches(a, e, assignable) for a, e in zip(args, expression.elts))
            return all(_matches(args[0], item, assignable) for item in expression.elts)
        if isinstance(expression, ast.Dict) and len(args) == 2:
            return all(_matches(args[0], k, assignable) and _matches(args[1], v, assignable) for k, v in zip(expression.keys, expression.values))
        return True  # e.g. an empty list() or dict() constructor
    name = _name(annotation).removeprefix('builtins.').removeprefix('typing.')
    if name in ('Any', 'object'):
        return True
    container_nodes = {'list': ast.List, 'dict': ast.Dict, 'tuple': ast.Tuple, 'set': ast.Set}
    if name in container_nodes and isinstance(expression, container_nodes[name]):
        return True
    if isinstance(expression, ast.Call):
        called = _name(expression.func).removeprefix('builtins.')
        if called in DEFAULTS:
            # Only empty container constructors; no execution/conversion guesses.
            return name == called and called in ('list','dict','tuple','set','frozenset') and not expression.args and not expression.keywords
        return assignable(called, name)  # Also honor diagram inheritance/polymorphism.
    try:
        value = ast.literal_eval(expression)
    except (ValueError, TypeError):
        raise ValueError(tr('This expression cannot be checked without running code. Use a literal value or turn off initial-value checking.'))
    types = {'str': str, 'int': int, 'float': float, 'bool': bool, 'list': list, 'dict': dict,
             'tuple': tuple, 'set': set, 'frozenset': frozenset, 'bytes': bytes, 'complex': complex,
             'None': type(None), 'NoneType': type(None)}
    if name in types:
        actual = type(value)
        if name == 'float':
            return actual in (int, float)
        if name == 'complex':
            return actual in (int, float, complex)
        return actual is types[name]
    # Object-reference attributes may start as None, before an object is assigned.
    return value is None


def _assignable_classes(document):
    bases = {}
    if document:
        cards = {card['id']: card for card in document['classes']}
        for relation in document.get('relationships', ()):
            if relation['kind'] in ('inheritance', 'realization'):
                child, parent = cards[relation['start']]['name'], cards[relation['end']]['name']
                bases.setdefault(child, set()).add(parent)
        for card in cards.values():
            header = card.get('header', card.get('source', {}).get('header', {}))
            try:
                nodes = ast.parse('['+header.get('bases', '')+']', mode='eval').body.elts
                bases.setdefault(card['name'], set()).update(ast.unparse(node) for node in nodes)
            except (SyntaxError, ValueError):
                pass
    def assignable(actual, expected):
        pending, seen = [actual], set()
        while pending:
            current = pending.pop()
            if current == expected:
                return True
            if current not in seen:
                seen.add(current)
                pending.extend(bases.get(current, ()))
        return False
    return assignable


def initial_value_error(typename, value, document=None):
    if not typename.strip() or not value.strip():
        return ''
    try:
        annotation = ast.parse(typename, mode='eval').body
        expression = ast.parse(value, mode='eval').body
        if sum(1 for _ in ast.walk(annotation)) + sum(1 for _ in ast.walk(expression)) > 200:
            return tr('The initial value is too complex to check.')
        if not _matches(annotation, expression, _assignable_classes(document)):
            return tr('The initial value does not match type {type}.').format(type=typename)
    except SyntaxError:
        return tr('Please enter a valid Python value.')
    except (ValueError, TypeError, RecursionError) as exc:
        return str(exc) or tr('The initial value is too complex to check.')
    return ''


def member_initial_fields(value, section):
    if section == 'attributes':
        yield 'default', value['type'], value['default']
    else:
        for index, parameter in enumerate(value['parameters']):
            yield (index, 'default'), parameter['type'], parameter['default']


def validate_member_initial_values(value, section, document=None):
    for field, typename, text in member_initial_fields(value, section):
        error = initial_value_error(typename, text, document)
        if error:
            raise MemberFieldError(error, field)
