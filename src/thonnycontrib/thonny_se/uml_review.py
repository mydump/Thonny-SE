# SPDX-FileCopyrightText: 2026 Sebastian Ladhoff
# SPDX-License-Identifier: GPL-3.0-only
# See LICENSE in the project root for the full license text.

"""Presentation data for the same two-card review in either update direction."""
from dataclasses import dataclass

from .i18n import tr
from .uml_batch import TO_CODE
from .uml_codegen import attribute_code, method_code
from .uml_methods import member_text, is_constructor, constructor_parameters
from .uml_python_semantics import generated_header
from .uml_source import _fingerprint


@dataclass
class ReviewRow:
    """The target is before; the corresponding source is after, including in full view."""
    key: object
    section: str
    before: str
    after: str
    kind: str = 'same'
    selected: bool = False
    selectable: bool = False
    conflict: bool = False
    note: str = ''

    @property
    def status(self):
        if self.conflict:
            return 'conflict'
        return 'blocked' if self.kind != 'same' and not self.selectable and self.key is not None else self.kind


def header_text(card):
    header = card.get('header', {'name':card['name'],'bases':''})
    lines = []
    kind = card.get('class_kind','class')
    if kind != 'class':
        lines.append('«'+kind+'»')
    lines.append(header['name'])
    if header.get('bases'):
        lines.append(tr('Base classes: {bases}').format(bases=header['bases']))
    return '\n'.join(lines)


def _name(row, section):
    try:
        return (attribute_code if section == 'attributes' else method_code)(row)[0]
    except (ValueError,SyntaxError):
        return row.get('attribute',row.get('method',{})).get('name',row.get('text',''))


def _hidden(row, section, changed=False):
    return section == 'methods' and is_constructor(row) and not constructor_parameters(row) and not changed


def review_rows(entry, direction):
    if entry.action:
        from .uml_class_changes import class_review_rows
        header, rows = class_review_rows(entry, direction)
    else:
        header, rows = _code_rows(entry) if direction == TO_CODE else _diagram_rows(entry)
    for row in [header, *rows]:
        row.selected = row.selectable and not row.conflict
    return header, rows


def _code_rows(entry):
    plan,card = entry.plan,entry.card
    before = plan.incoming
    after = {**card, 'header':generated_header(card)}
    change = plan.header
    previous = card['source'].get('header')
    conflict = bool(change.after and before['header'] != previous and before['header'] != after['header'])
    note = change.note if not change.selectable or before['header']['name'] != after['header']['name'] else ''
    header = ReviewRow(change,'header',header_text(before),header_text(after),
                       'update' if change.after else 'same',change.selected,change.selectable,conflict,note)
    rows = []
    for section in ('attributes','methods'):
        incoming = {_name(row,section):row for row in before[section]}
        consumed = set()
        for row in card[section]:
            change = next((item for item in plan.changes if item.section == section and item.row_id == row['id']),None)
            name = _name(row,section)
            previous = next((item for item in card['source']['baseline'][section] if item['id']==row['id']),None)
            original_name = change.old_name if change and change.old_name else previous['name'] if previous else name
            original = incoming.get(original_name)
            if original is not None:
                consumed.add(original_name)
            if change is None:
                # A rejected declaration has no patch, but its reason must remain visible.
                change = next((item for item in plan.changes if item.group != 'same' and not item.section
                               and item.before == member_text(row,card['name'])),None)
            changed = change is not None and change.group != 'same'
            if _hidden(row,section,changed):
                continue
            left = member_text(original,before['name']) if original is not None else ''
            right = member_text(row,card['name'])
            if not changed:
                rows.append(ReviewRow(None,section,left,right))
                continue
            conflict = ((original is not None and (previous is None or previous['digest'] != _fingerprint(original)))
                        or (change.group == 'add' and not change.selected and bool(change.note)))
            note = tr('Both versions were edited. Check this change before applying it.') if conflict else change.note
            rows.append(ReviewRow(change,section,left,right,change.group,change.selected,change.selectable,conflict,note))
        for name,row in incoming.items():
            if name in consumed:
                continue
            change = next((item for item in plan.changes if item.section==section and item.old_name==name),None)
            if _hidden(row,section,change is not None):
                continue
            text = member_text(row,before['name'])
            rows.append(ReviewRow(change,section,text,'','delete' if change else 'same',
                                  change.selected if change else False,change.selectable if change else False,
                                  note=change.note if change else ''))
    return header,rows


def _diagram_rows(entry):
    card = entry.card
    if entry.header:
        before,after,conflict = entry.header
        current = {**card, 'header':before or card.get('header',{'name':card['name'],'bases':''})}
        proposal = {**card,'header':after,'class_kind':after.get('class_kind','class')}
        header = ReviewRow(('header',0),'header',header_text(current),header_text(proposal),'update',
                           not conflict and ({key:value for key,value in after.items() if key != 'class_kind'} != card['source'].get('header')
                           or after.get('class_kind','class') != card['source'].get('class_kind','class')),True,conflict)
    else:
        source_card = {**card,'header':entry.source.get('header',card.get('header',{'name':card['name'],'bases':''})),
                       'class_kind':entry.source.get('class_kind','class')}
        header = ReviewRow(None,'header',header_text(card),header_text(source_card))
    rows = []
    for section,entries in entry.plan.items():
        for index,(local,python,decision) in enumerate(entries):
            if decision == 'diagram':
                if (local or python) is not None and not _hidden(local or python,section):
                    before = member_text(local,card['name']) if local is not None else ''
                    after = member_text(python,card['name']) if python is not None else ''
                    note = tr('Only the target was changed. There is no source change to apply.') if before != after else ''
                    rows.append(ReviewRow(None,section,before,after,note=note))
                continue
            kind = 'delete' if python is None else 'add' if local is None else 'update'
            conflict = decision == 'conflict'
            rows.append(ReviewRow((section,index),section,
                member_text(local,card['name']) if local is not None else '',
                member_text(python,card['name']) if python is not None else '',kind,
                decision == 'python' and python is not None,True,conflict,
                tr('Both versions were edited. Check this change before applying it.') if conflict else
                tr('Only the target was changed. Select this entry to replace it with the source version.') if decision == 'target' else ''))
    return header,rows


def wrap_lines(text, measure, width, indent=16):
    """Wrap without ellipses, preferring syntax separators and hanging indents."""
    result = []
    for paragraph in text.split('\n'):
        remaining = paragraph
        continuation = False
        while remaining:
            inset = indent if continuation else 0
            limit = max(1,width-inset)
            if measure(remaining) <= limit:
                result.append((remaining,inset))
                break
            end = 1
            while end < len(remaining) and measure(remaining[:end+1]) <= limit:
                end += 1
            space = remaining.rfind(' ',0,end+1)
            if space > 0:
                end = space
            result.append((remaining[:end].rstrip(),inset))
            remaining = remaining[end:].lstrip()
            continuation = True
        if not paragraph:
            result.append(('',0))
    return result or [('',0)]
