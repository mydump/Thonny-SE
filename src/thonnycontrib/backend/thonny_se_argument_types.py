# SPDX-FileCopyrightText: 2026 Sebastian Ladhoff
# SPDX-License-Identifier: GPL-3.0-only
"""Side-effect-free checks of literals and known variables, never eval."""
import ast


def describe(value, budget=None, depth=0):
    budget = [500] if budget is None else budget
    cls = type(value)
    bases = type.__getattribute__(cls, '__mro__')
    result = {'types': [type.__getattribute__(base, '__name__') for base in bases],
              'qualified': [type.__getattribute__(base, '__module__')+'.'+type.__getattribute__(base, '__qualname__') for base in bases]}
    if depth >= 5 or budget[0] <= 0:
        return result
    budget[0] -= 1
    if cls in (list, tuple, set, frozenset, dict) and len(value) <= min(100, budget[0]):
        if cls is dict:
            result['pairs'] = [(describe(k, budget, depth+1), describe(v, budget, depth+1)) for k, v in value.items()]
        else:
            result['items'] = [describe(item, budget, depth+1) for item in value]
    return result


def argument_context(namespace):
    budget = [1500]
    values, aliases = {}, {}
    for name, value in list(namespace.items()):
        if name in {'__builtins__', '__annotations__', '__warningregistry__'}:
            continue
        if issubclass(type(value), type):
            aliases[name] = type.__getattribute__(value, '__module__')+'.'+type.__getattribute__(value, '__qualname__')
        values[name] = describe(value, budget)
    return {'values': values, 'aliases': aliases}


def _all(checks):
    checks = list(checks)
    return False if False in checks else None if None in checks else True


def matches(value, annotation, aliases):
    if isinstance(annotation, ast.Constant):
        if annotation.value is None:
            return value['types'][0] == 'NoneType'
        if isinstance(annotation.value, str):
            try:
                return matches(value, ast.parse(annotation.value, mode='eval').body, aliases)
            except (SyntaxError, RecursionError):
                return None
    if isinstance(annotation, ast.BinOp) and isinstance(annotation.op, ast.BitOr):
        checks = [matches(value, annotation.left, aliases), matches(value, annotation.right, aliases)]
        return True if True in checks else None if None in checks else False
    if isinstance(annotation, (ast.Name, ast.Attribute)):
        name = annotation.id if isinstance(annotation, ast.Name) else annotation.attr
        if name in ('Any', 'object'):
            return True
        if name in aliases:
            return aliases[name] in value.get('qualified', ())
        if name == 'float' and value['types'][0] == 'int':
            return True
        if name == 'int' and value['types'][0] == 'bool':
            return False
        if name in value['types']:
            return True
        if name not in {'str', 'int', 'float', 'bool', 'bytes', 'bytearray', 'list', 'tuple', 'dict', 'set', 'frozenset', 'complex', 'type', 'NoneType'}:
            return None
        return False
    if isinstance(annotation, ast.Subscript):
        base = annotation.value.id if isinstance(annotation.value, ast.Name) else annotation.value.attr if isinstance(annotation.value, ast.Attribute) else ''
        args = annotation.slice.elts if isinstance(annotation.slice, ast.Tuple) else [annotation.slice]
        if base == 'Optional':
            return True if value['types'][0] == 'NoneType' else matches(value, args[0], aliases)
        if base == 'Union':
            checks = [matches(value, arg, aliases) for arg in args]
            return True if True in checks else None if None in checks else False
        if base == 'Annotated':
            return matches(value, args[0], aliases)
        base = {'List':'list', 'Tuple':'tuple', 'Dict':'dict', 'Set':'set', 'FrozenSet':'frozenset'}.get(base, base)
        if base not in ('list', 'tuple', 'dict', 'set', 'frozenset'):
            return None
        if base not in value['types']:
            return False
        if base == 'dict':
            if 'pairs' not in value or len(args) != 2: return None
            return _all(check for k, v in value['pairs'] for check in (matches(k, args[0], aliases), matches(v, args[1], aliases)))
        if 'items' not in value: return None
        items = value['items']
        if base == 'tuple' and len(args) > 1 and not (isinstance(args[-1], ast.Constant) and args[-1].value is Ellipsis):
            return len(items) == len(args) and _all(matches(item, arg, aliases) for item, arg in zip(items, args))
        return _all(matches(item, args[0], aliases) for item in items)
    return None


def field_states(parameters, values, context=None, check_types=True):
    context = context or {}
    states = {}
    for parameter in parameters:
        name = parameter['name']
        text = values.get(name, '').strip()
        if not text:
            states[name] = 'missing' if parameter['required'] else 'valid'
            continue
        states[name] = 'valid'
        if not check_types:
            continue
        try:
            tree = ast.parse(text, mode='eval').body
        except (SyntaxError, ValueError, RecursionError):
            states[name] = 'invalid'
            continue
        # Calls and other dynamic expressions belong to execution, not typing.
        if any(isinstance(node, ast.Call) for node in ast.walk(tree)):
            continue
        if isinstance(tree, ast.Name):
            value = context.get('values', {}).get(tree.id)
            if value is None:
                states[name] = 'invalid'
                continue
        else:
            try:
                value = describe(ast.literal_eval(tree))
            except (ValueError, TypeError, SyntaxError, RecursionError, MemoryError):
                continue
        annotation = parameter.get('annotation', '')
        if not annotation or parameter['kind'] in ('VAR_POSITIONAL', 'VAR_KEYWORD'):
            continue
        try:
            expected = ast.parse(annotation, mode='eval').body
            if matches(value, expected, context.get('aliases', {})) is False:
                states[name] = 'invalid'
        except (SyntaxError, ValueError, RecursionError):
            pass
    return states
