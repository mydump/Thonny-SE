# SPDX-FileCopyrightText: 2026 Sebastian Ladhoff
# SPDX-License-Identifier: GPL-3.0-only
# See LICENSE in the project root for the full license text.

"""Keep UML methods generated for an attribute tied to its stable row ID."""
from .i18n import tr
from uuid import uuid4

from .uml_methods import attribute_draft, display_member_name, draft_from_row, python_visibility, accessor_name, accessor_names


def manual_accessor_kinds(card, attribute_id):
    attribute = next((row for row in card['attributes'] if row['id'] == attribute_id), None)
    if attribute is None:
        return set()
    data = attribute_draft(attribute)
    name = display_member_name(data['name'], data['visibility'])
    present = {draft_from_row(row)[0]['name'] for row in card['methods'] if 'accessor' not in row}
    return {kind for kind in ('get','set') if accessor_names(kind, name) & present}


def accessor_kinds(card, attribute_id):
    return manual_accessor_kinds(card, attribute_id) | {
        row["accessor"]["kind"] for row in card["methods"]
        if "accessor" in row and row["accessor"]["attribute"] == attribute_id
    }


def set_accessors(card, attribute, kinds):
    attribute_id = attribute["id"]
    if not kinds:
        card["methods"] = [
            row for row in card["methods"] if row.get("accessor", {}).get("attribute") != attribute_id
        ]
        return
    existing = {
        row["accessor"]["kind"]: row for row in card["methods"]
        if "accessor" in row and row["accessor"]["attribute"] == attribute_id
    }
    data = attribute["attribute"]
    name = display_member_name(data["name"], python_visibility(data["name"]))
    generated = {}
    occupied = set()
    for row in card["methods"]:
        if row.get("accessor", {}).get("attribute") == attribute_id:
            continue
        method, _ = draft_from_row(row)
        if method["visibility"] == "public":
            occupied.add(method["name"])
    for row in card["attributes"]:
        item = attribute_draft(row)
        if item["visibility"] == "public":
            occupied.add(item["name"])
    for kind in ("get", "set"):
        if kind not in kinds:
            continue
        previous = existing.get(kind)
        # Keep the convention of existing managed methods, including after edits.
        style = ('snake_case' if previous['method']['name'].startswith(kind+'_') else 'camelCase') if previous else None
        method_name = accessor_name(kind, name, style)
        if kind in manual_accessor_kinds(card, attribute_id):
            continue
        if method_name in occupied:
            if kind in manual_accessor_kinds(card, attribute_id):
                continue
            raise ValueError(tr('{p0} already exists. Please choose a different attribute name.').format(p0=method_name))
        getter = kind == "get"
        generated[kind] = {
            "id": existing[kind]["id"] if kind in existing else uuid4().hex,
            "method": {
                "name": method_name, "visibility": "public", "kind": "function" if getter else "procedure",
                "return_type": (data["type"] or "object") if getter else "",
                "parameters": [] if getter else [{"name": "wert", "type": data["type"], "default": ""}],
            },
            "accessor": {"attribute": attribute_id, "kind": kind},
        }

    methods = []
    for row in card["methods"]:
        accessor = row.get("accessor", {})
        if accessor.get("attribute") != attribute_id:
            methods.append(row)
        elif accessor["kind"] in generated:
            methods.append(generated.pop(accessor["kind"]))
    card["methods"] = methods + list(generated.values())
