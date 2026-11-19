# SPDX-FileCopyrightText: 2026 Sebastian Ladhoff
# SPDX-License-Identifier: GPL-3.0-only
# See LICENSE in the project root for the full license text.

"""Diagramm und Auswahlregeln, unabhängig von Thonny und Tk."""
from __future__ import annotations

from .i18n import tr
from dataclasses import dataclass
import copy

FORMAT = "thonny-se-structogram"
VERSION = 1
MAX_DEPTH = 12
MAX_NODES = 1000
LOOP_KINDS = {"while", "repeat", "for", "foreach"}
LOOP_FIELDS = {
    "repeat": ("count",),
    "for": ("variable", "start", "end", "step", "direction"),
    "foreach": ("element", "collection"),
}
IF_KINDS = {"if", "if_single"}


@dataclass(frozen=True)
class Selection:
    """Pfad zu einer Folge; index=None bezeichnet deren Körper, sonst einen Kopf."""
    path: tuple = ("body",)
    index: int | None = None
    at_start: bool = False
    end_index: int | None = None


def body_at(document, path):
    value = document
    for part in path:
        value = value[part]
    return value


def selected_node(document, selection):
    return None if selection.index is None else body_at(document, selection.path)[selection.index]


def new_node(kind):
    if kind == "try":
        return {"kind":"try", "body":[], "handlers":[], "else":None, "finally":[]}
    if kind == "switch":
        return {"kind": kind, "text": "", "cases": [
            {"value": "1", "body": []}, {"value": "2", "body": []}], "default": []}
    if kind == "if_single":
        return {"kind": kind, "text": "", "then": []}
    if kind == "repeat":
        return {"kind": kind, "count": "n", "body": []}
    if kind == "for":
        return {"kind": kind, "variable": "i", "start": "a", "end": "e",
                "step": "1", "direction": "up", "body": []}
    if kind == "foreach":
        return {"kind": kind, "element": "element", "collection": "liste", "body": []}
    node = {"kind": kind, "text": ""}
    if kind == "if":
        node.update({"then": [], "else": []})
    elif kind == "while":
        node["body"] = []
    elif kind not in ("statement", "call"):
        raise ValueError(tr('Unknown block type.'))
    return node


def insert_node(document, selection, kind):
    """Körper: am Ende hinein. Kopf: direkt dahinter. Danach immer neuer Kopf."""
    return insert_copy(document, selection, new_node(kind))


def insert_copy(document, selection, node):
    return insert_copies(document, selection, [node])


def insert_copies(document, selection, nodes):
    """Insert a group atomically, validating the combined model only once."""
    nodes = [copy.deepcopy(node) for node in nodes]
    if not nodes:
        raise ValueError(tr('The clipboard is empty.'))
    validate(dict(new_document(), body=nodes))
    body = body_at(document, selection.path)
    index = 0 if selection.at_start else len(body) if selection.index is None else (selection.end_index if selection.end_index is not None else selection.index) + 1
    body[index:index] = nodes
    try:
        validate(document)
    except ValueError:
        del body[index:index+len(nodes)]
        raise
    return Selection(selection.path, index,
                     end_index=index+len(nodes)-1 if len(nodes) > 1 else None)


def child_bodies(node):
    if node['kind'] == 'try':
        parts = [(('body',),node['body'],'try')]
        for index,handler in enumerate(node['handlers']):
            label = ('except*' if node.get('starred',False) else 'except')
            if handler['type']:label += ' '+handler['type']
            if handler['name']:label += ' as '+handler['name']
            parts.append((('handlers',index,'body'),handler['body'],label))
        for key in ('else','finally'):
            if node[key] is not None:parts.append(((key,),node[key],key))
        return parts
    if node["kind"] in LOOP_KINDS:
        return [(("body",), node["body"], tr('Loop body'))]
    if node["kind"] in IF_KINDS:
        result = [(("then",), node["then"], tr('true'))]
        if node["kind"] == "if":
            result.append((("else",), node["else"], tr('false')))
        return result
    if node["kind"] == "switch":
        return [(("cases", i, "body"), case["body"], case["value"] or tr('Case'))
                for i, case in enumerate(node["cases"])] + [(("default",), node["default"], tr('else'))]
    return []


