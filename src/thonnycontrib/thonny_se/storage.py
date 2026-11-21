# SPDX-FileCopyrightText: 2026 Sebastian Ladhoff
# SPDX-License-Identifier: GPL-3.0-only
# See LICENSE in the project root for the full license text.

"""UTF-8-JSON-Dateien mit Schema-Prüfung und atomarem Speichern."""
from .i18n import tr
import json
import os
import stat
import tempfile
from pathlib import Path

from .model import validate

EXTENSION = ".nsd.json"
_DIAGRAM_EXTENSIONS = (EXTENSION, ".uml.json")
# Worst case: 1000 Blöcke mit je 10000 Zeichen, inklusive JSON-Escapes.
MAX_FILE_CHARS = 64_000_000


def is_model_path(path):
    return str(path).lower().endswith(EXTENSION)


def is_diagram_path(path):
    return str(path).lower().endswith(_DIAGRAM_EXTENSIONS)


def diagram_stem(path):
    name = Path(path).name
    for extension in _DIAGRAM_EXTENSIONS:
        if name.lower().endswith(extension):
            return name[:-len(extension)]
    return Path(name).stem


def dumps(document, validator=validate):
    validator(document)
    return json.dumps(document, ensure_ascii=False, indent=2) + "\n"


def loads(text, validator=validate):
    try:
        return validator(json.loads(text))
    except (json.JSONDecodeError, RecursionError) as exc:
        raise ValueError(tr('The file does not contain a valid JSON model.')) from exc


def read_document(path, validator=validate):
    with Path(path).open("r", encoding="utf-8") as stream:
        text = stream.read(MAX_FILE_CHARS + 1)
    if len(text) > MAX_FILE_CHARS:
        raise ValueError(tr('The model file is too large.'))
    return loads(text, validator)


def write_document(path, document, validator=validate):
    write_text(path, dumps(document, validator))


def write_text(path, content):
    """Text atomar als UTF-8 speichern; vorhandene Datei bei Fehler erhalten."""
    _write(path, content, binary=False)


def write_new_text(path, content):
    """Publish a complete new file without replacing any existing entry."""
    _write(path, content, binary=False, replace=False)


def write_bytes(path, content):
    _write(path, content, binary=True)


def _write(path, content, binary, *, replace=True):
    path = Path(path)
    # Symlinks wie beim gewöhnlichen Speichern am Ziel aktualisieren.
    if replace:
        path = path.resolve()
    temporary = None
    try:
        if replace and path.exists() and not os.access(path, os.W_OK):
            raise PermissionError(tr('The model file is read-only.'))
        mode = stat.S_IMODE(path.stat().st_mode) if replace and path.exists() else None
        with tempfile.NamedTemporaryFile(mode="wb" if binary else "w", encoding=None if binary else "utf-8", dir=path.parent,
                                         prefix=".thonny-se-", delete=False) as stream:
            temporary = stream.name
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        if mode is not None:
            os.chmod(temporary, mode)
        if replace:
            os.replace(temporary, path)
        else:
            os.link(temporary, path)
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)
