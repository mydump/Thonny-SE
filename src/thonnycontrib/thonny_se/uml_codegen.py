# SPDX-FileCopyrightText: 2026 Sebastian Ladhoff
# SPDX-License-Identifier: GPL-3.0-only
# See LICENSE in the project root for the full license text.

"""Generate Python declarations from UML classes."""
from .i18n import tr
import ast
import keyword
from unicodedata import normalize

from .uml_methods import (
    attribute_draft, display_member_name, draft_from_row, python_visibility,
    validate_attribute, validate_method, visible_methods, is_constructor, parameter_signature,
)


def _identifier(name, description):
    normalized = normalize("NFKC", name)
    if not normalized.isidentifier() or keyword.iskeyword(normalized):
        raise ValueError(tr('{p0}: {p1!r} is not a valid Python name.').format(p0=description, p1=name))
    return normalized


def _member_name(data):
    name = data["name"]
    base = display_member_name(name, python_visibility(name))
    prefix = {"public": "", "protected": "_", "private": "__"}[data["visibility"]]
    name = _identifier(prefix + base, tr('Class member'))
    if python_visibility(name) != data["visibility"]:
        raise ValueError(tr('The selected visibility cannot be represented for {p0!r}.').format(p0=name))
    return name


def _expression(value, label):
    try:
        return ast.unparse(ast.parse(value, mode="eval").body)
    except SyntaxError as exc:
        raise ValueError(tr('{p0}: {p1!r} is not a valid Python expression.').format(p0=label, p1=value)) from exc


def _declaration(name, typename, default):
    if typename:
        name += ": " + _expression(typename, tr('Type'))
    if default:
        name += " = " + _expression(default, tr('Default value'))
    return name


def attribute_code(row):
    data = validate_attribute(attribute_draft(row))
    name = _member_name(data)
    declaration = _declaration(name, data["type"], data["default"])
    if not data["type"] and not data["default"]:
        declaration += " = None"
    return name, declaration


def instance_attribute_code(row, receiver="self"):
    name, declaration = attribute_code(row)
    if not attribute_draft(row)["default"] and not declaration.endswith(" = None"):
        declaration += " = None"
    return name, f"{receiver}.{declaration}"


def constructor_lines(has_bases):
    if has_bases:
        return ["def __init__(self, *args, **kwargs):", "    super().__init__(*args, **kwargs)"]
    return ["def __init__(self):"]


def method_code(row, receiver="self", *, asynchronous=False):
    method, unparsed = draft_from_row(row)
    if unparsed:
        raise ValueError(tr('The method declaration {p0!r} cannot be read as a Python signature.').format(p0=row['text']))
    validate_method(method)
    name = "__init__" if is_constructor(row) else _member_name(method)
    parameters = [receiver] if receiver else []
    signature = parameter_signature(method['parameters'], lambda param:
        _declaration(_identifier(param['name'], tr('Parameter')), param['type'], param['default']))
    if signature:
        parameters.append(signature)
    result = " -> " + _expression(method["return_type"], tr('Return type')) if method["return_type"] else ""
    prefix = "async def" if asynchronous else "def"
    return name, f"{prefix} {name}({', '.join(parameters)}){result}:"


def class_header(header):
    name = _identifier(header["name"], tr('Class'))
    bases = header["bases"].strip()
    if len(name) > 200 or len(bases) > 4000:
        raise ValueError(tr('The class name or list of base classes is too long.'))
    declaration = f"class {name}" + (f"({bases}):" if bases else ":")
    try:
        tree = ast.parse(declaration + "\n    pass")
    except SyntaxError as exc:
        raise ValueError(tr('Invalid class header: {p0}').format(p0=exc.msg)) from exc
    if len(tree.body) != 1 or len(tree.body[0].body) != 1 or not isinstance(tree.body[0].body[0], ast.Pass):
        raise ValueError(tr('Please enter only base classes and class options.'))
    return declaration


