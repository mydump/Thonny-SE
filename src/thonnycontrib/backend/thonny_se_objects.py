# SPDX-FileCopyrightText: 2026 Sebastian Ladhoff
# SPDX-License-Identifier: GPL-3.0-only
# See LICENSE in the project root for the full license text.

"""Read-only snapshots of named CPython instances for Objektinspektor SE."""
import inspect
import json
import ast
import textwrap
import importlib.util
from pathlib import Path
import sysconfig
import uuid
import sys
import types


def is_user_instance(value):
    """Use the concrete class's origin, not its bases, to classify an instance."""
    cls = type(value)
    if isinstance(value, (type, types.ModuleType, types.FunctionType,
                          types.MethodType, types.BuiltinFunctionType)):
        return False
    if cls.__module__ in ('builtins', 'typing', 'typing_extensions', 'types'):
        return False
    if cls.__module__ == '__main__':
        return True
    try:
        origin = Path(inspect.getfile(cls)).resolve()
    except (TypeError, OSError):
        return False
    library_paths = {Path(path).resolve() for key, path in sysconfig.get_paths().items()
                     if key in ('stdlib', 'platstdlib', 'purelib', 'platlib')}
    return not any(origin.is_relative_to(root) for root in library_paths)


def load_file(path, namespace):
    """Import a saved file without invoking its __main__ guard, then expose names."""
    path = Path(path).resolve()
    name = '_thonny_se_loaded_' + uuid.uuid4().hex
    spec = importlib.util.spec_from_file_location(name, str(path))
    if spec is None or spec.loader is None:
        raise ValueError('Not a loadable Python file')
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # Required by dataclasses and runtime type lookups.
    previous_path = list(sys.path)
    try:
        sys.path.insert(0, str(path.parent))
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(name, None)
        raise
    finally:
        sys.path[:] = previous_path
    namespace.update({key: value for key, value in vars(module).items()
                      if not key.startswith('_')})


def class_methods(cls):
    """Inspect class members once; callers copy before hiding instance shadows."""
    methods = {}
    for base in reversed(cls.__mro__):
        for method, member in vars(base).items():
            if method.startswith('__') and method.endswith('__'):
                continue
            is_static = isinstance(member, staticmethod)
            if isinstance(member, (staticmethod, classmethod)):
                member = member.__func__
            if inspect.isfunction(member):
                try:
                    # Inspect a copy without lazy annotations: even STRING format
                    # can execute annotation calls in Python 3.14.
                    target = types.FunctionType(member.__code__, member.__globals__,
                        member.__name__, member.__defaults__, member.__closure__)
                    target.__kwdefaults__ = member.__kwdefaults__
                    if sys.version_info >= (3, 14):
                        try:
                            tree = ast.parse(textwrap.dedent(inspect.getsource(member)))
                            node = next(n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)))
                            args = node.args
                            parameters_ast = args.posonlyargs + args.args + args.kwonlyargs
                            parameters_ast += [a for a in (args.vararg, args.kwarg) if a is not None]
                            annotations = {a.arg: ast.unparse(a.annotation) for a in parameters_ast if a.annotation is not None}
                            if node.returns is not None:
                                annotations['return'] = ast.unparse(node.returns)
                            target.__annotations__ = annotations
                        except (OSError, TypeError, SyntaxError, StopIteration):
                            pass  # Shell definitions may have no retrievable source.
                    else:
                        target.__annotations__ = inspect.get_annotations(member, eval_str=False)
                    signature = inspect.signature(target, eval_str=False)
                    parameters = list(signature.parameters.values())
                    if not is_static and parameters:
                        signature = signature.replace(parameters=parameters[1:])
                    signature = str(signature)
                except Exception:
                    signature = '(…)'
                methods[method] = signature
            elif method in methods:
                del methods[method]
    return methods


CONTAINERS = (list, tuple, dict, set, frozenset)


def stored_fields(value):
    """Read actual instance storage without invoking properties or custom accessors."""
    try:
        fields = object.__getattribute__(value, '__dict__')
    except (AttributeError, TypeError):
        fields = {}
    fields = dict(fields) if isinstance(fields, dict) else {}
    seen = set()
    for base in type(value).__mro__:
        for name, descriptor in vars(base).items():
            if name in seen:
                continue
            seen.add(name)
            if isinstance(descriptor, types.MemberDescriptorType):
                try:
                    fields[name] = descriptor.__get__(value, type(value))
                except AttributeError:
                    pass
    return {name: content for name, content in fields.items() if isinstance(name, str)}


