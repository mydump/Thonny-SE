# SPDX-FileCopyrightText: 2026 Sebastian Ladhoff
# SPDX-License-Identifier: GPL-3.0-only
# See LICENSE in the project root for the full license text.

"""UML relationship labels, geometry and inference from class cards."""
from .i18n import tr
from .diagram_preferences import relationship_count_label
import ast
from collections import defaultdict
import math
from pathlib import Path
import re
from uuid import uuid4


def multiplicity(text):
    text = text.strip()
    if not text or text in ("*", "n"):
        return text
    match = re.fullmatch(r"([0-9]{1,8})(?:\s*\.\.\s*([0-9]{1,8}|\*))?", text)
    if match:
        lower, upper = match.groups()
        if upper is None:
            return str(int(lower))
        if upper == "*" or int(lower) <= int(upper):
            return f"{int(lower)}..{upper if upper == '*' else int(upper)}"
    raise ValueError(tr('Please enter a value for {term}, such as 1, 0..1, 0..* or 1..*.').format(term=relationship_count_label()))


def card_edge_toward(bounds, point):
    """Intersect a ray from the card center toward a point with the card edge."""
    x, y = (bounds[0]+bounds[2])/2, (bounds[1]+bounds[3])/2
    dx, dy = point[0]-x, point[1]-y
    if not (dx or dy):
        return bounds[2], y
    factor = min((bounds[2]-bounds[0])/(2*abs(dx)) if dx else math.inf,
                 (bounds[3]-bounds[1])/(2*abs(dy)) if dy else math.inf)
    return x+dx*factor, y+dy*factor


def self_relationship_points(bounds, lane=0, bend=0):
    """A loop with distinct upper/lower ports, entirely outside its own card."""
    left, top, right, bottom = bounds
    lane = max(0, lane)
    inset = (bottom-top)/(4+2*lane)
    upper, lower = top+inset, bottom-inset
    outside = right+max(40, 88+36*lane+bend)
    return ((right, upper), (outside, upper), (outside, lower), (right, lower))


def association_points(start, end, lane=0):
    """Return direct endpoints, separating parallel relationships slightly."""
    if start == end:
        return self_relationship_points(start, lane)
    ax, ay = (start[0]+start[2])/2, (start[1]+start[3])/2
    bx, by = (end[0]+end[2])/2, (end[1]+end[3])/2

    # Shared attachment axes keep aligned rows/columns straight even when
    # card dimensions differ (notably when export omits editing controls).
    top, bottom = max(start[1], end[1]), min(start[3], end[3])
    left, right = max(start[0], end[0]), min(start[2], end[2])
    if top < bottom and (start[2] <= end[0] or end[2] <= start[0]):
        y = min(bottom-1, max(top+1, (top+bottom)/2 + lane*16))
        return ((start[2], y), (end[0], y)) if ax < bx else ((start[0], y), (end[2], y))
    if left < right and (start[3] <= end[1] or end[3] <= start[1]):
        x = min(right-1, max(left+1, (left+right)/2 + lane*16))
        return ((x, start[3]), (x, end[1])) if ay < by else ((x, start[1]), (x, end[3]))
    if lane:
        dx, dy = bx-ax, by-ay
        length = math.hypot(dx, dy)
        first = card_edge_toward(start, (bx, by))
        last = card_edge_toward(end, (ax, ay))
        mx, my = (first[0]+last[0])/2-dy/length*lane*32, (first[1]+last[1])/2+dx/length*lane*32
        return card_edge_toward(start, (mx, my)), (mx, my), card_edge_toward(end, (mx, my))
    return card_edge_toward(start, (bx, by)), card_edge_toward(end, (ax, ay))


def multiplicity_position(endpoint, next_point, width, *, side=1, clearance=0):
    x, y = endpoint
    dx, dy = next_point[0]-x, next_point[1]-y
    length = math.hypot(dx, dy)
    if not length:
        return x, y-13
    ux, uy = dx/length, dy/length
    offset = min(max(14, width/2+5), max(14, length*.55))
    offset += clearance
    return x+ux*offset+uy*12*side, y+uy*offset-ux*12*side


RELATIONSHIP_KINDS = {
    "association": 'Association',
    "aggregation": 'Aggregation',
    "composition": 'Composition',
    "inheritance": 'Inheritance',
    "realization": 'Realization',
}
BASE_RELATIONSHIPS = ("inheritance", "realization")
DIRECTIONS = ("", "end", "start", "both")
END_FIELDS = ("start_multiplicity", "end_multiplicity", "start_role", "end_role")