def header_data(node):
    return {"name": node.name, "bases": ", ".join(ast.unparse(item) for item in (*node.bases, *node.keywords))}


def method_body(card, row):
    accessor = row.get("accessor")
    if accessor is None:
        return "pass"
    attribute = next(item for item in card["attributes"] if item["id"] == accessor["attribute"])
    name = _member_name(attribute["attribute"])
    if accessor["kind"] == "get":
        return f"return self.{name}"
    parameters = row["method"]["parameters"]
    value = parameters[0]["name"] if parameters else "wert"
    return f"self.{name} = {value}"


def generate_class(card, *, include_imports=True, inherited=()):
    from .uml_python_semantics import abstract_method, generated_header, required_imports, validate_abstract_class
    validate_abstract_class(card, inherited)
    header = class_header(generated_header(card))
    body = []
    used = set()

    def add_member(name, code):
        if name in used:
            raise ValueError(tr('The class member {p0!r} occurs more than once.').format(p0=name))
        used.add(name)
        body.append(code)

    constructors = [row for row in card['methods'] if is_constructor(row)]
    if len(constructors) > 1:
        raise ValueError(tr('This class already has a constructor.'))
    if card['attributes'] or constructors:
        node = ast.parse(header + "\n    pass").body[0]
        has_bases = any(ast.unparse(base) not in ('abc.ABC','typing.Protocol') for base in node.bases)
        lines = [method_code(constructors[0])[1]] if constructors else constructor_lines(has_bases)
        if constructors and has_bases:
            lines.append('    super().__init__()')
        for row in card['attributes']:
            name, declaration = instance_attribute_code(row)
            if name in used:
                raise ValueError(tr('The class member {p0!r} occurs more than once.').format(p0=name))
            used.add(name)
            lines.append('    ' + declaration)
        if len(lines) == 1:
            lines.append('    pass')
        body.extend('    ' + line + '\n' for line in lines)

    for row in visible_methods(card):
        if is_constructor(row):
            continue
        name, signature = method_code(row)
        decorator = "    @abc.abstractmethod\n" if abstract_method(card, row) else ""
        add_member(name, ("\n" if body else "") + decorator + f"    {signature}\n        {method_body(card, row)}\n")

    code = header + "\n" + ("".join(body) if body else "    pass\n")
    try:
        compile(code, "<Thonny-SE-Klasse>", "exec")
    except SyntaxError as exc:
        raise ValueError(tr('The class definition is invalid: {p0}').format(p0=exc.msg)) from exc
    imports = required_imports([card]) if include_imports else []
    return ("\n".join(imports)+"\n\n" if imports else "")+code

def generate_diagram(cards):
    """Put local base classes ahead of subclasses in the generated module."""
    cards = list(cards)
    from .uml_python_semantics import abstract_contracts, validate_interfaces
    validate_interfaces(cards)
    contracts = abstract_contracts(cards)
    definitions = {}
    dependencies = {}
    for card in cards:
        code = generate_class(card, include_imports=False, inherited=contracts[card["id"]][1])
        node = ast.parse(code).body[0]
        if node.name in definitions:
            raise ValueError(tr('Multiple cards use the Python class name {p0!r}.').format(p0=node.name))
        definitions[node.name] = code
        bases = (base.value if isinstance(base, ast.Subscript) else base for base in node.bases)
        dependencies[node.name] = {base.id for base in bases if isinstance(base, ast.Name)}

    remaining = set(definitions)
    ordered = []
    while remaining:
        ready = [name for name in definitions
                 if name in remaining and not (dependencies[name] & remaining)]
        if not ready:
            raise ValueError(tr('The classes cannot be ordered because of cyclic inheritance.'))
        ordered.extend(definitions[name].rstrip() for name in ready)
        remaining.difference_update(ready)
    from .uml_python_semantics import required_imports
    imports = ["from __future__ import annotations", *required_imports(cards)]
    return "\n".join(imports)+"\n\n\n"+"\n\n\n".join(ordered)+"\n"
