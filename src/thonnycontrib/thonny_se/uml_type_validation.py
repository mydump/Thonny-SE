# SPDX-FileCopyrightText: 2026 Sebastian Ladhoff
# SPDX-License-Identifier: GPL-3.0-only
# See LICENSE in the project root for the full license text.

"""Check names in UML type annotations without executing student modules."""
import ast
import builtins
import importlib
from importlib.machinery import PathFinder
from pathlib import Path
import sys
import typing
from tokenize import open as open_python

from .i18n import tr
from .uml_methods import MemberFieldError

TYPING_NAMES = frozenset(name for name in 'Any Optional Union Literal Annotated Callable ClassVar Final Self Never NoReturn List Dict Tuple Set FrozenSet Type Sequence MutableSequence Mapping MutableMapping Iterable Iterator Collection Container Generator AsyncIterator AsyncIterable Awaitable Coroutine Protocol Generic LiteralString TypeGuard TypeIs Unpack Concatenate'.split() if hasattr(typing, name))
STANDARD_MODULES = frozenset(('builtins', 'typing', 'types', 'collections', 'collections.abc', 'datetime', 'decimal', 'fractions', 'pathlib', 're', 'enum'))
GENERIC_BUILTINS = frozenset(('list', 'dict', 'tuple', 'set', 'frozenset', 'type'))