def new_relationship(start, end, kind="association", *, direction="", label="", **labels):
    return dict(id=uuid4().hex, start=start, end=end, kind=kind, direction=direction, label=label,
                **{field: labels.get(field, "") for field in END_FIELDS})


def role_name(text):
    text = text.strip()
    if len(text) > 100 or any(char in text for char in "\r\n\0"):
        raise ValueError(tr('Please enter a single line of at most 100 characters.'))
    return text


def association_arrow(endpoint, next_point, *, scale=1):
    x, y = endpoint
    dx, dy = next_point[0]-x, next_point[1]-y
    length = math.hypot(dx, dy)
    if not length:
        return ()
    ux, uy = dx/length, dy/length
    return (x+scale*(12*ux-6*uy), y+scale*(12*uy+6*ux), x, y,
            x+scale*(12*ux+6*uy), y+scale*(12*uy-6*ux))


def endpoint_symbol(kind, endpoint, next_point, *, scale=1):
    x, y = endpoint
    dx, dy = next_point[0]-x, next_point[1]-y
    length = math.hypot(dx, dy)
    if not length:
        return ()
    ux, uy = dx/length, dy/length
    points = ((0, 0), (15, -9), (15, 9)) if kind in BASE_RELATIONSHIPS else ((0, 0), (9, -6), (18, 0), (9, 6))
    return tuple(coordinate for along, across in points
                 for coordinate in (x+scale*(along*ux-across*uy), y+scale*(along*uy+across*ux)))


def _type_references(node, depth=0, aliases=None):
    """Return explicit attribute targets, never metadata or guessed ownership."""
    if depth > 32:
        return []
    aliases = aliases or {}
    def qualified(node):
        text = ast.unparse(node)
        head, dot, tail = text.partition('.')
        return aliases.get(head, head) + (dot+tail if dot else '')
    recurse = lambda child: _type_references(child, depth+1, aliases)
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return recurse(ast.parse(node.value, mode="eval").body)
    if isinstance(node, (ast.Name, ast.Attribute)):
        return [(qualified(node), "1")]
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        return [(name, "0..*" if count == "0..*" else "0..1")
                for child in (node.left, node.right) for name, count in recurse(child)]
    if not isinstance(node, ast.Subscript):
        return []
    qualifier, _, short = qualified(node.value).rpartition(".")
    if qualifier not in ("", "typing", "builtins", "collections.abc", "collections"):
        return [(qualified(node.value), "1")]
    inner = node.slice
    items = inner.elts if isinstance(inner, ast.Tuple) else [inner]
    if short == "Annotated":
        return recurse(items[0]) if items else []
    if short in ("Optional", "Union"):
        return [(name, "0..*" if count == "0..*" else "0..1")
                for item in items for name, count in recurse(item)]
    if short in ("dict", "Dict", "Mapping", "MutableMapping"):
        return [(name, "0..*") for name, _ in recurse(items[1])] if len(items) == 2 else []
    if short in ("tuple", "Tuple"):
        return [(name, "0..*") for item in items for name, _ in recurse(item)]
    if short in ("list", "List", "set", "Set", "frozenset", "FrozenSet",
                 "Sequence", "MutableSequence", "Iterable", "Collection", "Deque", "deque"):
        return [(name, "0..*") for name, _ in recurse(inner)]
    # A user-defined generic is a reference to that class, not its arguments.
    return [(qualified(node.value), "1")]


def class_references(cards):
    aliases = defaultdict(set)
    for card in cards:
        source = card.get("source", {})
        qualified = source.get("class", card["name"])
        names = {card["name"], qualified, qualified.rsplit(".", 1)[-1],
                 card.get("header", {}).get("name", card["name"])}
        if source:
            names.add(f"{Path(source['path']).stem}.{qualified}")
        for name in names:
            aliases[name].add(card["id"])

    return {name: next(iter(ids)) for name, ids in aliases.items() if len(ids) == 1}


def base_targets(header, references, cid, *, aliases=None):
    try:
        bases = ast.parse(f"class A({header}): pass").body[0].bases if header else ()
    except (SyntaxError, ValueError, RecursionError):
        return ()
    result = []
    for base in bases:
        base = base.value if isinstance(base, ast.Subscript) else base
        if isinstance(base, (ast.Name, ast.Attribute)):
            name = ast.unparse(base)
            head, dot, tail = name.partition(".")
            name = (aliases or {}).get(head, head) + (dot+tail if dot else "")
            target = references.get(name)
            if target and target != cid and target not in result:
                result.append(target)
    return tuple(result)


