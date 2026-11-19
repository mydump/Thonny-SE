# SPDX-FileCopyrightText: 2026 Sebastian Ladhoff
# SPDX-License-Identifier: GPL-3.0-only
# See LICENSE in the project root for the full license text.

"""Eigenständiges UML-Klassenmodell; keine automatische Codekopplung."""
from .i18n import tr
from .uml_methods import validate_method, validate_attribute, member_text
from .uml_source import SECTIONS
from .uml_relationships import DIRECTIONS, END_FIELDS, RELATIONSHIP_KINDS, multiplicity, role_name
import math
from uuid import uuid4


VERSION = 13
COMMENT_MIN_SIZE = (100, 56)
COMMENT_MAX_SIZE = 1600
CLASS_KINDS = {"class": "Class", "abstract": "Abstract class", "interface": "Interface"}


def new_document():
    return {"format": "thonny-se-uml", "version": VERSION, "classes": [], "relationships": [], "comments": []}


def initial_upper(text):
    return text[:1].upper() + text[1:]


def class_name(text):
    text = initial_upper(text.strip())
    if not text or len(text) > 200 or "\n" in text or "\r" in text:
        raise ValueError(tr('Please enter a class name of 1 to 200 characters.'))
    return text


def new_class(name, x, y):
    return {"id": uuid4().hex, "name": class_name(name), "x": x, "y": y,
            "attributes": [], "methods": []}


def new_member(text):
    return {"id": uuid4().hex, "text": text.strip()}


def validate(document):
    def require(condition):
        if not condition:
            raise ValueError(tr('Invalid UML model.'))
    require(isinstance(document, dict) and set(document) - {"removed_classes"} == {"format", "version", "classes", "relationships", "comments"})
    require(document["format"] == "thonny-se-uml" and type(document["version"]) is int and document["version"] == VERSION)
    classes = document["classes"]
    require(isinstance(classes, list) and len(classes) <= 200)
    ids, names, count = set(), set(), 0
    parameter_count = 0
    for card in classes:
        require(isinstance(card, dict) and set(card) - {"source", "header", "class_kind"} == {"id", "name", "x", "y", "attributes", "methods"})
        kind = card.get("class_kind", "class")
        require(isinstance(kind, str) and kind in CLASS_KINDS)
        if "header" in card:
            _validate_header(card["header"], require)
        if "source" in card:
            _validate_source(card["source"], require)
        require(isinstance(card["id"], str) and 0 < len(card["id"]) <= 100 and card["id"] not in ids)
        ids.add(card["id"])
        name = card["name"]
        require(isinstance(name, str) and class_name(name) == name and name not in names)
        names.add(name)
        for key in ("x", "y"):
            value = card[key]
            require(type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 1_000_000)
        for section in ("attributes", "methods"):
            require(isinstance(card[section], list))
            count += len(card[section])
            require(count <= 1000)
            for row in card[section]:
                require(isinstance(row, dict))
                keys = set(row) - ({"abstract"} if section == "methods" else set()) - ({"accessor"} if section == "methods" and "method" in row else set())
                require((keys == {"id", "text"} or (section == "methods" and keys == {"id", "method"}) or (section == "attributes" and set(row) == {"id", "attribute"})))
                require(isinstance(row["id"], str) and 0 < len(row["id"]) <= 100 and row["id"] not in ids)
                ids.add(row["id"])
                if "attribute" in row:
                    validate_attribute(row["attribute"])
                    continue
                if "abstract" in row:
                    require(section == "methods" and type(row["abstract"]) is bool)
                if "method" in row:
                    validate_method(row["method"])
                    parameter_count += len(row["method"]["parameters"])
                    require(parameter_count <= 5000)
                    continue
                require(isinstance(row["text"], str) and 0 < len(row["text"]) <= 500 and row["text"] == row["text"].strip() and "\n" not in row["text"] and "\r" not in row["text"])
        constructors = [r for r in card["methods"] if "method" in r and r["method"]["kind"] == "constructor"]
        require(len(constructors) <= 1)
        attributes = {row["id"] for row in card["attributes"] if "attribute" in row}
        accessors = set()
        for row in card["methods"]:
            if "accessor" not in row:
                continue
            value = row["accessor"]
            require(isinstance(value, dict) and set(value) == {"attribute", "kind"})
            attribute_id, kind = value["attribute"], value["kind"]
            require(isinstance(attribute_id, str) and attribute_id in attributes and kind in ("get", "set"))
            require(row["method"]["kind"] == ("function" if kind == "get" else "procedure"))
            require((attribute_id, kind) not in accessors)
            accessors.add((attribute_id, kind))
    relationships = document["relationships"]
    require(isinstance(relationships, list) and len(relationships) <= 1000)
    class_ids = {card["id"] for card in classes}
    for relation in relationships:
        require(isinstance(relation, dict) and set(relation) - {"bend"} == {
            "id", "start", "end", "kind", "direction", "label", *END_FIELDS
        })
        bend = relation.get("bend", 0)
        require(type(bend) in (int, float) and math.isfinite(bend) and abs(bend) <= 1_000_000)
        relation_id = relation["id"]
        require(isinstance(relation_id, str) and 0 < len(relation_id) <= 100 and relation_id not in ids)
        ids.add(relation_id)
        start, end = relation["start"], relation["end"]
        require(isinstance(start, str) and isinstance(end, str) and {start, end} <= class_ids)
        kind = relation["kind"]
        require(isinstance(kind, str) and kind in RELATIONSHIP_KINDS)
        require(start != end or kind not in ("inheritance", "realization"))
        label = relation["label"]
        require(isinstance(label, str) and label == role_name(label))
        direction = relation["direction"]
        require(direction in DIRECTIONS and (kind == "association" or not direction))
        for key in END_FIELDS:
            value = relation[key]
            require(isinstance(value, str))
            if key.endswith("_role"):
                require(value == role_name(value))
            else:
                require(len(value) <= 18 and value == multiplicity(value))
            require(kind not in ("inheritance", "realization") or not value)
    comments = document["comments"]
    require(isinstance(comments, list) and len(comments) <= 200)
    for note in comments:
        required = {"id", "text", "x", "y", "target"}
        require(isinstance(note, dict) and set(note) in (required, required | {"width", "height"}))
        if "width" in note:
            for key, minimum in zip(("width", "height"), COMMENT_MIN_SIZE):
                size = note[key]
                require(type(size) in (float, int) and minimum <= size <= COMMENT_MAX_SIZE)
        cid, text, target = note["id"], note["text"], note["target"]
        require(isinstance(cid, str) and 0 < len(cid) <= 100 and cid not in ids)
        ids.add(cid)
        require(isinstance(text, str) and 0 < len(text) <= 1000 and text == text.strip() and "\0" not in text)
        require(target is None or (isinstance(target, str) and target in class_ids))
        for key in ("x", "y"):
            value = note[key]
            require(type(value) in (float, int) and 0 <= value <= 1_000_000)
    removed = document.get("removed_classes", [])
    require(isinstance(removed, list) and len(removed) <= 200)
    removed_ids = set()
    for card in removed:
        require(isinstance(card, dict) and "source" in card)
        validate({**new_document(), "classes": [card]})
        require(card["id"] not in class_ids and card["id"] not in removed_ids)
        removed_ids.add(card["id"])
    return document



