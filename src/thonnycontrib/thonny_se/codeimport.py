# SPDX-FileCopyrightText: 2026 Sebastian Ladhoff
# SPDX-License-Identifier: GPL-3.0-only
# See LICENSE in the project root for the full license text.

"""Python strukturell lesen, ohne Code auszuführen oder Inhalte zu verwerfen."""
from .i18n import tr
import ast
import io
import tokenize

from .model import new_document, new_node, validate
from .python_targets import is_iteration_target


def parse_python(source, *, selection=False, strict=False):
    try:
        try:
            tree = ast.parse(source)
        except IndentationError:
            if not selection:
                raise
            # Parse an indented selection without altering multiline literals.
            tree = ast.parse("if True:\n" + source)
            if len(tree.body) != 1:
                raise ValueError(tr('Please select a contiguous block of statements.'))
            tree.body = tree.body[0].body
            ast.increment_lineno(tree, -1)
        try:
            compile(tree, "<Thonny-SE-Import>", "exec")
        except SyntaxError:
            if not selection:
                raise
            # A selection can be a function body containing return/yield.
            # Validate in that context without adding a function to the diagram
            # or changing source indentation (notably multiline literals).
            wrapper = ast.FunctionDef(
                name="_thonny_se_selection",
                args=ast.arguments(posonlyargs=[], args=[], kwonlyargs=[],
                                   kw_defaults=[], defaults=[]),
                body=tree.body, decorator_list=[],
                lineno=1, col_offset=0,
                end_lineno=max((node.end_lineno for node in tree.body), default=1),
                end_col_offset=0,
            )
            module = ast.fix_missing_locations(ast.Module(body=[wrapper], type_ignores=[]))
            compile(module, "<Thonny-SE-Import>", "exec")
    except SyntaxError as exc:
        raise ValueError(tr('Python syntax error on line {p0}: {p1}').format(p0=exc.lineno, p1=exc.msg)) from exc
    warnings = []

    def text(node):
        return ast.unparse(node)

    def opaque(node):
        kind = 'call' if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call) else 'statement'
        result = new_node(kind)
        result['text'] = text(node)
        return result

    unsupported_labels = {
        ast.ClassDef: tr('Class definition'),
        ast.FunctionDef: tr('Function definition'),
        ast.AsyncFunctionDef: tr('Async function definition'),
        ast.For: tr('For loop with this target variable or an else branch'),
        ast.While: tr('While loop with an else branch'),
        ast.Try: tr('Exception handling with try'),
        ast.With: tr('With block'),
        ast.AsyncWith: tr('Async with block'),
        ast.AsyncFor: tr('Async for loop'),
    }

    def unsupported(node, description):
        if strict:
            raise ValueError(tr('Line {p0}: {p1} cannot be represented as a structogram block.').format(p0=node.lineno, p1=description))
        warnings.append(tr('Line {p0}: {p1} is preserved in full as a code block.').format(p0=node.lineno, p1=description))
        return opaque(node)

    def convert(nodes):
        result = []
        for node in nodes:
            # pass ist ein syntaktischer Platzhalter, kein Arbeitsschritt.
            if isinstance(node, ast.Pass):
                continue
            if isinstance(node, ast.If):
                item = new_node('if' if node.orelse else 'if_single')
                item.update(text=text(node.test), then=convert(node.body))
                if node.orelse:
                    item['else'] = convert(node.orelse)
            elif isinstance(node, (ast.Try,)+( (ast.TryStar,) if hasattr(ast,'TryStar') else ())):
                item = dict(new_node('try'), body=convert(node.body),
                    handlers=[{'type':text(h.type) if h.type is not None else '',
                               'name':h.name or '', 'body':convert(h.body)} for h in node.handlers],
                    **{'else':convert(node.orelse) if node.orelse else None,
                       'finally':convert(node.finalbody) if node.finalbody else None})
                if hasattr(ast,'TryStar') and isinstance(node,ast.TryStar):item['starred']=True
            elif isinstance(node, ast.While) and not node.orelse:
                item = dict(new_node('while'), text=text(node.test), body=convert(node.body))
            elif isinstance(node, ast.For) and not node.orelse and is_iteration_target(node.target):
                item = dict(new_node('foreach'), element=text(node.target), collection=text(node.iter), body=convert(node.body))
                # range bleibt absichtlich ein Für-jedes: kein Erraten von
                # Schattennamen, dynamischen Vorzeichen oder inklusiven Grenzen.
            elif isinstance(node, getattr(ast, 'Match', ())):
                cases = []
                default = []
                supported = True
                for case in node.cases:
                    if case.guard is not None:
                        supported = False
                    if isinstance(case.pattern, ast.MatchValue):
                        cases.append({'value': text(case.pattern.value), 'body': convert(case.body)})
                    elif isinstance(case.pattern, ast.MatchSingleton):
                        # True/False/None-Patterns vergleichen Identität, nicht ==.
                        supported = False
                    elif isinstance(case.pattern, ast.MatchAs) and case.pattern.name is None and case.pattern.pattern is None:
                        default = convert(case.body)
                    else:
                        supported = False
                if supported and cases:
                    item = dict(new_node('switch'), text=text(node.subject), cases=cases, default=default)
                else:
                    item = unsupported(node, tr('Complex pattern matching'))
            elif strict and isinstance(node, ast.Expr) and isinstance(node.value, (ast.Constant, ast.Name)):
                # A standalone value or docstring is not an algorithm step.
                continue
            elif hasattr(node, "body"):
                item = unsupported(node, unsupported_labels.get(type(node), tr('This Python block')))
            else:
                item = opaque(node)
            result.append(item)
        return result

    document = new_document()
    document['body'] = convert(tree.body)
    if any(token.type == tokenize.COMMENT for token in tokenize.generate_tokens(io.StringIO(source).readline)):
        warnings.append(tr('Comments and original formatting are not preserved on import.'))
    validate(document)
    return document, list(dict.fromkeys(warnings))
