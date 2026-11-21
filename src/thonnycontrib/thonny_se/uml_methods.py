# SPDX-FileCopyrightText: 2026 Sebastian Ladhoff
# SPDX-License-Identifier: GPL-3.0-only
# See LICENSE in the project root for the full license text.

"""Strukturierte UML-Mitglieder und kompakte Signaturdarstellung."""
from .i18n import tr
import copy

VISIBILITIES = {"public": "+", "protected": "#", "private": "−"}


class MemberFieldError(ValueError):
    def __init__(self, message, field):
        super().__init__(message)
        self.field = field


def python_visibility(name):
    if name.startswith("__") and not name.endswith("__"):
        return "private"
    if name.startswith("_") and not name.startswith("__"):
        return "protected"
    return "public"


def display_member_name(name, visibility):
    if name == "_" or visibility == "public" or python_visibility(name) != visibility:
        return name
    return name[2 if visibility == "private" else 1:]



def validate_method(method):
    def text(value, limit=200):
        return isinstance(value, str) and len(value) <= limit and value == value.strip() and "\n" not in value and "\r" not in value
    if not isinstance(method, dict) or set(method) != {"kind", "name", "visibility", "parameters", "return_type"}:
        raise ValueError(tr('Invalid method details.'))
    if not isinstance(method["kind"], str) or not isinstance(method["visibility"], str) or method["kind"] not in ("procedure", "function", "constructor") or method["visibility"] not in VISIBILITIES:
        raise ValueError(tr('Please select a method kind and visibility.'))
    if not text(method["name"]) or (method["kind"] != "constructor" and not method["name"].isidentifier()):
        raise MemberFieldError(tr('Please enter a valid method name.'), "name")
    if method["kind"] == "constructor" and method["name"] not in ("", "__init__"):
        raise MemberFieldError(tr('Use __init__ for the constructor.'), "name")
    if not text(method["return_type"]) or (method["kind"] != "function" and method["return_type"]):
        raise MemberFieldError(tr('Only functions have a return type.'), "type")
    if method["kind"] == "function" and not method["return_type"]:
        raise MemberFieldError(tr('Please enter a return type for the function.'), "type")
    params = method["parameters"]
    if not isinstance(params, list) or len(params) > 100:
        raise ValueError(tr('At most 100 parameters per method.'))
    names = set()
    for index, param in enumerate(params):
        if not isinstance(param, dict) or set(param) - {"kind"} != {"name", "type", "default"}:
            raise ValueError(tr('Invalid parameter details.'))
        if param.get("kind", "positional") not in ("positional", "positional_only", "keyword_only", "vararg", "kwarg"):
            raise ValueError(tr('Invalid parameter details.'))
        for key, value in param.items():
            if not text(value, 500):
                raise MemberFieldError(tr('Please use short, single-line entries.'), (index, key))
        if not param["name"].isidentifier() or param["name"] in names or param["name"] in ("self", "cls"):
            raise MemberFieldError(tr('Parameter names must be unique; do not include self/cls.'), (index, "name"))
        names.add(param["name"])
    return method


def constructor_display_name(class_name):
    from .diagram_preferences import UML_CONSTRUCTOR_NAME, enabled
    return class_name if class_name and enabled(UML_CONSTRUCTOR_NAME) else "__init__"


def member_text(row, class_name):
    if "attribute" in row:
        data = row["attribute"]
        return VISIBILITIES[data["visibility"]] + " " + display_member_name(data["name"], data["visibility"]) + (": " + data["type"] if data["type"] else "") + (" = " + data["default"] if data["default"] else "")
    method = row["method"]
    name = constructor_display_name(class_name) if method["kind"] == "constructor" else display_member_name(method["name"], method["visibility"])
    signature = ("" if method["kind"] == "constructor" else VISIBILITIES[method["visibility"]] + " ") + name + parameter_text(method["parameters"])
    if method["kind"] == "function":
        signature += ": " + method["return_type"]
    return signature


def parameter_signature(parameters, render):
    values = []
    keyword_separator = False
    for index, param in enumerate(parameters):
        kind = param.get('kind', 'positional')
        if kind == 'keyword_only' and not keyword_separator:
            values.append('*')
            keyword_separator = True
        prefix = '*' if kind == 'vararg' else '**' if kind == 'kwarg' else ''
        values.append(prefix + render(param))
        if kind == 'vararg':
            keyword_separator = True
        if kind == 'positional_only' and (index+1 == len(parameters) or parameters[index+1].get('kind') != 'positional_only'):
            values.append('/')
    return ', '.join(values)


def parameter_text(parameters):
    def render(param):
        return (param['name'] + (': ' + param['type'] if param['type'] else '')
                + (' = ' + param['default'] if param['default'] else ''))
    return '(' + parameter_signature(parameters, render) + ')'