def _resolve_object(namespace, path):
    """Follow stored references, never evaluate a Python expression."""
    if isinstance(path, str):
        return namespace.get(path)
    value = namespace.get(path['root'])
    for step in path.get('steps', ()):
        if step[0] == 'attr':
            value = stored_fields(value)[step[1]]
        elif step[0] == 'index' and type(value) in (list, tuple):
            value = value[step[1]]
        elif step[0] == 'dict' and type(value) is dict:
            value = next(content for key,content in value.items() if id(key) == step[1])
        elif step[0] == 'set' and type(value) in (set, frozenset):
            value = next(content for content in value if id(content) == step[1])
        else:
            raise ValueError('stale_object')
    return value


def resolve_object(namespace, path):
    try:
        return _resolve_object(namespace, path)
    except (KeyError, IndexError, StopIteration, TypeError, AttributeError):
        raise ValueError('stale_object') from None


def snapshot(namespace, *, representation_error="<Representation failed>", expanded=(), item_limits=None):
    """Bounded, lazy reference trees; aliases retain their real Python identity."""
    expanded = set(expanded)
    item_limits = item_limits or {}
    methods, kinds, aliases = {}, {}, {}
    def kind(value):
        if type(value) in CONTAINERS:
            return 'container'
        key = id(type(value))
        if key not in kinds:
            kinds[key] = is_user_instance(value)
        return 'object' if kinds[key] else 'scalar'
    def representation(value):
        try:
            return repr(value)[:500]
        except Exception:
            return representation_error
    roots = []
    for name,value in list(namespace.items()):
        if name.startswith('_') or not name.isidentifier() or kind(value) == 'scalar':
            continue
        if id(value) not in aliases:
            aliases[id(value)] = []
            roots.append((name,value))
        aliases[id(value)].append(name)
    remaining = [500]
    def describe(value, path, ancestors=(), force=False):
        node_kind = kind(value)
        node = dict(id=id(value), kind=node_kind, path=path, names=aliases.get(id(value), []),
                    class_name=type(value).__name__, attributes={}, methods={})
        if node_kind == 'scalar':
            node['value'] = representation(value)
            return node
        node['expansion_key'] = json.dumps(path, sort_keys=True, separators=(',', ':'))
        node['cycle'] = id(value) in ancestors
        node['expanded'] = not node['cycle'] and (force or node['expansion_key'] in expanded or id(value) in expanded)
        if node_kind == 'container':
            node['length'] = len(value)
        if not node['expanded']:
            return node
        if len(ancestors) >= 12 or remaining[0] <= 0:
            node['limited'] = True
            return node
        remaining[0] -= 1
        ancestors = (*ancestors, id(value))
        def child(content, step):
            return describe(content, dict(root=path['root'], steps=[*path['steps'], step]), ancestors)
        if node_kind == 'container':
            if type(value) is dict:
                entries = ((representation(key), content, ['dict',id(key)]) for key,content in value.items())
            elif type(value) in (set, frozenset):
                entries = ((str(i),content,['set',id(content)]) for i,content in enumerate(value))
            else:
                entries = ((str(i),content,['index',i]) for i,content in enumerate(value))
            node['items'] = []
            for i,(label,content,step) in enumerate(entries):
                if i >= max(100,int(item_limits.get(node['expansion_key'],100))):
                    break
                node['items'].append(dict(label=label, node=child(content,step)))
            node['remaining'] = max(0,len(value)-len(node['items']))
        else:
            fields = stored_fields(value)
            node['references'] = {name:child(content,['attr',name]) for name,content in fields.items()
                                  if kind(content) != 'scalar'}
            # References are displayed as expandable nodes, never as their full repr.
            node['attributes'] = {name:(node['references'][name]['class_name'] if name in node['references']
                                      else representation(content)) for name,content in fields.items()}
            cls = type(value)
            class_key = id(cls)
            if class_key not in methods:
                methods[class_key] = class_methods(cls)
            node['methods'] = {name:signature for name,signature in methods[class_key].items() if name not in fields}
            node['class_names'] = [base.__name__ for base in cls.__mro__]
        return node
    result = [describe(value, dict(root=name,steps=[]), force=kind(value)=='object') for name,value in roots]
    occurrences = {}
    def collect(node):
        if node['kind'] != 'scalar':
            occurrences.setdefault(node['id'], []).append(node)
        for child in node.get('references', {}).values():
            collect(child)
        for entry in node.get('items', []):
            collect(entry['node'])
    for node in result:
        collect(node)
    for number,nodes in enumerate(occurrences.values(),1):
        if len(nodes)>1:
            for node in nodes:
                node['reference'] = number
    return result


def load_plugin(backend):
    def get_objects(command):
        objects = snapshot(vars(sys.modules['__main__']),
            representation_error=command.get('representation_error', '<Representation failed>'),
            expanded=command.get('expanded', ()), item_limits=command.get('item_limits', {}))
        return {'objects': objects}
    backend.add_command('thonny_se_objects', get_objects)
