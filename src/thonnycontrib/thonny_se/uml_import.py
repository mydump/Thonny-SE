# SPDX-FileCopyrightText: 2026 Sebastian Ladhoff
# SPDX-License-Identifier: GPL-3.0-only
# See LICENSE in the project root for the full license text.

"""Python-Klassendefinitionen statisch in editierbare UML-Karten übersetzen."""
from .i18n import tr
import ast
from collections import Counter
from uuid import uuid4

from . import uml_model
from .uml_codegen import header_data
from .uml_methods import python_visibility
from .uml_source import attach_source
from .uml_python_semantics import imported_names, python_kind, canonical_header, abstract_decorator


_FUNCTIONS = (ast.FunctionDef, ast.AsyncFunctionDef)
_SCOPES = (ast.ClassDef, *_FUNCTIONS)


class ParsedSource:
    """One operation's immutable syntax analysis, shared by linked classes."""
    def __init__(self, source):
        self.source = source
        self.tree = parse_tree(source)
        self.classes = list(_classes(self.tree))
        self.aliases = imported_names(self.tree)
        self._document = None

    def node(self, identity):
        return linked_class_node(self.tree, identity, classes=self.classes)

    def cards(self):
        if self._document is None:
            self._document, _ = _parse_document(self.source, None, analysis=self)
        return self._document['classes']

    def linked(self, path, identity):
        if self._document is not None:
            from copy import deepcopy
            self.node(identity)  # Retain the ambiguity check for duplicate identities.
            index = next(i for i,(_,name) in enumerate(self.classes) if name == identity)
            card = deepcopy(self.cards()[index])
            attach_source(card, path, identity)
            return card
        document, _ = _parse_document(self.source, None, path=path,
                                       qualified_name=identity, analysis=self)
        return document['classes'][0]


def parse_python_classes(source, *, class_line=None, path=None):
    document, _ = _parse_document(source, class_line, path=path)
    return document


def parse_python_class(source, class_line, *, path=None):
    """Return the UML document and the clicked class's original Python name."""
    return _parse_document(source, class_line, path=path)


def parse_linked_class(source, path, qualified_name):
    document, _ = _parse_document(source, None, path=path, qualified_name=qualified_name)
    return document["classes"][0]


def parse_tree(source):
    try:
        tree = ast.parse(source)
        compile(tree, "<UML-Import>", "exec")
    except SyntaxError as exc:
        raise ValueError(tr('Python syntax error on line {p0}: {p1}').format(p0=exc.lineno, p1=exc.msg)) from exc

    return tree


def linked_class_node(tree, qualified_name, *, classes=None):
    classes = [node for node, name in (_classes(tree) if classes is None else classes) if name == qualified_name]
    if len(classes) != 1:
        reason = tr('is missing') if not classes else tr('is defined more than once')
        raise ValueError(tr('Class {p0} {p1}.').format(p0=qualified_name, p1=reason))
    return classes[0]


def _parse_document(source, class_line, *, path=None, qualified_name=None, analysis=None):
    tree = analysis.tree if analysis is not None else parse_tree(source)
    aliases = analysis.aliases if analysis is not None else imported_names(tree)
    document = uml_model.new_document()
    names = set()
    classes = list(analysis.classes) if analysis is not None else list(_classes(tree))
    all_nodes = {qualified:node for node,qualified in classes}
    simple = {node.name:node for node,qualified in classes if sum(other.name == node.name for other,_ in classes) == 1}
    pending_cache = {}
    def pending(node, visiting=frozenset()):
        if id(node) in pending_cache:return pending_cache[id(node)]
        if id(node) in visiting:return set()
        result=set()
        for base in node.bases:
            name=_expression(base.value if isinstance(base,ast.Subscript) else base)
            parent=all_nodes.get(name,simple.get(name))
            if parent is not None:result.update(pending(parent,visiting|{id(node)}))
        for method in node.body:
            if isinstance(method,_FUNCTIONS):
                name=method.name
                if name.startswith('__') and not name.endswith('__'):name='_'+node.name.lstrip('_')+name
                if any(abstract_decorator(decorator,aliases) for decorator in method.decorator_list):result.add(name)
                else:result.discard(name)
        pending_cache[id(node)]=result
        return result
    if qualified_name is not None:
        classes = [(linked_class_node(tree, qualified_name, classes=classes), qualified_name)]
    if class_line is not None:
        enclosing = [
            (node, name) for node, name in classes
            if min([node.lineno, *(decorator.lineno for decorator in node.decorator_list)])
            <= class_line <= node.end_lineno
        ]
        if not enclosing:
            raise ValueError(tr('The pointer is not inside a class here.'))
        classes = enclosing[-1:]
    for node, name in classes:
        card = uml_model.new_class(name, 0, 0)
        if card["name"] in names:
            raise ValueError(tr('The class name {p0} occurs more than once in the diagram.').format(p0=card['name']))
        names.add(card["name"])
        card['header'] = canonical_header(node, aliases)
        kind = python_kind(node, aliases)
        if kind != 'interface' and pending(node):
            kind = 'abstract'
        if kind != 'class':
            card['class_kind'] = kind
        _read_members(node, card, aliases)
        if path is not None:
            attach_source(card, path, name)
        document["classes"].append(card)
    original_name = classes[0][0].name if class_line is not None else None
    return uml_model.validate(document), original_name