def base_relationship_kind(document, start, end):
    cards = {card['id']: card for card in document['classes']}
    if (cards[end].get('class_kind', 'class') == 'interface'
            and cards[start].get('class_kind', 'class') != 'interface'):
        return 'realization'
    return 'inheritance'


def updated_inheritance(document, cid, previous_bases, bases):
    """Reconcile changed class headers while preserving unrelated/manual links."""
    references = class_references(document['classes'])
    previous = set(base_targets(previous_bases, references, cid))
    targets = base_targets(bases, references, cid)
    relations = []
    existing = set()
    for relation in document['relationships']:
        if relation['kind'] in BASE_RELATIONSHIPS and relation['start'] == cid:
            end = relation['end']
            if end in previous and end not in targets:
                continue
            relation = dict(relation, kind=base_relationship_kind(document, cid, end))
            existing.add(end)
        relations.append(relation)
    relations.extend(new_relationship(cid, end, base_relationship_kind(document, cid, end)) for end in targets if end not in existing)
    return relations


def infer_relationships(document, read_source=None):
    """Add missing links between existing cards from explicit bases/attributes.

    Preserve all existing links and labels. An optional reader resolves declared
    import aliases from source text (including unsaved editor buffers); sources
    are never executed and missing diagram classes are never searched for.
    """
    from .uml_methods import attribute_draft, display_member_name

    cards = document["classes"]
    references = class_references(cards)
    by_id = {card["id"]: card for card in cards}
    bases_present = set()
    unlabelled_pairs = set()
    roles_present = set()
    for relation in document["relationships"]:
        start, end = relation["start"], relation["end"]
        if relation["kind"] in BASE_RELATIONSHIPS:
            bases_present.add((start, end))
        elif not relation["start_role"] and not relation["end_role"]:
            unlabelled_pairs.add(frozenset((start, end)))
        else:
            if relation["end_role"]:
                roles_present.add((start, end, relation["end_role"]))
            if relation["start_role"]:
                roles_present.add((end, start, relation["start_role"]))
    inferred = []
    type_cache = {}
    source_aliases = {}
    file_references = defaultdict(dict)
    for card in cards:
        source = card.get('source', {})
        if source.get('path'):
            file_references[source['path']][source.get('class', card['name'])] = card['id']
    for card in cards:
        start = card["id"]
        aliases = {}
        path = card.get('source', {}).get('path')
        if path and read_source is not None:
            if path not in source_aliases:
                from .uml_python_semantics import imported_names
                try:
                    source_aliases[path] = imported_names(ast.parse(read_source(path)))
                except (OSError, ValueError, SyntaxError, UnicodeError, RecursionError):
                    source_aliases[path] = {}
            aliases = source_aliases[path]
        local_references = {**references, **file_references[path]} if path else references
        alias_key = tuple(aliases.items())
        header = card.get("header", {}).get("bases", "")
        for end in base_targets(header, local_references, start, aliases=aliases):
            if (start, end) not in bases_present:
                kind = 'realization' if (by_id[end].get('class_kind') == 'interface'
                                        and card.get('class_kind') != 'interface') else 'inheritance'
                inferred.append(new_relationship(start, end, kind))
                bases_present.add((start, end))
        for row in card["attributes"]:
            data = attribute_draft(row)
            annotation = data["type"]
            cache_key = (annotation, alias_key)
            if cache_key not in type_cache:
                try:
                    node = ast.parse(annotation, mode="eval").body
                    type_cache[cache_key] = _type_references(node, aliases=aliases) if sum(1 for _ in ast.walk(node)) <= 2000 else []
                except (SyntaxError, ValueError, RecursionError):
                    type_cache[cache_key] = []
            try:
                role = role_name(display_member_name(data["name"], data["visibility"]))
            except ValueError:
                continue
            counts = {}
            for name, count in type_cache[cache_key]:
                counts[name] = "0..*" if "0..*" in (count, counts.get(name)) else count
            for name, count in counts.items():
                end = local_references.get(name)
                if end is None:
                    continue
                key = (start, end, role)
                if frozenset((start, end)) in unlabelled_pairs or key in roles_present:
                    continue
                inferred.append(new_relationship(start, end, end_role=role, end_multiplicity=count))
                roles_present.add(key)
    return inferred


