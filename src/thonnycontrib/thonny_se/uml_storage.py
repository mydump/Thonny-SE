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
from .uml_model import validate

EXTENSION = ".uml.json"
dumps = partial(storage.dumps, validator=validate)
def _read_validate(document):
    document = copy.deepcopy(document)
    validate(document)
    # Class kinds determine whether a base link is inheritance or realization.
    # Keep relationship notation consistent without changing Python headers.
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
