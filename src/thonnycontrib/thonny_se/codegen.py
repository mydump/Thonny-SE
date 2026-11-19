# SPDX-FileCopyrightText: 2026 Sebastian Ladhoff
# SPDX-License-Identifier: GPL-3.0-only
# See LICENSE in the project root for the full license text.

"""Explicit Python export; preserve non-Python instructions as comments, never execute."""
from .i18n import tr
import ast
import copy
import re
import textwrap

from .model import body_at, selected_nodes, validate, active_body, selection_enabled
from .python_targets import parse_iteration_target


def generate_python(document, selection=None):
    validate(document)
    body = document['body'] if selection is None else (
        body_at(document, selection.path) if selection.index is None else selected_nodes(document, selection))
    body = active_body(body) if selection is None or selection_enabled(document, selection) else []
    used = set(re.findall(r'\b\w+\b', repr(document)))

    def fresh(stem):
        index = 1
        while f'_tse_{stem}_{index}' in used:
            index += 1
        name = f'_tse_{stem}_{index}'
        used.add(name)
        return name

    def expression(text, label, fallback='False'):
        try:
            return ast.parse(text.strip() or fallback, mode='eval').body
        except SyntaxError as exc:
            raise ValueError(tr('{p0}: {p1} (line {p2}).').format(p0=label, p1=exc.msg, p2=exc.lineno)) from exc

    def variable(text, label):
        value = text.strip()
        node = expression(value, label, fresh('element'))
        if not isinstance(node, ast.Name):
            raise ValueError(tr('{label}: Please use a single Python variable name.').format(label=label))
        node.ctx = ast.Store()
        return node

    def name(value, store=False):
        return ast.Name(id=value, ctx=ast.Store() if store else ast.Load())

    def call(function, args):
        return ast.Call(func=name(function), args=args, keywords=[])

    raw_blocks = {}
    node_tokens = {}

    def raw_instruction(node):
        key = id(node)
        if key not in node_tokens:
            token = fresh('block')
            text = textwrap.dedent(node['text']).strip()
            try:
                parsed = ast.parse(text or 'pass')
                python = ast.unparse(parsed)
                commented = not parsed.body
            except SyntaxError:
                python, commented = '', True
            raw_blocks[token] = dict(text=text, python=python, commented=commented)
            node_tokens[key] = token
        return node_tokens[key]

    def statements(nodes):
        result = []
        executable = False
        for node in nodes:
            kind = node['kind']
            if kind not in ('statement','call'):executable = True
            if kind in ('statement', 'call'):
                token = raw_instruction(node)
                result.append(ast.Expr(value=call(token, [])))
                executable |= not raw_blocks[token]['commented']
            elif kind in ('if', 'if_single'):
                result.append(ast.If(test=expression(node['text'], tr('Condition')), body=statements(node['then']),
                                     orelse=statements(node['else']) if kind == 'if' else []))
            elif kind == 'try':
                handlers=[]
                for handler in node['handlers']:
                    clause=handler['type']+(' as '+handler['name'] if handler['name'] else '')
                    keyword='except*' if node.get('starred',False) else 'except'
                    try:
                        parsed=ast.parse('try:\n    pass\n'+keyword+(' '+clause if clause else '')+':\n    pass').body[0].handlers[0]
                    except SyntaxError as exc:
                        raise ValueError(tr('Exception clause: {message}').format(message=exc.msg)) from exc
                    parsed.body=statements(handler['body'])
                    handlers.append(parsed)
                kind_type=getattr(ast,'TryStar',None) if node.get('starred',False) else ast.Try
                if kind_type is None:raise ValueError(tr('Exception groups require Python 3.11 or newer.'))
                result.append(kind_type(body=statements(node['body']),handlers=handlers,
                    orelse=statements(node['else']) if node['else'] is not None else [],
                    finalbody=statements(node['finally']) if node['finally'] is not None else []))
            elif kind == 'while':
                result.append(ast.While(test=expression(node['text'], tr('Loop condition')), body=statements(node['body']), orelse=[]))
            elif kind == 'switch':
                selector = fresh('auswahl')
                result.append(ast.Assign(targets=[name(selector, True)], value=expression(node['text'], tr('Selection expression'), 'None')))
                tail = statements(node['default'])
                for case in reversed(node['cases']):
                    test = ast.Compare(left=name(selector), ops=[ast.Eq()], comparators=[expression(case['value'], tr('Case value'), 'None')])
                    tail = [ast.If(test=test, body=statements(case['body']), orelse=tail)]
                result.extend(tail)
            else:
                if kind == 'repeat':
                    target = name(fresh('wiederholung'), True)
                    iterator = call('range', [expression(node['count'], tr('Count'), '0')])
                elif kind == 'foreach':
                    try:
                        target = parse_iteration_target(node['element'].strip() or fresh('element'))
                    except (SyntaxError, ValueError) as exc:
                        raise ValueError(tr('Element variable: Please use variable names or tuple/list unpacking.')) from exc
                    iterator = expression(node['collection'], tr('Collection'), '()')
                else:
                    target = variable(node['variable'], tr('Counter variable'))
                    start = expression(node['start'], tr('Initial value'), '0')
                    end = expression(node['end'], tr('Final value'), '-1' if node['direction']=='up' else '1')
                    step = expression(node['step'], tr('Step'), '1')
                    if isinstance(step, ast.Constant) and step.value == 0:
                        raise ValueError(tr('The step must not be zero.'))
                    down = node['direction'] == 'down'
                    stop = ast.BinOp(left=end, op=ast.Sub() if down else ast.Add(), right=ast.Constant(1))
                    stride = call('abs', [step])
                    if down:
                        stride = ast.UnaryOp(op=ast.USub(), operand=stride)
                    iterator = call('range', [start, stop, stride])
                result.append(ast.For(target=target, iter=iterator, body=statements(node['body']), orelse=[]))
        if not executable:result.append(ast.Pass())
        return result

    # Markers retain each instruction's identity after formatting the control tree.
    # A final compile can also detect context errors (e.g. break outside a loop).
    # Such an instruction becomes a comment; valid break inside a loop stays code.
    nodes = copy.deepcopy(body)
    while True:
        module = ast.fix_missing_locations(ast.Module(body=statements(nodes), type_ignores=[]))
        lines = [tr('# Generated from a structogram with Thonny SE.\n').rstrip('\n')]
        owners = {}
        for line in ast.unparse(module).splitlines():
            token = line.strip()[:-2] if line.strip().endswith('()') else ''
            block = raw_blocks.get(token)
            if block is None:
                lines.append(line)
                continue
            indent = line[:len(line)-len(line.lstrip())]
            if block['commented']:
                values = [(part if part.lstrip().startswith('#') else '# '+part)
                          for part in block['text'].splitlines()] or ['#']
            else:
                values = block['python'].splitlines()
            for part in values:
                lines.append(indent+part)
                owners[len(lines)] = token
        content = '\n'.join(lines)+'\n'
        try:
            compile(content, '<Thonny-SE-Export>', 'exec')
        except SyntaxError as exc:
            token = owners.get(exc.lineno)
            if token is not None and not raw_blocks[token]['commented']:
                raw_blocks[token]['commented'] = True
                continue
            raise ValueError(tr('Python code: {p0} (line {p1}).').format(p0=exc.msg, p1=exc.lineno)) from exc
        return content
