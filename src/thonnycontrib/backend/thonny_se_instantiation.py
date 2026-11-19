# SPDX-FileCopyrightText: 2026 Sebastian Ladhoff
# SPDX-License-Identifier: GPL-3.0-only
# See LICENSE in the project root for the full license text.

"""Runtime class loading and constructor calls in the local Python backend."""
import ast
import hashlib
import importlib.util
import inspect
import keyword
from pathlib import Path
import sys
import traceback
import sysconfig
import tokenize
import textwrap
import types
import uuid

from .thonny_se_objects import snapshot


def source_files():
    libraries = {Path(value).resolve() for value in sysconfig.get_paths().values()}
    result = {}
    for module in list(sys.modules.values()):
        if getattr(module, '__name__', '').startswith('thonnycontrib.backend.thonny_se_'):
            continue
        name = getattr(module, '__file__', None)
        if not name:
            continue
        path = Path(name).resolve()
        if path.suffix != '.py' or any(path.is_relative_to(root) for root in libraries):
            continue
        try:
            with tokenize.open(path) as file:
                text = file.read()
            result[str(path)] = dict(digest=hashlib.sha256(path.read_bytes()).hexdigest(), text=text)
        except (OSError, UnicodeError, SyntaxError):
            continue
    return result


def constructor_signature(cls):
    # Cloning strips deferred annotations, which can execute expressions on 3.14.
    target = cls.__init__ if cls.__init__ is not object.__init__ else cls.__new__
    if cls.__init__ is object.__init__ and cls.__new__ is object.__new__:
        return inspect.Signature()
    if not isinstance(target, types.FunctionType):
        raise ValueError('unsupported_constructor')
    clone = types.FunctionType(target.__code__, target.__globals__, target.__name__,
                               target.__defaults__, target.__closure__)
    clone.__kwdefaults__ = target.__kwdefaults__
    signature = inspect.signature(clone, follow_wrapped=False)
    signature = signature.replace(parameters=list(signature.parameters.values())[1:])
    parameters = list(signature.parameters.values())
    if parameters and all(param.kind in (param.VAR_POSITIONAL, param.VAR_KEYWORD) for param in parameters):
        try:
            node = ast.parse(textwrap.dedent(inspect.getsource(target))).body[0]
            varargs, kwargs = node.args.vararg, node.args.kwarg
            if varargs is not None and kwargs is not None:
                expected = ast.parse(f"super().__init__(*{varargs.arg}, **{kwargs.arg})").body[0]
                forwards = any(ast.dump(statement) == ast.dump(expected) for statement in node.body)
            else:
                forwards = False
        except (OSError, TypeError, SyntaxError, IndexError):
            forwards = False
        if forwards:
            base = next((base for base in cls.__mro__[1:] if base.__init__ is not target), None)
            if base is not None:
                return constructor_signature(base)
    return signature


def evaluate_arguments(signature, values, namespace):
    """Evaluate each expression once and bind Python parameter kinds correctly."""
    args, kwargs = [], {}
    has_varargs = any(param.kind == param.VAR_POSITIONAL and values.get(param.name, '').strip()
                      for param in signature.parameters.values())
    for parameter in signature.parameters.values():
        text = values.get(parameter.name, '').strip()
        if not text:
            if parameter.default is parameter.empty and parameter.kind not in (parameter.VAR_POSITIONAL, parameter.VAR_KEYWORD):
                raise TypeError(f'Missing argument: {parameter.name}')
            if (parameter.kind == parameter.POSITIONAL_ONLY or
                    (has_varargs and parameter.kind == parameter.POSITIONAL_OR_KEYWORD)) and parameter.default is not parameter.empty:
                args.append(parameter.default)
            continue
        ast.parse(text, mode='eval')
        value = eval(compile(text, '<Thonny SE argument>', 'eval'), namespace)
        if parameter.kind == parameter.POSITIONAL_ONLY or (has_varargs and parameter.kind == parameter.POSITIONAL_OR_KEYWORD):
            args.append(value)
        elif parameter.kind == parameter.VAR_POSITIONAL:
            if not isinstance(value, (tuple, list)):
                raise ValueError('invalid_varargs')
            args.extend(value)
        elif parameter.kind == parameter.VAR_KEYWORD:
            if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
                raise ValueError('invalid_kwargs')
            if kwargs.keys() & value.keys():
                raise ValueError('duplicate_arguments')
            kwargs.update(value)
        else:
            if parameter.name in kwargs:
                raise ValueError('duplicate_arguments')
            kwargs[parameter.name] = value
    signature.bind(*args, **kwargs)
    return args, kwargs


