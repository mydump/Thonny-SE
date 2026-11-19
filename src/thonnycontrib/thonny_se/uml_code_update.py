# SPDX-FileCopyrightText: 2026 Sebastian Ladhoff
# SPDX-License-Identifier: GPL-3.0-only
# See LICENSE in the project root for the full license text.

"""Plan small source edits for one Python class, keeping surrounding text intact."""
from .i18n import tr
import ast
from functools import cached_property
from bisect import bisect_left, bisect_right
from itertools import islice
from collections import defaultdict
from dataclasses import dataclass
from io import StringIO
import tokenize

from .uml_python_semantics import generated_header, abstract_method, abstract_decorator, imported_names, validate_abstract_class
from .uml_codegen import attribute_code, class_header, constructor_lines, header_data, instance_attribute_code, method_body, method_code
from .uml_import import ParsedSource, _classes, constructor_receiver, instance_assignments, linked_class_node, parse_linked_class, parse_tree
from .uml_methods import attribute_draft, member_text, visible_methods, is_constructor
from .uml_source import SECTIONS, _fingerprint


UPDATE_CODE_LABEL = tr('Update code from class')
FUNCTIONS = (ast.FunctionDef, ast.AsyncFunctionDef)


@dataclass
class Change:
    group: str
    before: str
    after: str = ""
    patch: tuple | None = None
    addition: str = ""
    selected: bool = False
    note: str = ""
    section: str = ""
    row_id: str = ""
    old_name: str = ""
    new_name: str = ""
    removed_node: ast.AST | None = None

    @property
    def selectable(self):
        return self.patch is not None or bool(self.addition)


def changes_code(change, text):
    if change.group == 'same':
        return False
    if change.addition:
        return True
    if change.patch is not None:
        start, end, replacement = change.patch
        return text[start:end] != replacement
    return bool(change.after or change.note)


class CodeSource(ParsedSource):
    @cached_property
    def lines(self):
        return self.source.split('\n')

    @cached_property
    def offsets(self):
        offsets = [0]
        for line in self.lines:
            offsets.append(offsets[-1]+len(line)+1)
        return offsets

    @cached_property
    def tokens(self):
        return list(tokenize.generate_tokens(StringIO(self.source).readline))


    @cached_property
    def token_offsets(self):
        return [self.offsets[token.start[0]-1]+token.start[1] for token in self.tokens]

    def tokens_between(self, start, end=None):
        first = bisect_left(self.token_offsets, start)
        last = len(self.tokens) if end is None else bisect_right(self.token_offsets, end)
        return islice(self.tokens, first, last)