def synchronized_inheritance(document, relationships=None):
    """Apply relationship edits and Python base changes as one model operation.

    Headers may also refer to external bases with no diagram card. Keep those,
    along with generic arguments, metaclasses and unrelated relationships.
    """
    import copy
    from .uml_codegen import class_header, header_data
    from .uml_model import validate

    candidate = copy.deepcopy(document)
    if relationships is not None:
        candidate['relationships'] = copy.deepcopy(relationships)
        for relation in candidate['relationships']:
            if (relation['kind'] == 'realization'
                    and base_relationship_kind(candidate, relation['start'], relation['end']) != 'realization'):
                raise ValueError(tr('A realization must lead from a class to an interface.'))
    validate(candidate)
    cards = {card['id']: card for card in candidate['classes']}
    references = class_references(candidate['classes'])
    previous = {(r['start'], r['end']) for r in document['relationships'] if r['kind'] in BASE_RELATIONSHIPS}
    current = {(r['start'], r['end']) for r in candidate['relationships'] if r['kind'] in BASE_RELATIONSHIPS}
    affected = {start for start, _ in previous | current}
    for cid in affected:
        card = cards[cid]
        header = dict(card.get('header', card.get('source', {}).get('header',
                            {'name': card['name'], 'bases': ''})))
        node = ast.parse(class_header(header)+'\n    pass').body[0]
        removed = {end for start, end in previous-current if start == cid}
        def target(base):
            expression = base.value if isinstance(base, ast.Subscript) else base
            return references.get(ast.unparse(expression))
        node.bases = [base for base in node.bases if target(base) not in removed]
        present = {target(base) for base in node.bases}
        for relation in candidate['relationships']:
            if relation['kind'] not in BASE_RELATIONSHIPS or relation['start'] != cid or relation['end'] in present:
                continue
            base = cards[relation['end']]
            name = base.get('header', {}).get('name', base.get('source', {}).get('class', base['name']))
            expression = ast.parse(name, mode='eval').body
            if references.get(ast.unparse(expression)) != base['id']:
                raise ValueError(tr('The Python name of base class {name!r} is ambiguous.').format(name=base['name']))
            node.bases.append(expression)
            present.add(base['id'])
        card['header'] = header_data(node)
    for cid, card in cards.items():
        bases = card.get('header',{}).get('bases','')
        node = ast.parse('class Placeholder('+bases+'):\n    pass').body[0] if bases else None
        if node is not None and any(references.get(ast.unparse(base.value if isinstance(base,ast.Subscript) else base)) == cid for base in node.bases):
            raise ValueError(tr('Inheritance cannot contain a cycle.'))
    # Reject cycles immediately, including those written into class headers.
    graph = {cid: base_targets(card.get('header', {}).get('bases', ''), references, cid)
             for cid, card in cards.items()}
    done, visiting = set(), set()
    def visit(cid):
        if cid in visiting:
            raise ValueError(tr('Inheritance cannot contain a cycle.'))
        if cid in done:
            return
        visiting.add(cid)
        for base in graph[cid]:
            visit(base)
        visiting.remove(cid)
        done.add(cid)
    for cid in graph:
        visit(cid)
    for relation in candidate['relationships']:
        if relation['kind'] in BASE_RELATIONSHIPS:
            relation['kind'] = base_relationship_kind(candidate, relation['start'], relation['end'])
    return validate(candidate)


def renamed_class(document, cid, name):
    """Rename local Python identities and their bases; linked source names stay explicit."""
    import copy
    from .uml_codegen import class_header, header_data
    from .uml_model import class_name
    candidate = copy.deepcopy(document)
    card = next(card for card in candidate['classes'] if card['id'] == cid)
    card['name'] = class_name(name)
    if not card['name'].isidentifier():
        return candidate
    references = class_references(document['classes'])
    if 'header' in card:
        card['header']['name'] = card['name']
    for child in candidate['classes']:
        header = child.get('header')
        if not header:
            continue
        node = ast.parse(class_header(header)+'\n    pass').body[0]
        changed = False
        for index,base in enumerate(node.bases):
            expression = base.value if isinstance(base,ast.Subscript) else base
            if references.get(ast.unparse(expression)) == cid:
                replacement = ast.Name(id=card['name'],ctx=ast.Load())
                if isinstance(base,ast.Subscript):
                    base.value = replacement
                else:
                    node.bases[index] = replacement
                changed = True
        if changed:
            child['header'] = header_data(node)
    return candidate
