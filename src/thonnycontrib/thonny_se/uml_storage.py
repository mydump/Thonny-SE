# SPDX-FileCopyrightText: 2026 Sebastian Ladhoff
# SPDX-License-Identifier: GPL-3.0-only
# See LICENSE in the project root for the full license text.

"""UML-Dateien verwenden denselben atomaren Speicherweg wie Struktogramme."""
from .i18n import tr
import copy
import os
from pathlib import Path
from functools import partial
from . import storage
from .uml_model import VERSION, class_name, validate

EXTENSION = ".uml.json"
dumps = partial(storage.dumps, validator=validate)
def _read_validate(document):
    # Frühere Schreibweisen bis auf den Anfangsbuchstaben beibehalten.
    document = copy.deepcopy(document)
    if isinstance(document, dict) and isinstance(document.get("classes"), list):
        for card in document["classes"]:
            if isinstance(card, dict) and isinstance(card.get("name"), str):
                card["name"] = class_name(card["name"])
        names = [card.get("name") for card in document["classes"] if isinstance(card, dict) and isinstance(card.get("name"), str)]
        if len(names) != len(set(names)):
            raise ValueError(tr('Capitalizing the first letter produces duplicate class names. Please give these classes distinct names in the file.'))
    if isinstance(document, dict) and type(document.get("version")) is int and document["version"] in (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12):
        document["version"] = VERSION
        document.setdefault("comments", [])
        document.setdefault("relationships", [])
        if isinstance(document["relationships"], list):
            for relation in document["relationships"]:
                if isinstance(relation, dict):
                    relation.setdefault("kind", "association")
                    relation.setdefault("direction", "")
                    relation.setdefault("label", "")
                    relation.setdefault("start_role", "")
                    relation.setdefault("end_role", "")
    validate(document)
    # Class kinds determine whether a base link is inheritance or realization.
    # This updates the notation of older files without changing Python headers.
    from .uml_relationships import BASE_RELATIONSHIPS, base_relationship_kind
    for relation in document['relationships']:
        if relation['kind'] in BASE_RELATIONSHIPS:
            relation['kind'] = base_relationship_kind(document, relation['start'], relation['end'])
    return document


loads = partial(storage.loads, validator=_read_validate)


def read_document(path):
    document = storage.read_document(path, validator=_read_validate)
    for card in [*document["classes"], *document.get("removed_classes", [])]:
        if "source" in card:
            source = card["source"]
            source["path"] = os.path.abspath(Path(path).parent / source["path"])
    return document


def write_document(path, document):
    validate(document)
    document = copy.deepcopy(document)
    for card in [*document["classes"], *document.get("removed_classes", [])]:
        if "source" in card:
            source = card["source"]
            if Path(source["path"]).is_absolute():
                try:
                    source["path"] = Path(os.path.relpath(source["path"], Path(path).parent)).as_posix()
                except ValueError:
                    # Windows cannot express a relative path across drive letters.
                    pass
    storage.write_document(path, document, validator=validate)


def is_model_path(path):
    return str(path).lower().endswith(EXTENSION)