def parent_selection(selection):
    path = selection.path
    if len(path) == 1:
        return selection
    if len(path) >= 4 and path[-3] in ("cases","handlers"):
        return Selection(path[:-4], path[-4])
    return Selection(path[:-2], path[-2])


def set_if_variant(node, with_else):
    if node["kind"] not in IF_KINDS:
        raise ValueError(tr('Not an if selection.'))
    if with_else:
        node["kind"] = "if"
        node.setdefault("else", [])
    else:
        if node.get("else"):
            raise ValueError(tr('The else branch contains blocks. Please move or remove them first.'))
        node["kind"] = "if_single"
        node.pop("else", None)


def delete_node(document, selection):
    if selection.index is None:
        return selection
    body = body_at(document, selection.path)
    del body[selection.index:(selection.end_index if selection.end_index is not None else selection.index)+1]
    if body:
        return Selection(selection.path, min(selection.index, len(body) - 1))
    return Selection(selection.path)


def move_node(document, selection, delta):
    if selection.index is None:
        return selection
    body = body_at(document, selection.path)
    end = selection.end_index if selection.end_index is not None else selection.index
    if delta < 0 and selection.index > 0:
        body[selection.index-1:end+1] = body[selection.index:end+1] + [body[selection.index-1]]
    elif delta > 0 and end < len(body)-1:
        body[selection.index:end+2] = [body[end+1]] + body[selection.index:end+1]
    else:
        return selection
    return Selection(selection.path, selection.index+delta,
                     end_index=end+delta if selection.end_index is not None else None)


def selected_nodes(document, selection):
    if selection.index is None:
        return []
    end = selection.end_index if selection.end_index is not None else selection.index
    return body_at(document, selection.path)[selection.index:end+1]


def move_selection(document, source, target):
    """Teilbäume atomar verschieben, auch bei sich ändernden Zielpfaden."""
    if source.index is None:
        return source
    end = source.end_index if source.end_index is not None else source.index
    prefix = source.path
    if target.path[:len(prefix)] == prefix and len(target.path) > len(prefix):
        child_index = target.path[len(prefix)]
        if source.index <= child_index <= end:
            raise ValueError(tr('A block cannot be moved into its own body.'))
    if target.path == source.path and target.index is not None and source.index <= target.index <= end:
        return source
    candidate = copy.deepcopy(document)
    origin = body_at(candidate, source.path)
    destination = body_at(candidate, target.path)
    index = 0 if target.at_start else len(destination) if target.index is None else (target.end_index if target.end_index is not None else target.index)+1
    moving = origin[source.index:end+1]
    if not moving:
        raise ValueError(tr('No blocks selected.'))
    if destination is origin:
        index -= sum(i < index for i in range(source.index, end+1))
    del origin[source.index:end+1]
    destination[index:index] = moving
    validate(candidate)

    def locate(body, path):
        if body is destination:
            return path
        for i, node in enumerate(body):
            for relative, nested, _ in child_bodies(node):
                found = locate(nested, path+(i,)+relative)
                if found is not None:
                    return found
        return None

    path = locate(candidate["body"], ("body",))
    if path is None:
        raise ValueError(tr('Invalid insertion target.'))
    document.clear()
    document.update(candidate)
    return Selection(path, index, end_index=index+len(moving)-1 if len(moving)>1 else None)


def new_document():
    return {"format": FORMAT, "version": VERSION, "title": "", "body": []}