def parse_python_files(sources, *, reserved_names=()):
    """Merge (path, source) pairs into one UML document."""
    cards = []
    for path, source in sources:
        try:
            document = parse_python_classes(source, path=path)
        except (ValueError, RecursionError) as exc:
            raise ValueError(f"{path}\n{exc}") from exc
        cards.extend((path, card) for card in document["classes"])

    counts = Counter(card["name"] for _, card in cards)
    reserved = set(reserved_names)
    used = reserved | set(counts)
    document = uml_model.new_document()
    for path, card in cards:
        name = card["name"]
        if counts[name] > 1 or name in reserved:
            module = uml_model.initial_upper(path.stem.strip() or tr('Module'))
            qualified = f"{module}.{name}"
            suffix = 2
            while qualified in used:
                qualified = f"{module}_{suffix}.{name}"
                suffix += 1
            card["name"] = uml_model.class_name(qualified)
            used.add(card["name"])
        document["classes"].append(card)
    return uml_model.validate(document)


def _classes(node, scope=()):
    if isinstance(node, _SCOPES):
        scope = (*scope, node.name)
    if isinstance(node, ast.ClassDef):
        yield node, ".".join(scope)
    for child in ast.iter_child_nodes(node):
        yield from _classes(child, scope)


def _expression(node):
    return ast.unparse(node) if node is not None else ""


def _assignments(node):
    if isinstance(node, _SCOPES):
        return
    if isinstance(node, (ast.Assign, ast.AnnAssign)):
        yield node
        return
    for child in ast.iter_child_nodes(node):
        yield from _assignments(child)


def constructor_receiver(node):
    if not isinstance(node, ast.FunctionDef) or node.name != "__init__":
        return None
    positional = node.args.posonlyargs + node.args.args
    decorators = {_expression(decorator) for decorator in node.decorator_list}
    if positional and not decorators.intersection({"staticmethod", "classmethod"}):
        return positional[0].arg
    return None


def instance_assignments(body, receiver):
    for statement in body:
        for assignment in _assignments(statement):
            targets = assignment.targets if isinstance(assignment, ast.Assign) else [assignment.target]
            for target in targets:
                if (isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name)
                        and target.value.id == receiver):
                    yield assignment, target


def _read_attributes(body, attributes, receiver):
    for assignment, target in instance_assignments(body, receiver):
        name = target.attr
        data = attributes.setdefault(
            name, dict(name=name, visibility=python_visibility(name), type="", default="")
        )
        if isinstance(assignment, ast.AnnAssign):
            data["type"] = _expression(assignment.annotation)
        if assignment.value is not None:
            # Constructor-local expressions cannot be copied into a generated constructor.
            try:
                ast.literal_eval(assignment.value)
            except (ValueError, TypeError, RecursionError):
                data["default"] = ""
            else:
                data["default"] = _expression(assignment.value)


def _method(node, skip_receiver):
    args = node.args
    positional = args.posonlyargs + args.args
    defaults = [None] * (len(positional) - len(args.defaults)) + args.defaults
    entries = list(zip(positional, defaults))[int(skip_receiver):]
    if args.vararg:
        entries.append((args.vararg, None))
    entries.extend(zip(args.kwonlyargs, args.kw_defaults))
    if args.kwarg:
        entries.append((args.kwarg, None))
    result = "" if isinstance(node.returns, ast.Constant) and node.returns.value is None else _expression(node.returns)
    return dict(
        name=node.name, visibility=python_visibility(node.name),
        kind="function" if result else "procedure", return_type=result,
        parameters=[
            dict(name=arg.arg, type=_expression(arg.annotation), default=_expression(default),
                 **({"kind": "positional_only"} if arg in args.posonlyargs else
                    {"kind": "vararg"} if arg is args.vararg else
                    {"kind": "kwarg"} if arg is args.kwarg else
                    {"kind": "keyword_only"} if arg in args.kwonlyargs else {}))
            for arg, default in entries if arg.arg not in ("self", "cls")
        ],
    )


def _read_members(node, card, aliases):
    attributes = {}
    for member in node.body:
        if not isinstance(member, _FUNCTIONS):
            continue
        decorators = {_expression(decorator) for decorator in member.decorator_list}
        static = "staticmethod" in decorators
        receiver = constructor_receiver(member)
        if receiver is not None:
            _read_attributes(member.body, attributes, receiver)
        if member.name != "__new__":
            row = dict(id=uuid4().hex, method=_method(member, not static))
            if member.name == '__init__':
                row['method'].update(kind='constructor', name='__init__', visibility='public', return_type='')
            abstract = any(abstract_decorator(decorator, aliases) for decorator in member.decorator_list)
            if abstract or card.get('class_kind') in ('abstract','interface'):
                row['abstract'] = abstract
            card['methods'].append(row)
    card["attributes"] = [dict(id=uuid4().hex, attribute=data) for data in attributes.values()]