def _validate_source(source, require):
    require(isinstance(source, dict) and set(source) - {"header", "class_kind"} == {"path", "class", "baseline"})
    if "class_kind" in source:
        require(isinstance(source["class_kind"], str) and source["class_kind"] in CLASS_KINDS)
    if "header" in source:
        _validate_header(source["header"], require)
    path, name, baseline = source["path"], source["class"], source["baseline"]
    require(isinstance(path, str) and 0 < len(path) <= 8192 and "\0" not in path)
    require(isinstance(name, str) and 0 < len(name) <= 1000 and all(part.isidentifier() for part in name.split(".")))
    require(isinstance(baseline, dict) and set(baseline) == set(SECTIONS))
    ids = set()
    for rows in baseline.values():
        require(isinstance(rows, list) and len(rows) <= 1000)
        for entry in rows:
            require(isinstance(entry, dict) and set(entry) == {"id", "name", "digest"})
            row_id, row_name, digest = entry["id"], entry["name"], entry["digest"]
            require(isinstance(row_id, str) and 0 < len(row_id) <= 100 and row_id not in ids)
            require(isinstance(row_name, str) and len(row_name) <= 500 and row_name.isidentifier())
            require(isinstance(digest, str) and len(digest) == 64 and all(c in "0123456789abcdef" for c in digest))
            ids.add(row_id)


def _validate_header(header, require):
    require(isinstance(header, dict) and set(header) == {"name", "bases"})
    require(isinstance(header["name"], str) and len(header["name"]) <= 200 and header["name"].isidentifier())
    require(isinstance(header["bases"], str) and len(header["bases"]) <= 4000 and "\0" not in header["bases"])
