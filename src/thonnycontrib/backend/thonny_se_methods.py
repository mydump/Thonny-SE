# SPDX-FileCopyrightText: 2026 Sebastian Ladhoff
# SPDX-License-Identifier: GPL-3.0-only
# See LICENSE in the project root for the full license text.

"""Prepare and call real instance methods without evaluating annotations/properties."""
import ast
import inspect
import sys
import traceback
import textwrap
import types
import uuid

from .thonny_se_instantiation import evaluate_arguments
from .thonny_se_objects import snapshot, resolve_object


def resolve_method(obj, name):
    member = inspect.getattr_static(obj, name)
    if isinstance(member, staticmethod):
        function, receiver = member.__func__, None
    elif isinstance(member, classmethod):
        function, receiver = member.__func__, type(obj)
    elif isinstance(member, types.FunctionType):
        function, receiver = member, obj
    else:
        raise ValueError('unsupported_method')
    # Functions assigned directly to an instance are not bound Python methods.
    if inspect.getattr_static(type(obj), name, None) is not member:
        raise ValueError('unsupported_method')
    if inspect.iscoroutinefunction(function):
        raise ValueError('async_method')
    return function, receiver


def describe_method(function, receiver):
    # Do not invoke lazy Python 3.14 annotations, __signature__ or __wrapped__.
    clone = types.FunctionType(function.__code__, function.__globals__, function.__name__,
                               function.__defaults__, function.__closure__)
    clone.__kwdefaults__ = function.__kwdefaults__
    signature = inspect.signature(clone, follow_wrapped=False)
    annotations = {}
    try:
        node = ast.parse(textwrap.dedent(inspect.getsource(function))).body[0]
        args = node.args
        arguments = args.posonlyargs + args.args + args.kwonlyargs
        arguments += [arg for arg in (args.vararg, args.kwarg) if arg]
        annotations = {arg.arg: ast.unparse(arg.annotation) for arg in arguments if arg.annotation}
    except (OSError, TypeError, SyntaxError, IndexError, AttributeError):
        pass  # Shell-defined methods may not have retrievable source.
    parameters = list(signature.parameters.values())
    if receiver is not None:
        # Bind the implicit receiver even for unusual `def method(*args)` forms.
        if parameters and parameters[0].kind in (inspect.Parameter.POSITIONAL_ONLY,
                                                 inspect.Parameter.POSITIONAL_OR_KEYWORD):
            parameters = parameters[1:]
        else:
            raise ValueError('unsupported_method')
    signature = signature.replace(parameters=parameters)
    fields = [dict(name=param.name, kind=param.kind.name,
                   required=param.default is param.empty and param.kind not in (param.VAR_POSITIONAL, param.VAR_KEYWORD),
                   default='' if param.default is param.empty else repr(param.default),
                   annotation=annotations.get(param.name, '')) for param in parameters]
    return signature, fields


class MethodSession:
    def __init__(self, namespace):
        self.namespace = namespace
        self.prepared = {}

    def prepare(self, object_name, object_id, method):
        obj = resolve_object(self.namespace, object_name)
        if obj is None or id(obj) != object_id:
            raise ValueError('stale_object')
        function, receiver = resolve_method(obj, method)
        signature, parameters = describe_method(function, receiver)
        # A single dialog can be active; release references from earlier dialogs.
        self.prepared.clear()
        token = uuid.uuid4().hex
        self.prepared[token] = object_name, obj, method, function, receiver, signature
        return dict(token=token, parameters=parameters, documentation=(inspect.getdoc(function) or '')[:2400],
                    signature=str(signature))

    def call(self, token, values):
        name, obj, method, function, receiver, signature = self.prepared[token]
        if resolve_object(self.namespace, name) is not obj:
            raise ValueError('stale_object')
        current, current_receiver = resolve_method(obj, method)
        if current is not function or current_receiver is not receiver:
            raise ValueError('stale_object')
        args, kwargs = evaluate_arguments(signature, values, self.namespace)
        if receiver is not None:
            args.insert(0, receiver)
        return function(*args, **kwargs)


def load_plugin(backend):
    session = MethodSession(vars(sys.modules['__main__']))

    def prepare(command):
        try:
            return dict(session.prepare(command.object_name, command.object_id, command.method),
                        request_id=command.request_id)
        except BaseException as exc:
            traceback.print_exception(exc, file=sys.stderr)
            return dict(error=str(exc), error_type=type(exc).__name__, request_id=command.request_id)

    def call(command):
        response = dict(request_id=command.request_id)
        try:
            result = session.call(command.token, command.values)
            try:
                response['result'] = repr(result)[:2000]
            except Exception:
                response['result'] = command.get('representation_error', '<Representation failed>')
        except BaseException as exc:
            traceback.print_exception(exc, file=sys.stderr)
            response.update(error=str(exc), error_type=type(exc).__name__)
        # A failed method may already have changed state; refresh on both paths.
        response.update(objects=snapshot(session.namespace,
                        representation_error=command.get('representation_error', '<Representation failed>'),
                        expanded=command.get('expanded', ()), item_limits=command.get('item_limits', {})))
        return response

    backend.add_command('thonny_se_prepare_method', prepare)
    backend.add_command('thonny_se_call_method', call)
