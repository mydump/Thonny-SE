# SPDX-FileCopyrightText: 2026 Sebastian Ladhoff
# SPDX-License-Identifier: GPL-3.0-only
# See LICENSE in the project root for the full license text.

"""Static Python mapping for abstract classes and protocol interfaces."""
import ast
from .i18n import tr


def imported_names(tree):
    names = {}
    for node in tree.body:
        if isinstance(node, ast.Import):
            for item in node.names:
                names[item.asname or item.name.split('.')[0]] = item.name if item.asname else item.name.split('.')[0]
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            for item in node.names:
                names[item.asname or item.name] = f'{node.module}.{item.name}'
    return names


def resolved_name(node, aliases):
    if isinstance(node, ast.Name):
        return aliases.get(node.id, node.id)
    if isinstance(node, ast.Attribute):
        return resolved_name(node.value, aliases)+'.'+node.attr
    if isinstance(node, ast.Subscript):
        return resolved_name(node.value, aliases)
    return ''


def abstract_decorator(node, aliases):
    return resolved_name(node, aliases) in ('abc.abstractmethod','abc.abstractproperty','abc.abstractclassmethod','abc.abstractstaticmethod')


def python_kind(node, aliases):
    if any(resolved_name(base, aliases) in ('typing.Protocol','typing_extensions.Protocol') for base in node.bases):
        return 'interface'
    if any(abstract_decorator(decorator, aliases) for method in node.body
           if isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef)) for decorator in method.decorator_list):
        return 'abstract'
    # ABC alone does not make a Python class abstract, and never means interface.
    return 'class'


def canonical_header(node, aliases):
    bases = []
    for base in node.bases:
        resolved = resolved_name(base, aliases)
        if resolved in ('typing.Protocol','typing_extensions.Protocol'):
            base = ast.parse('typing.Protocol',mode='eval').body
        elif resolved == 'abc.ABC':
            base = ast.parse('abc.ABC',mode='eval').body
        bases.append(ast.unparse(base))
    bases += [('metaclass=abc.ABCMeta' if item.arg == 'metaclass' and resolved_name(item.value,aliases) == 'abc.ABCMeta' else ast.unparse(item)) for item in node.keywords]
    return {'name':node.name,'bases':', '.join(bases)}


def abstract_method(card, row):
    from .uml_methods import is_constructor
    # Imported methods carry explicit flags. Keep the historical default for
    # diagram-created/legacy methods without a flag; interfaces stay abstract.
    kind = card.get('class_kind')
    return not is_constructor(row) and (kind == 'interface' or row.get('abstract', kind == 'abstract'))


def generated_header(card):
    from .uml_codegen import class_header, header_data
    header = dict(card.get('header', {'name':card['name'],'bases':''}))
    node = ast.parse(class_header(header)+'\n    pass').body[0]
    kind = card.get('class_kind','class')
    # Framework bases follow the selected class kind, not stale imported text.
    node.bases = [base for base in node.bases
                  if ast.unparse(base) != 'typing.Protocol'
                  and not (kind == 'interface' and ast.unparse(base) == 'abc.ABC')]
    if kind == 'interface':
        node.bases.append(ast.parse('typing.Protocol',mode='eval').body)
    elif kind == 'abstract' or any(row.get('abstract') for row in card['methods']):
        if not any(ast.unparse(base) == 'abc.ABC' for base in node.bases):
            node.bases.append(ast.parse('abc.ABC',mode='eval').body)
    return header_data(node)


def required_imports(cards):
    result=[]
    if any(card.get('class_kind') == 'abstract' or any(abstract_method(card,row) for row in card['methods'])
           or 'abc.ABC' in card.get('header',{}).get('bases','') or 'abc.ABCMeta' in card.get('header',{}).get('bases','') for card in cards):
        result.append('import abc')
    if any(card.get('class_kind') == 'interface' for card in cards):
        result.append('import typing')
    return result


def validate_abstract_class(card, inherited=()):
    from .uml_methods import visible_methods
    if not inherited and card.get('class_kind') == 'abstract' and not any(abstract_method(card,row) for row in visible_methods(card)):
        raise ValueError(tr('Abstract class {name!r} needs a method. Add a method or choose Class.').format(name=card['name']))


def abstract_contracts(cards):
    """Track known local abstract methods without executing project code."""
    from .uml_methods import draft_from_row, visible_methods, is_constructor
    from .uml_codegen import _member_name
    by_name = {card.get('header',{}).get('name',card['name']):card for card in cards}
    result, visiting = {}, set()
    def visit(card):
        cid=card['id']
        if cid in result:return result[cid]
        if cid in visiting:
            return set(),set()  # The normal inheritance validator reports cycles.
        visiting.add(cid)
        header=generated_header(card)
        node=ast.parse('class Placeholder('+header['bases']+'):\n    pass').body[0] if header['bases'] else None
        inherited=set()
        if node:
            for base in node.bases:
                name=ast.unparse(base.value if isinstance(base,ast.Subscript) else base)
                if name in by_name:
                    inherited.update(visit(by_name[name])[1])
        pending=set(inherited)
        for row in visible_methods(card):
            if is_constructor(row):
                continue
            method,unparsed=draft_from_row(row)
            if unparsed:continue
            name=_member_name(method)
            if name.startswith('__') and not name.endswith('__'):
                name='_'+header['name'].lstrip('_')+name
            if abstract_method(card,row):pending.add(name)
            else:pending.discard(name)
        visiting.remove(cid)
        result[cid]=inherited,pending
        return result[cid]
    for card in cards:visit(card)
    return result


def validate_interfaces(cards):
    by_name={card.get('header',{}).get('name',card['name']):card for card in cards}
    for card in cards:
        if card.get('class_kind') != 'interface':continue
        bases=generated_header(card)['bases']
        node=ast.parse('class Placeholder('+bases+'):\n    pass').body[0]
        for base in node.bases:
            name=ast.unparse(base.value if isinstance(base,ast.Subscript) else base)
            if name in by_name and by_name[name].get('class_kind') != 'interface':
                raise ValueError(tr('Interface {name!r} can inherit only from interfaces.').format(name=card['name']))