class TypeContext:
    def __init__(self, document, card, read_source=None):
        self.classes = {value for item in document['classes']
                        for value in (item['name'], item.get('header', {}).get('name', ''), item.get('source', {}).get('class', '')) if value}
        self.read_source = read_source
        self.cache = {}
        self.sources = {}
        self.path = Path(card.get('source', {}).get('path', '.')).resolve()
        self.tree = None
        if card.get('source'):
            try:
                text = self._read(self.path)
                self.tree = ast.parse(text)
            except (OSError, ValueError, SyntaxError, UnicodeError):
                pass

    def _read(self, path):
        if self.read_source is not None:
            return self.read_source(str(path))
        with open_python(path) as stream:
            return stream.read()

    def check(self, text):
        if not text:
            return True
        try:
            node = ast.parse(text, mode='eval').body
            if isinstance(node, ast.Constant) and node.value is Ellipsis:
                return False
            return sum(1 for _ in ast.walk(node)) <= 200 and self._valid(node, set())
        except (SyntaxError, ValueError, RecursionError):
            return False

    def _valid(self, node, visiting):
        if isinstance(node, ast.Constant):
            if node.value is None or node.value is Ellipsis:
                return True
            return isinstance(node.value, str) and self._forward(node.value, visiting)
        if isinstance(node, (ast.Name, ast.Attribute)):
            return self._name(ast.unparse(node), visiting)
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
            return self._valid(node.left, visiting) and self._valid(node.right, visiting)
        if isinstance(node, ast.Subscript):
            name = ast.unparse(node.value)
            if not self._valid(node.value, visiting) or name in vars(builtins) and name not in GENERIC_BUILTINS:
                return False
            values = node.slice.elts if isinstance(node.slice, ast.Tuple) else [node.slice]
            short = name.rsplit('.', 1)[-1]
            if short == 'Literal':
                return all(isinstance(value, (ast.Constant, ast.UnaryOp, ast.Attribute)) for value in values)
            if short == 'Annotated':
                return len(values) >= 2 and self._valid(values[0], visiting)
            return all(self._valid(value, visiting) for value in values)
        if isinstance(node, ast.List):  # Callable[[int, str], bool]
            return all(self._valid(value, visiting) for value in node.elts)
        return False

    def _forward(self, text, visiting):
        key = ('forward', text)
        if key in visiting:
            return False
        return self._valid(ast.parse(text, mode='eval').body, visiting | {key})

    def _name(self, name, visiting):
        if name in self.classes or name in TYPING_NAMES or isinstance(vars(builtins).get(name), type):
            return True
        if '.' in name:
            module, symbol = name.rsplit('.', 1)
            if module in STANDARD_MODULES:
                return self._standard(module, symbol)
        return self.tree is not None and self._defined(self.tree, self.path, name, visiting)

    def _standard(self, module, symbol):
        if module == 'typing':
            return symbol in TYPING_NAMES
        return isinstance(vars(importlib.import_module(module)).get(symbol), type)

    def _module(self, module, symbol, directory, visiting):
        key = (module, symbol, str(directory))
        if key in self.cache:
            return self.cache[key]
        if key in visiting or len(visiting) > 20:
            return False
        visiting = visiting | {key}
        if module in STANDARD_MODULES:
            return self._standard(module, symbol)
        search = [str(directory), *sys.path]
        spec = None
        for index, part in enumerate(module.split('.')):
            spec = PathFinder.find_spec('.'.join(module.split('.')[:index+1]), search)
            if spec is None:
                return False
            search = spec.submodule_search_locations
            if index < len(module.split('.'))-1 and search is None:
                return False
        if not spec or not spec.origin or not spec.origin.endswith(('.py', '.pyi')):
            return False
        path = Path(spec.origin)
        try:
            if path not in self.sources:
                self.sources[path] = ast.parse(self._read(path))
            result = self._defined(self.sources[path], path, symbol, visiting)
        except (OSError, ValueError, SyntaxError, UnicodeError):
            result = False
        self.cache[key] = result
        return result

    def _defined(self, tree, path, name, visiting):
        first, _, tail = name.partition('.')
        for node in tree.body:
            if isinstance(node, ast.ClassDef) and node.name == first:
                return not tail or self._defined(node, path, tail, visiting)
            if isinstance(node, ast.Import):
                for alias in node.names:
                    bound = alias.asname or alias.name.split('.')[0]
                    if bound == first and tail:
                        module = alias.name if alias.asname else first
                        return self._module(module+'.'+tail.rsplit('.', 1)[0], tail.rsplit('.', 1)[-1], path.parent, visiting) if '.' in tail else self._module(module, tail, path.parent, visiting)
            if isinstance(node, ast.ImportFrom):
                directory = path.parent
                for _ in range(max(0, node.level-1)):
                    directory = directory.parent
                for alias in node.names:
                    if (alias.asname or alias.name) == first:
                        if not node.module:
                            return bool(tail) and self._module(alias.name, tail, directory, visiting)
                        if tail and self._module(node.module+'.'+alias.name, tail, directory, visiting):
                            return True
                        return self._module(node.module, alias.name+('.'+tail if tail else ''), directory, visiting)
            alias_node = getattr(ast, 'TypeAlias', ())
            if alias_node and isinstance(node, alias_node) and node.name.id == first:
                return not tail
            targets = node.targets if isinstance(node, ast.Assign) else [node.target] if isinstance(node, ast.AnnAssign) else []
            if any(isinstance(target, ast.Name) and target.id == first for target in targets) and not tail:
                key = ('alias', str(path), first)
                if key in visiting or node.value is None:
                    return False
                if isinstance(node.value, ast.Call) and ast.unparse(node.value.func) in ('TypeVar', 'typing.TypeVar', 'NewType', 'typing.NewType', 'ParamSpec', 'typing.ParamSpec'):
                    return True
                previous = self.tree, self.path
                self.tree, self.path = tree, path
                try:
                    return self._valid(node.value, visiting | {key})
                finally:
                    self.tree, self.path = previous
        return False


def member_type_fields(value, section):
    if section == 'attributes':
        return [('type', value['type'])]
    return [('type', value['return_type']),
            *[((index, 'type'), param['type']) for index, param in enumerate(value['parameters'])]]


def type_error(text):
    return tr('Unknown or invalid data type: {type}.').format(type=text)


def validate_member_types(value, section, context):
    for field, text in member_type_fields(value, section):
        if not context.check(text):
            raise MemberFieldError(type_error(text), field)