class CodeUpdate:
    def __init__(self, source, card, *, analysis=None):
        self.source, self.card = source, card
        self.identity = card["source"]["class"]
        self.path = card["source"]["path"]
        analysis = analysis if analysis is not None else CodeSource(source)
        if analysis.source != source:
            raise ValueError('Source analysis does not match the supplied text')
        self.analysis = analysis
        self.lines, self.offsets = analysis.lines, analysis.offsets
        self.node = analysis.node(self.identity)
        # Analyze all siblings once, then attach an independent linked card.
        siblings = analysis.cards()
        self.incoming = analysis.linked(self.path, self.identity)
        self.tokens = analysis.tokens
        self.aliases = analysis.aliases
        from .uml_python_semantics import abstract_contracts, validate_interfaces
        siblings = [item for item in siblings if item.get('header',{}).get('name') != self.node.name] + [card]
        validate_interfaces(siblings)
        # Only abstract cards need the inherited-method contract check.
        # Concrete/interface cards cannot fail validate_abstract_class.
        if card.get('class_kind') == 'abstract':
            validate_abstract_class(card, abstract_contracts(siblings)[card['id']][1])
        self.header = self._class_change()
        self.changes = self._member_changes()

    def _offset(self, position):
        line, column = position
        return self.offsets[line-1] + column

    def _start(self, node):
        return self._ast_offset(node.lineno, node.col_offset)

    def _end(self, node):
        return self._ast_offset(node.end_lineno, node.end_col_offset)

    def _ast_offset(self, line, column):
        prefix = self.lines[line-1].encode("utf-8")[:column].decode("utf-8")
        return self.offsets[line-1] + len(prefix)

    def _header_span(self, node):
        start = self._start(node)
        depth = 0
        comment = False
        for token in self.analysis.tokens_between(start):
            if token.type == tokenize.COMMENT:
                comment = True
            if token.type != tokenize.OP:
                continue
            if token.string in ("(", "[", "{"):
                depth += 1
            elif token.string in (")", "]", "}"):
                depth -= 1
            elif token.string == ":" and depth == 0:
                # A lambda return annotation can have a colon before the header ends.
                returns = getattr(node, "returns", None)
                if returns is None or self._offset(token.start) >= self._end(returns):
                    return start, self._offset(token.end), comment
        raise ValueError(tr('The class or method header could not be read unambiguously.'))

    def _class_change(self):
        current = self.incoming["header"]
        desired = generated_header(self.card)
        start, end, comment = self._header_span(self.node)
        change = Change("header", self.source[start:end])
        if desired == current:
            return change
        try:
            change.after = class_header(desired)
            if getattr(self.node, "type_params", None) or comment:
                raise ValueError(tr('This class header contains comments or type parameters. Please edit it directly in Python.'))
            if desired["name"] != current["name"]:
                next_identity = ".".join((*self.identity.split(".")[:-1], desired["name"]))
                if any(name == next_identity for _, name in self.analysis.classes):
                    raise ValueError(tr('The new class name is already used in this scope.'))
            change.patch = (start, end, change.after)
            change.note = tr('Renaming does not update call sites or other classes.')
        except ValueError as exc:
            change.note = str(exc)
        return change

    def _locations(self):
        methods = defaultdict(list)
        attributes = defaultdict(list)
        for member in self.node.body:
            if not isinstance(member, FUNCTIONS):
                continue
            methods[member.name].append(member)
            receiver = constructor_receiver(member)
            if receiver is not None:
                for assignment, target in instance_assignments(member.body, receiver):
                    attributes[target.attr].append((assignment, target))
        return {"attributes": attributes, "methods": methods}

    def _member_changes(self):
        locations = self._locations()
        changes = []
        desired_names = set()
        for section, kind in SECTIONS.items():
            existing = defaultdict(list)
            for row in self.incoming[section]:
                existing["__init__" if kind == "method" and is_constructor(row) else row[kind]["name"]].append(row)
            baseline = {row["id"]: row for row in self.card["source"]["baseline"][section]}
            local = self.card[section] if kind == "attribute" else self.card["methods"]
            consumed = set()
            for row in local:
                previous = baseline.get(row["id"])
                if previous:
                    consumed.add(previous["name"])
                try:
                    renderer = attribute_code if kind == "attribute" else method_code
                    name, desired = renderer(row)
                    old_name = previous["name"] if previous and previous["name"] in existing else name
                    found = existing.get(old_name, [])
                    consumed.add(old_name)
                    if name in desired_names:
                        raise ValueError(tr('This Python name occurs more than once on the card.'))
                    desired_names.add(name)
                    change = self._plan_member(section, row, previous, name, desired, old_name, found, locations)
                except (ValueError, SyntaxError) as exc:
                    change = Change("update", member_text(row, self.card["name"]), note=str(exc))
                changes.append(change)
            for name, rows in existing.items():
                if name not in consumed:
                    if section == 'methods' and name == '__init__' and not any(
                            entry['name'] == '__init__' for entry in baseline.values()):
                        # Older files did not model constructors. Absence there is
                        # not an instruction to delete their Python implementation.
                        continue
                    targets = locations[section][name]
                    changes.append(self._plan_delete(section, name, rows, targets, locations["attributes"]))
        return changes

    def _plan_member(self, section, row, previous, name, desired, old_name, found, locations):
        kind = SECTIONS[section]
        renderer = attribute_code if kind == "attribute" else method_code
        if not found:
            change = Change("add", desired, selected=previous is None, section=section, row_id=row["id"], new_name=name)
            if any(mapping.get(name) for mapping in locations.values()) or (kind == "method" and self._other_class_binding(name)):
                change.note = tr('This name is already used in the Python class.')
            else:
                if kind == "attribute":
                    constructors = locations["methods"]["__init__"]
                    receiver = constructor_receiver(constructors[0]) if len(constructors) == 1 else None
                    if (constructors and (receiver is None
                                          or any(isinstance(node, ast.Return) for node in ast.walk(constructors[0])))
                            or (not constructors and self._other_class_binding("__init__"))):
                        change.note = tr('Please add the attribute to this constructor directly in Python.')
                        return change
                    _, change.addition = instance_attribute_code(row, receiver or "self")
                    change.before = change.addition
                else:
                    decorator = '@abc.abstractmethod\n' if abstract_method(self.card,row) else ''
                    change.addition = decorator + desired + "\n    " + method_body(self.card, row)
                try:
                    ast.parse(change.addition)
                except SyntaxError as exc:
                    change.addition = ""
                    change.note = tr('Invalid declaration: {p0}').format(p0=exc.msg)
                    return change
                if previous:
                    change.note = tr('This entry has since been removed from Python.')
            return change
        targets = locations[section][old_name]
        same = all(renderer(remote)[1] == desired for remote in found)
        if kind == 'method':
            same = same and all(remote.get('abstract',False) == abstract_method(self.card,row) for remote in found)
        if kind == "attribute" and len(targets) == 1 and isinstance(targets[0][1], ast.Attribute):
            data = attribute_draft(row)
            node, _ = targets[0]
            if data["default"] and node.value is not None:
                proposed = ast.parse(desired).body[0]
                previous_data = found[0]["attribute"]
                same = (name == old_name and data["type"] == previous_data["type"]
                        and ast.unparse(node.value) == ast.unparse(proposed.value))
        if same:
            return Change("same", member_text(row, self.card["name"]))
        change = Change("update", member_text(found[0], self.card["name"]), desired,
                        section=section, row_id=row["id"], old_name=old_name, new_name=name)
        if len(found) != 1 or len(targets) != 1:
            change.note = tr('The name has multiple or ambiguous definitions in Python.')
            return change
        if old_name != name and (any(mapping.get(name) for mapping in locations.values())
                                 or (kind == "method" and self._other_class_binding(name))):
            change.note = tr('The new name is already used in the Python class.')
            return change
        try:
            if kind == "method":
                if "accessor" in row:
                    expected = ast.parse(method_body(self.card, row)).body
                    actual = targets[0].body
                    if [ast.dump(item) for item in actual] != [ast.dump(item) for item in expected]:
                        raise ValueError(tr('The accessor has a different method body. Please adjust it directly in Python.'))
                change.patch, change.before, change.after = self._method_patch(targets[0], row)
            else:
                change.patch, change.before, change.after = self._attribute_patch(*targets[0], row, name, desired)
            changed_in_python = previous is None or previous["digest"] != _fingerprint(found[0])
            change.selected = not changed_in_python and old_name == name
            if changed_in_python:
                change.note = tr('The Python version was changed independently or has not been synchronized yet.')
            elif old_name != name:
                change.note = tr('Call sites and attribute accesses must be checked when renaming.')
        except (ValueError, SyntaxError) as exc:
            change.note = str(exc)
        return change

    def _other_class_binding(self, name):
        pending = list(self.node.body)
        while pending:
            node = pending.pop()
            if isinstance(node, (ast.ClassDef, *FUNCTIONS)):
                if node.name == name:
                    return True
                continue
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store) and node.id == name:
                return True
            if isinstance(node, ast.alias) and (node.asname or node.name.split(".")[0]) == name:
                return True
            pending.extend(ast.iter_child_nodes(node))
        return False

    def _method_patch(self, node, row):
        args = node.args
        decorators = {ast.unparse(item) for item in node.decorator_list}
        receiver = args.args[0] if args.args and "staticmethod" not in decorators else None
        if (args.posonlyargs or args.kwonlyargs or args.vararg or args.kwarg or getattr(node, "type_params", None)
                or receiver and (receiver.annotation or len(args.defaults) == len(args.args))):
            raise ValueError(tr('This Python signature contains details that cannot be edited in the diagram.'))
        start, end, comment = self._header_span(node)
        if comment:
            raise ValueError(tr('This method header contains comments. Please edit it directly in Python.'))
        _, header = method_code(row, receiver.arg if receiver else None, asynchronous=isinstance(node, ast.AsyncFunctionDef))
        proposed = ast.parse(header + "\n    pass").body[0]
        removed = {arg.arg for arg in args.args} - {arg.arg for arg in proposed.args.args}
        used = {part.id for statement in node.body for part in ast.walk(statement) if isinstance(part, ast.Name)}
        if removed & used:
            raise ValueError(tr('Parameters used in the method body must first be adjusted in Python.'))
        current_abstract = any(abstract_decorator(item,self.aliases) for item in node.decorator_list)
        desired_abstract = abstract_method(self.card,row)
        if current_abstract != desired_abstract:
            decorators = []
            for item in node.decorator_list:
                if item.lineno != item.end_lineno:
                    raise ValueError(tr('Please change multiline decorators directly in Python.'))
                if not abstract_decorator(item,self.aliases):
                    decorators.append('@'+self.source[self._start(item):self._end(item)])
            if node.decorator_list:
                first = min(item.lineno for item in node.decorator_list)
                start = self.offsets[first-1] + node.col_offset
                if '#' in self.source[start:self._start(node)]:
                    raise ValueError(tr('Please change commented decorators directly in Python.'))
            if desired_abstract:
                decorators.append('@abc.abstractmethod')
            indent = self.lines[node.lineno-1][:node.col_offset]
            header = ('\n'+indent).join([*decorators,header])
        return (start, end, header), self.source[start:end], header

    def _attribute_patch(self, node, target, row, name, desired):
        if isinstance(node, ast.Assign) and len(node.targets) != 1:
            raise ValueError(tr('Please edit multiple assignments directly in Python.'))
        start, end = self._start(node), self._end(node)
        if any(token.type == tokenize.COMMENT and start <= self._offset(token.start) < end for token in self.analysis.tokens_between(start, end)):
            raise ValueError(tr('This assignment contains comments. Please edit it directly in Python.'))
        if isinstance(target, ast.Attribute):
            proposed = ast.parse(desired).body[0]
            data = attribute_draft(row)
            name = self.source[self._start(target.value):self._end(target.value)] + "." + name
            annotation = ": " + ast.unparse(proposed.annotation) if isinstance(proposed, ast.AnnAssign) else ""
            if data["default"]:
                value = ast.unparse(proposed.value)
            else:
                value = ""
                if node.value is not None:
                    # The annotation may be parenthesized; keep the assignment from its actual equals token.
                    left = self._end(target if isinstance(node, ast.Assign) else node.annotation)
                    equals = next(token for token in self.analysis.tokens_between(left, self._start(node.value))
                                  if token.type == tokenize.OP and token.string == "="
                                  and left <= self._offset(token.start) <= self._start(node.value))
                    value = " " + self.source[self._offset(equals.start):end]
                if value:
                    desired = name + annotation + value
                    return (start, end, desired), self.source[start:end], desired
                value = ""
            desired = name + annotation + (" = " + value if value else "")
            if not annotation and not value:
                raise ValueError(tr('This instance variable needs an assignment or type annotation.'))
        return (start, end, desired), self.source[start:end], desired

    def _plan_delete(self, section, name, rows, targets, attributes):
        change = Change("delete", member_text(rows[0], self.card["name"]), section=section, old_name=name)
        if len(rows) != 1 or len(targets) != 1:
            change.note = tr('The entry has multiple or ambiguous definitions in Python.')
            return change
        if section == "methods":
            node = targets[0]
            first = min([node.lineno, *(decorator.lineno for decorator in node.decorator_list)])
            start, end = self.offsets[first-1], min(len(self.source), self.offsets[node.end_lineno])
            live_attributes = set()
            for row in self.card["attributes"]:
                if "attribute" in row:
                    live_attributes.add(row["attribute"]["name"])
            live_ids = {row["id"] for row in self.card["attributes"]}
            live_attributes.update(row["name"] for row in self.card["source"]["baseline"]["attributes"]
                                   if row["id"] in live_ids)
            if any(start <= self._start(assignment) < end
                   for attribute in live_attributes for assignment, _ in attributes[attribute]):
                change.note = tr('The method assigns attributes that will remain on the card.')
                return change
            change.note = tr('The method and its implementation will be removed.')
        else:
            node, _ = targets[0]
            start, end = self._start(node), self._end(node)
            if isinstance(node, ast.Assign) and len(node.targets) != 1:
                change.note = tr('Please edit multiple assignments directly in Python.')
                return change
            change.note = tr('The assignment will be removed.')
        if section == "attributes":
            if node not in self.node.body or node.lineno == self.node.lineno:
                change.patch = (start, end, "pass")
                return change
            prefix = self.source[self.offsets[node.lineno-1]:start]
            suffix = self.source[end:self.offsets[node.end_lineno]].strip()
            if prefix.strip() or (suffix and not suffix.startswith("#")):
                change.note = tr('This line contains multiple statements. Please edit it directly in Python.')
                return change
            start, end = self.offsets[node.lineno-1], min(len(self.source), self.offsets[node.end_lineno])
        change.patch = (start, end, "")
        change.removed_node = node
        return change

    def _suite_indent(self, node):
        first = node.body[0]
        if first.lineno == node.lineno:
            start = self._start(node)-self.offsets[node.lineno-1]
            prefix = self.lines[node.lineno-1][:start]
            return prefix + ("\t" if prefix.endswith("\t") else "    ")
        line = self.lines[min([first.lineno, *(item.lineno for item in getattr(first, "decorator_list", ()))])-1]
        return line[:len(line)-len(line.lstrip())]

    def _append_suite(self, node, additions, patches, insertions):
        indent = self._suite_indent(node)
        if node.body[0].lineno == node.lineno:
            _, colon, _ = self._header_span(node)
            patches.append((colon, self._start(node.body[0]), "\n" + indent))
        end = min(len(self.source), self.offsets[node.end_lineno])
        lines = insertions.setdefault(end, [])
        unit = "\t" if indent.endswith("\t") else "    "
        lines.extend(indent + unit + line[4:] if line.startswith("    ") else indent + line
                     for item in additions for line in item.split("\n"))

    def apply(self, selected):
        deletions = [change.patch for change in selected if change.group == "delete" and change.patch]
        patches = [
            change.patch for change in selected if change.patch is not None
            and not (change.group == "delete" and any(
                outer[0] <= change.patch[0] and change.patch[1] <= outer[1] and outer != change.patch
                for outer in deletions
            ))
        ]
        attributes = [change.addition for change in selected if change.addition and change.section == "attributes"]
        additions = [change.addition for change in selected if change.addition and change.section != "attributes"]
        insertions = {}
        if attributes:
            ctor = next((node for node in self.node.body if constructor_receiver(node) is not None), None)
            if ctor is not None:
                self._append_suite(ctor, attributes, patches, insertions)
            else:
                has_bases = bool(self.node.bases)
                if self.header in selected:
                    has_bases = bool(ast.parse(self.header.after + "\n    pass").body[0].bases)
                planned = next((index for index, item in enumerate(additions)
                                if item.startswith('def __init__(')), None)
                if planned is None:
                    additions.insert(0, "\n".join([*constructor_lines(has_bases), *("    " + item for item in attributes)]))
                else:
                    additions[planned] += "\n" + "\n".join("    " + item for item in attributes)
        if additions:
            self._append_suite(self.node, additions, patches, insertions)
        elif all(node in {change.removed_node for change in selected} for node in self.node.body):
            end = min(len(self.source), self.offsets[self.node.end_lineno])
            patches.append((end, end, self._suite_indent(self.node) + "pass\n"))
        for end, lines in insertions.items():
            prefix = "" if self.source[:end].endswith("\n") else "\n"
            patches.append((end, end, prefix + "\n".join(lines) + "\n"))
        pieces = '\n'.join((change.after or change.addition) for change in selected)
        modules = [name for name in ('abc','typing') if name+'.' in pieces and self.aliases.get(name) != name]
        if modules:
            tree = parse_tree(self.source)
            for node in tree.body:
                bound = ({node.name} if isinstance(node,(ast.ClassDef,ast.FunctionDef,ast.AsyncFunctionDef)) else
                         {part.id for part in ast.walk(node) if isinstance(part,ast.Name) and isinstance(part.ctx,ast.Store)})
                if bound.intersection(modules):
                    raise ValueError(tr('The Python names abc or typing are already used. Please adjust the imports directly in Python.'))
            offset = 0
            for index,node in enumerate(tree.body):
                if ((index == 0 and isinstance(node,ast.Expr) and isinstance(node.value,ast.Constant) and isinstance(node.value.value,str))
                    or (isinstance(node,ast.ImportFrom) and node.module == '__future__')):
                    offset = self.offsets[node.end_lineno]
                else:
                    break
            patches.append((offset,offset,''.join('import '+name+'\n' for name in modules)))
        result = self.source
        boundary = len(result)
        for start, end, value in sorted(patches, reverse=True):
            if end > boundary:
                raise ValueError(tr('These changes affect the same section of code. Please apply them separately.'))
            result = result[:start] + value + result[end:]
            boundary = start
        parse_tree(result)
        if self.header in selected and self.card.get('class_kind') == 'abstract':
            identity = '.'.join((*self.identity.split('.')[:-1],generated_header(self.card)['name']))
            incoming = parse_linked_class(result,self.path,identity)
            if incoming.get('class_kind') != 'abstract':
                raise ValueError(tr('Please also select an abstract method change. ABC alone does not prevent instantiation.'))
        if self.header not in selected and not self.node.bases and not self.node.keywords:
            if any(change.section == 'methods' and '@abc.abstractmethod' in (change.after or change.addition) for change in selected):
                raise ValueError(tr('Please also select the class definition to activate abstract methods.'))
        return result, sorted(patches, reverse=True)

    def updated_source(self, result, selected):
        identity = self.identity
        if self.header in selected:
            declaration = ast.parse(self.header.after + "\n    pass").body[0]
            identity = ".".join((*identity.split(".")[:-1], declaration.name))
        incoming = parse_linked_class(result, self.path, identity)
        previous = self.card["source"]
        source = {**previous, "class": identity, "baseline": {
            section: list(rows) for section, rows in previous["baseline"].items()
        }}
        if self.header in selected:
            source["header"] = incoming["header"]
            if incoming.get('class_kind','class') == 'class':
                source.pop('class_kind',None)
            else:
                source['class_kind'] = incoming['class_kind']
        if incoming.get('class_kind','class') == 'class':
            source.pop('class_kind',None)
        else:
            source['class_kind'] = incoming['class_kind']
        for change in selected:
            if not change.section:
                continue
            rows = source["baseline"][change.section]
            old = next((row for row in rows if row["id"] == change.row_id or row["name"] == change.old_name), None)
            if old is not None:
                rows.remove(old)
            if change.new_name:
                kind = SECTIONS[change.section]
                row = next(row for row in incoming[change.section] if row[kind]["name"] == change.new_name)
                rows.append({"id": change.row_id, "name": change.new_name, "digest": _fingerprint(row)})
        return source
