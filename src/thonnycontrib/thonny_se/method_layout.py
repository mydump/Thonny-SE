# SPDX-FileCopyrightText: 2026 Sebastian Ladhoff
# SPDX-License-Identifier: GPL-3.0-only
"""Wrap displayed signatures only at top-level parameter boundaries."""
from functools import lru_cache
import io
import tokenize


@lru_cache(maxsize=256)
def method_parts(name, signature):
    try:
        offsets, position = [], 0
        for line in signature.splitlines(keepends=True):
            offsets.append(position)
            position += len(line)
        def index(point):
            return offsets[point[0]-1]+point[1]
        depth, start, parts = 0, None, []
        for token in tokenize.generate_tokens(io.StringIO(signature).readline):
            if token.type != tokenize.OP:
                continue
            if token.string in '([{':
                depth += 1
                if start is None:
                    if token.string != '(': break
                    start = index(token.end)
            elif token.string in ')]}':
                depth -= 1
                if depth == 0 and start is not None:
                    last = signature[start:index(token.start)].strip()
                    if last: parts.append(last)
                    return name+'(', tuple(parts), signature[index(token.start):]
            elif token.string == ',' and depth == 1:
                parts.append(signature[start:index(token.start)].strip())
                start = index(token.end)
    except (tokenize.TokenError, IndentationError, IndexError):
        pass
    return name+signature, (), ''


def minimum_method_width(name, signature, measure):
    prefix, parameters, tail = method_parts(name, signature)
    if not parameters:
        return measure(prefix+tail)
    units = [parameter+(',' if i<len(parameters)-1 else tail) for i,parameter in enumerate(parameters)]
    return max(measure(prefix), *(measure('    '+unit) for unit in units))


def wrap_method(name, signature, measure, width):
    prefix, parameters, tail = method_parts(name, signature)
    if not parameters:
        return prefix+tail
    lines, line = [], prefix
    for index, parameter in enumerate(parameters):
        unit = parameter+(',' if index<len(parameters)-1 else tail)
        space = ' ' if index and line.strip() else ''
        if measure(line+space+unit) > width:
            lines.append(line.rstrip())
            line = '    '+unit
        else:
            line += space+unit
    lines.append(line)
    return '\n'.join(lines)
