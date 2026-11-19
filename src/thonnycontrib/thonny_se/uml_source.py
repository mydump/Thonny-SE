# SPDX-FileCopyrightText: 2026 Sebastian Ladhoff
# SPDX-License-Identifier: GPL-3.0-only
# See LICENSE in the project root for the full license text.

"""Source identity and member-level comparison for UML class cards."""
from collections import defaultdict, deque
from hashlib import sha256
import json
import os

from .uml_methods import display_member_name, is_constructor

SECTIONS = {"attributes": "attribute", "methods": "method"}


def _fingerprint(row):
    data = {key: value for key, value in row.items() if key not in ("id", "accessor") and not (key == "abstract" and value is False)}
    return sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


def _baseline(rows, kind):
    return [
        {"id": row["id"], "name": ("__init__" if kind == "method" and is_constructor(row) else row[kind]["name"]), "digest": _fingerprint(row)}
        for row in rows
    ]


def attach_source(card, path, qualified_name):
    card["source"] = {
        "path": os.path.abspath(path),
        "class": qualified_name,
        "baseline": {section: _baseline(card[section], kind) for section, kind in SECTIONS.items()},
    }
    if card.get("class_kind", "class") != "class":
        card["source"]["class_kind"] = card["class_kind"]
    if "header" in card:
        card["source"]["header"] = dict(card["header"])


def _member_key(data):
    if data.get("kind") == "constructor":
        return "public", "__init__"
    return data["visibility"], display_member_name(data["name"], data["visibility"])


def _aligned_rows(baseline, local, incoming, kind, *, first_link=False):
    by_name = defaultdict(deque)
    for entry in baseline:
        by_name[entry["name"] or "__init__" if kind == "method" else entry["name"]].append(entry["id"])
    tracked = {entry["id"] for entry in baseline}
    for row in local:
        if row["id"] not in tracked and kind in row:
            data = row[kind]
            by_name[_member_key(data) if first_link else data["name"]].append(row["id"])
    aligned = []
    for row in incoming:
        data = row[kind]
        matching = by_name[_member_key(data) if first_link else data["name"]]
        aligned.append({**row, "id": matching.popleft()} if matching else row)
    return aligned


def plan_update(card, incoming, *, first_link=False):
    """Return the new Python baseline and a plan in diagram row order."""
    source = dict(incoming["source"], baseline={})
    plan = {}
    for section, kind in SECTIONS.items():
        baseline = card["source"]["baseline"][section]
        remote = _aligned_rows(baseline, card[section], incoming[section], kind, first_link=first_link)
        source["baseline"][section] = _baseline(remote, kind)
        old = {entry["id"]: entry["digest"] for entry in baseline}
        local_by_id = {row["id"]: row for row in card[section]}
        remote_by_id = {row["id"]: row for row in remote}
        plan[section] = []
        for row_id in dict.fromkeys((*local_by_id, *remote_by_id)):
            local = local_by_id.get(row_id)
            python = remote_by_id.get(row_id)
            previous = old.get(row_id)
            local_digest = _fingerprint(local) if local is not None else None
            python_digest = _fingerprint(python) if python is not None else None
            if first_link and local is not None and python is not None and kind in local:
                local_data, python_data = local[kind], python[kind]
                if {**local_data, "name": _member_key(local_data)} == {**python_data, "name": _member_key(python_data)}:
                    plan[section].append((local, python, "diagram"))
                    continue
            if python_digest == local_digest:
                plan[section].append((local, python, "diagram"))
            elif python_digest == previous:
                plan[section].append((local, python, "target"))
            elif local_digest == previous:
                plan[section].append((local, python, "python"))
            else:
                plan[section].append((local, python, "conflict"))
    return source, plan


def resolve_update(card, source, plan, selected):
    previous_source = card["source"]
    resolved_source = {**source, "baseline": {}}
    result = {**card, "source": resolved_source}
    if ("header", 0) in selected:
        if card["name"] == card.get("header", {}).get("name"):
            result["name"] = source["header"]["name"]
        result["header"] = source["header"]
        if source.get('class_kind','class') == 'class':
            result.pop('class_kind',None)
        else:
            result['class_kind'] = source['class_kind']
    elif source.get("header") not in (card.get("header"), previous_source.get("header")):
        if "header" in previous_source:
            resolved_source["header"] = previous_source["header"]
        else:
            resolved_source.pop("header", None)
    if ('header',0) not in selected:
        if 'class_kind' in previous_source:
            resolved_source['class_kind'] = previous_source['class_kind']
        else:
            resolved_source.pop('class_kind',None)
    for section, rows in plan.items():
        result[section] = []
        previous = {entry["id"]: entry for entry in previous_source["baseline"][section]}
        incoming = {entry["id"]: entry for entry in source["baseline"][section]}
        for index, (local, python, decision) in enumerate(rows):
            accepted = decision != "diagram" and (section, index) in selected
            row = python if accepted else local
            if row is not None:
                result[section].append(row)
            if decision != "diagram" and not accepted:
                row_id = (local or python)["id"]
                if row_id in previous:
                    incoming[row_id] = previous[row_id]
                else:
                    incoming.pop(row_id, None)
        resolved_source["baseline"][section] = list(incoming.values())
    attributes = {row["id"] for row in result["attributes"] if "attribute" in row}
    result["methods"] = [
        {key: value for key, value in row.items() if key != "accessor"}
        if "accessor" in row and row["accessor"]["attribute"] not in attributes else row
        for row in result["methods"]
    ]
    return result
