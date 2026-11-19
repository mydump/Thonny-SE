# SPDX-FileCopyrightText: 2026 Sebastian Ladhoff
# SPDX-License-Identifier: GPL-3.0-only
# See LICENSE in the project root for the full license text.

"""A single loaded diagram; editing never destroys its live objects."""
from .uml_runtime import diagram_fingerprint


class ExecutionState:
    def __init__(self):
        self.clear()

    def clear(self):
        self.owner = None
        self.fingerprint = None
        self.stale = False

    def loaded(self, editor, fingerprint):
        self.owner, self.fingerprint = editor, fingerprint
        self.stale = diagram_fingerprint(editor.document) != fingerprint

    def changed(self, editor):
        if self.owner is editor and diagram_fingerprint(editor.document) != self.fingerprint:
            self.stale = True

    def ready(self, editor):
        return self.owner is editor and not self.stale and diagram_fingerprint(editor.document) == self.fingerprint