def validate(document):
    if not isinstance(document, dict) or set(document) != {"format", "version", "title", "body"}:
        raise ValueError(tr('The file does not contain a valid Thonny SE model.'))
    if document["format"] != FORMAT or type(document["version"]) is not int or document["version"] != VERSION:
        raise ValueError(tr('This model format or version is not supported.'))
    if not isinstance(document["title"], str) or len(document["title"]) > 200:
        raise ValueError(tr('The diagram title must not exceed 200 characters.'))
    count = 0

    def check_body(body, depth):
        nonlocal count
        if not isinstance(body, list) or depth > MAX_DEPTH:
            raise ValueError(tr('Invalid diagram body or more than 12 nesting levels.'))
        for node in body:
            count += 1
            if count > MAX_NODES or not isinstance(node, dict):
                raise ValueError(tr('Invalid diagram or more than 1000 blocks.'))
            fields = {"statement": (), "call": (), "if": ("then", "else"),
                      "if_single": ("then",), "switch": ("cases", "default"),
                      "try": ("body","handlers","else","finally"),
                      **{kind: ("body",) for kind in LOOP_KINDS}}
            kind = node.get("kind")
            if not isinstance(kind, str) or kind not in fields:
                raise ValueError(tr('Unknown block type.'))
            text_fields = () if kind == "try" else LOOP_FIELDS.get(kind, ("text",))
            if set(node) - ({"enabled","starred"} if kind=="try" else {"enabled"}) != {"kind"} | set(text_fields) | set(fields[kind]):
                raise ValueError(tr('Invalid block fields.'))
            if "enabled" in node and type(node["enabled"]) is not bool:
                raise ValueError(tr('Invalid block activation state.'))
            if kind == 'try':
                handlers=node['handlers']
                if not isinstance(handlers,list) or len(handlers)>32 or type(node.get('starred',False)) is not bool:
                    raise ValueError(tr('Invalid exception handling block.'))
                if not handlers and node['finally'] is None or node['else'] is not None and not handlers:
                    raise ValueError(tr('Invalid exception handling block.'))
                check_body(node['body'],depth+1)
                for handler in handlers:
                    count += 1
                    if (count>MAX_NODES or not isinstance(handler,dict) or set(handler)!={'type','name','body'}
                            or not isinstance(handler['type'],str) or len(handler['type'])>1000
                            or not isinstance(handler['name'],str) or len(handler['name'])>200):
                        raise ValueError(tr('Invalid exception handling block.'))
                    check_body(handler['body'],depth+1)
                for key in ('else','finally'):
                    if node[key] is not None:check_body(node[key],depth+1)
                continue
            for field in text_fields:
                limit = 1000 if kind in LOOP_FIELDS else 10000
                if not isinstance(node[field], str) or len(node[field]) > limit:
                    raise ValueError(tr('Block text must not exceed {p0} characters.').format(p0=limit))
            if kind == "for" and node["direction"] not in ("up", "down"):
                raise ValueError(tr('The counting direction must be up or down.'))
            if kind == "switch":
                if not isinstance(node["cases"], list) or not 1 <= len(node["cases"]) <= 32:
                    raise ValueError(tr('A multiway selection requires 1 to 32 cases.'))
                for case in node["cases"]:
                    count += 1
                    if count > MAX_NODES:
                        raise ValueError(tr('The diagram contains more than 1000 blocks and cases.'))
                    if (not isinstance(case, dict) or set(case) != {"value", "body"}
                            or not isinstance(case["value"], str) or len(case["value"]) > 1000):
                        raise ValueError(tr('Invalid case in multiway selection.'))
                    check_body(case["body"], depth + 1)
                check_body(node["default"], depth + 1)
                continue
            for field in fields[kind]:
                check_body(node[field], depth + 1)
    check_body(document["body"], 0)
    return document


def set_selected_enabled(document, selection, enabled):
    """Change only selected roots; retain nested blocks' individual states."""
    for node in selected_nodes(document, selection):
        if enabled:
            node.pop('enabled', None)
        else:
            node['enabled'] = False


def active_body(nodes):
    """Independent export copy, excluding disabled roots and all their children."""
    result = []
    for original in nodes:
        if not original.get('enabled', True):
            continue
        node = copy.deepcopy(original)
        node.pop('enabled', None)
        for relative, body, _ in child_bodies(node):
            parent = node
            for part in relative[:-1]:
                parent = parent[part]
            parent[relative[-1]] = active_body(body)
        result.append(node)
    return result


def selection_enabled(document, selection):
    value = document
    for part in selection.path:
        value = value[part]
        if isinstance(value, dict) and not value.get('enabled', True):
            return False
    return True