class InstantiationSession:
    def __init__(self, namespace):
        self.namespace = namespace
        self.modules = {}
        self.prepared = {}

    def prepare(self, path, qualified_name):
        path = str(Path(path).resolve())
        module = self.modules.get(path)
        if module is None:
            parts = [] if Path(path).name == '__init__.py' else [Path(path).stem]
            directory = Path(path).parent
            while (directory / '__init__.py').is_file():
                parts.insert(0, directory.name)
                directory = directory.parent
            module_name = '.'.join(parts)
            existing = sys.modules.get(module_name)
            if existing is not None:
                origin = getattr(existing, '__file__', None)
                if origin and Path(origin).resolve() == Path(path):
                    self.modules[path] = existing
                    return self.prepare(path, qualified_name)
                raise ValueError('module_name_conflict')
            spec = importlib.util.spec_from_file_location(module_name, path)
            if spec is None or spec.loader is None:
                raise ValueError('invalid_source')
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            previous = sys.path[:]
            try:
                sys.path.insert(0, str(directory))
                spec.loader.exec_module(module)
            except BaseException:
                sys.modules.pop(module_name, None)
                sys.path[:] = previous
                raise
            self.modules[path] = module
        cls = module
        for name in qualified_name.split('.'):
            cls = getattr(cls, name)
        return self.prepare_class(cls)

    def prepare_memory(self, sources, module, qualified_name):
        from .thonny_se_memory import MemoryModules
        if not hasattr(self, 'memory'):
            self.memory = MemoryModules()
        self.memory.configure(sources)
        cls = self.memory.load(module)
        for name, value in vars(cls).items():
            if isinstance(value, type) and value.__module__ in self.memory.sources:
                self.namespace[name] = value
        for name in qualified_name.split('.'):
            cls = getattr(cls, name)
        return self.prepare_class(cls)

    def load_diagram(self, sources, targets):
        from .thonny_se_memory import MemoryModules
        self.memory = MemoryModules()
        try:
            for source in sources:
                compile(source['text'], source['filename'], 'exec')
            self.memory.configure(sources)
            for source in sources:
                self.memory.load(source['name'])
            classes = {}
            for cid, target in targets.items():
                cls = self.memory.load(target['module'])
                for name in target['identity'].split('.'):
                    cls = getattr(cls, name)
                if not isinstance(cls, type):
                    raise ValueError('not_a_class')
                self.namespace[cls.__name__] = cls
                if inspect.isabstract(cls):
                    classes[cid] = {'instantiable': False}
                else:
                    try:
                        signature = constructor_signature(cls)
                        token = uuid.uuid4().hex
                        self.prepared[token] = cls, signature
                        classes[cid] = dict(token=token, instantiable=True)
                    except ValueError as error:
                        if str(error) != 'unsupported_constructor':
                            raise
                        # A valid Python class remains usable in the console even
                        # when its native constructor has no editable signature.
                        classes[cid] = {'instantiable': False}
            return dict(classes=classes, objects=snapshot(self.namespace))
        except BaseException:
            self.prepared.clear()
            self.memory.clear()
            for name in list(self.namespace):
                if not name.startswith('__'):
                    self.namespace.pop(name, None)
            raise

    def prepare_class(self, cls, *, include_files=True):
        if not isinstance(cls, type):
            raise ValueError('not_a_class')
        if inspect.isabstract(cls):
            raise ValueError('abstract_class')
        signature = constructor_signature(cls)
        self.namespace[cls.__name__] = cls
        token = uuid.uuid4().hex
        self.prepared[token] = cls, signature
        parameters = []
        for param in signature.parameters.values():
            parameters.append(dict(name=param.name, kind=param.kind.name,
                                   required=param.default is inspect.Parameter.empty and
                                   param.kind not in (param.VAR_POSITIONAL, param.VAR_KEYWORD),
                                   default='' if param.default is inspect.Parameter.empty else repr(param.default)))
        return dict(token=token, parameters=parameters, files=source_files() if include_files else {}, names=list(self.namespace))

    def instantiate(self, token, name, values):
        if not name.isidentifier() or keyword.iskeyword(name) or name.startswith('_'):
            raise ValueError('invalid_name')
        if name in self.namespace:
            raise ValueError('name_exists')
        cls, signature = self.prepared[token]
        args, kwargs = evaluate_arguments(signature, values, self.namespace)
        instance = cls(*args, **kwargs)
        self.namespace[name] = instance
        return instance


def load_plugin(backend):
    session = InstantiationSession(vars(sys.modules['__main__']))

    def prepare(command):
        try:
            if command.get('loaded_token') is not None:
                result = session.prepare_class(session.prepared[command.loaded_token][0], include_files=False)
            else:
                result = (session.prepare_memory(command.sources, command.module, command.qualified_name)
                          if command.get('sources') is not None else session.prepare(command.path, command.qualified_name))
            return dict(result, request_id=command.request_id)
        except BaseException as exc:
            traceback.print_exception(exc, file=sys.stderr)
            return dict(error=str(exc), error_type=type(exc).__name__, request_id=command.request_id,
                        files=source_files())

    def load_diagram(command):
        try:
            return dict(session.load_diagram(command.sources, command.targets), request_id=command.request_id)
        except BaseException as exc:
            traceback.print_exception(exc, file=sys.stderr)
            return dict(error=str(exc), error_type=type(exc).__name__, request_id=command.request_id)

    def instantiate(command):
        try:
            session.instantiate(command.token, command.object_name, command.values)
            return dict(request_id=command.request_id, objects=snapshot(session.namespace,
                        representation_error=command.get('representation_error', '<Representation failed>'),
                        expanded=command.get('expanded', ()), item_limits=command.get('item_limits', {})))
        except BaseException as exc:
            traceback.print_exception(exc, file=sys.stderr)
            return dict(error=str(exc), error_type=type(exc).__name__, request_id=command.request_id)

    backend.add_command('thonny_se_load_diagram', load_diagram)
    backend.add_command('thonny_se_prepare_class', prepare)
    backend.add_command('thonny_se_instantiate', instantiate)