def member_parts(row, section, class_name=""):
    if section == "methods" and is_constructor(row):
        data, _ = draft_from_row(row)
        return {"name": constructor_display_name(class_name), "parameters": parameter_text(data["parameters"])}
    if section == "attributes":
        data = attribute_draft(row)
        return {
            "name": display_member_name(data["name"], data["visibility"]),
            "type": ": " + data["type"] if data["type"] else "",
            "default": " = " + data["default"] if data["default"] else "",
        }
    data, unparsed = draft_from_row(row)
    return {
        "name": display_member_name(data["name"], data["visibility"]),
        "parameters": parameter_text(data["parameters"]),
        "type": ": " + data["return_type"] if data["return_type"] else "",
    }


def draft_from_row(row):
    if row is None:
        return dict(kind="procedure", name="", visibility="public", parameters=[], return_type=""), False
    return copy.deepcopy(row["method"]), False


def attribute_draft(row):
    if row is None:
        return dict(name="", type="", default="", visibility="private")
    return copy.deepcopy(row["attribute"])


def validate_attribute(data):
    if not isinstance(data, dict) or set(data) != {"name", "type", "default", "visibility"}:
        raise ValueError(tr('Invalid attribute details.'))
    for key, value in data.items():
        if not isinstance(value, str) or value != value.strip() or len(value) > 500 or "\n" in value or "\r" in value:
            raise MemberFieldError(tr('Please use short, single-line entries.'), key)
    if not data["name"].isidentifier() or data["visibility"] not in VISIBILITIES:
        raise MemberFieldError(tr('Please enter an attribute name and select +, − or #.'), "name")
    return data



def is_constructor(row):
    method = row.get("method", {})
    return method.get("kind") == "constructor" or method.get("name") in ("__init__", "__new__")


def visible_methods(card):
    return [row for row in card["methods"] if not is_constructor(row) or constructor_parameters(row)]



def member_visibility(row, section):
    return row["attribute" if section == "attributes" else "method"]["visibility"]


def constructor_parameters(row):
    data, unparsed = draft_from_row(row)
    return data['parameters'] if not unparsed else []


def canonical_method_name(card, name):
    return '__init__' if name in ('__init__', card['name'], card.get('header', {}).get('name')) else name


def hidden_constructor(card):
    return next((row for row in card['methods'] if is_constructor(row) and draft_from_row(row)[0]['name'] in ('', '__init__') and not constructor_parameters(row)), None)


def accessor_name(kind, name, style=None):
    """Name generated accessors only; never rewrite user-defined methods."""
    import re
    from .diagram_preferences import method_style
    words = re.sub(r'([A-Z]+)([A-Z][a-z])', r'\1_\2', name)
    words = re.sub(r'([a-z0-9])([A-Z])', r'\1_\2', words).strip('_').split('_')
    words = [word for word in words if word]
    if (style or method_style()) == 'camelCase':
        return kind + ''.join(word[:1].upper()+word[1:].lower() for word in words)
    return kind + '_' + '_'.join(word.lower() for word in words)


def accessor_names(kind, name):
    # Accept both conventions (and legacy unnormalized names) to avoid duplicates.
    return {accessor_name(kind, name, 'snake_case'), accessor_name(kind, name, 'camelCase'), kind+'_'+name}


def method_suggestions(card, exclude=None):
    """Offer missing members and reopen an existing hidden constructor."""
    occupied = set()
    for row in card['methods']:
        data, unparsed = draft_from_row(row)
        if not unparsed:
            occupied.add('__init__' if is_constructor(row) else data['name'])
    result = {}
    if '__init__' not in occupied:
        result['__init__'] = {'method': dict(kind='constructor', name='__init__', visibility='public', parameters=[], return_type='')}
    hidden = hidden_constructor(card)
    if hidden is not None and exclude is None:
        data, _ = draft_from_row(hidden)
        result['__init__'] = {'method': {**data, 'kind': 'constructor', 'name': '__init__'}, 'existing_id': hidden['id']}
    for row in card['attributes']:
        data = attribute_draft(row)
        name = display_member_name(data['name'], data['visibility'])
        for kind in ('get', 'set'):
            method_name = accessor_name(kind, name)
            if accessor_names(kind, name) & occupied:
                continue
            getter = kind == 'get'
            result[method_name] = {'method': dict(name=method_name, visibility='public',
                kind='function' if getter else 'procedure', return_type=(data['type'] or 'object') if getter else '',
                parameters=[] if getter else [dict(name='wert',type=data['type'],default='')]),
                'accessor':dict(attribute=row['id'],kind=kind)}
    return result
