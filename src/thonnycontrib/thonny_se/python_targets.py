# SPDX-FileCopyrightText: 2026 Sebastian Ladhoff
# SPDX-License-Identifier: GPL-3.0-only
# See LICENSE in the project root for the full license text.

"""Python loop targets representable in a foreach block without side effects."""
import ast


def is_iteration_target(node):
    if isinstance(node, ast.Name):
        return True
    if isinstance(node, (ast.Tuple, ast.List)):
        return all(is_iteration_target(item.value if isinstance(item, ast.Starred) else item)
                   for item in node.elts)
    return False


def parse_iteration_target(text):
    target = ast.parse(f'({text})', mode='eval').body
    if not is_iteration_target(target):
        raise ValueError('Unsupported iteration target')
    for node in ast.walk(target):
        if isinstance(node, (ast.Name, ast.Tuple, ast.List, ast.Starred)):
            node.ctx = ast.Store()
    loop = ast.For(target=target, iter=ast.Tuple(elts=[], ctx=ast.Load()),
                   body=[ast.Pass()], orelse=[])
    module = ast.fix_missing_locations(ast.Module(body=[loop], type_ignores=[]))
    compile(module, '<Thonny-SE-Loop>', 'exec')
    return target
