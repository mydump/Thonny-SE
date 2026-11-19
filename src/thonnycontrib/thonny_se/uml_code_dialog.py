# SPDX-FileCopyrightText: 2026 Sebastian Ladhoff
# SPDX-License-Identifier: GPL-3.0-only
# See LICENSE in the project root for the full license text.

"""Compatibility adapter: one code plan uses the shared card review."""
from .uml_batch import Batch, Entry, TO_CODE, file_key
from .uml_batch_dialog import BatchUpdateDialog
from .uml_model import new_document


class CodeUpdateDialog(BatchUpdateDialog):
    def __init__(self,parent,plan):
        self.plan = plan
        document = new_document();document['classes']=[plan.card]
        entry = Entry(plan.card,plan.path,file_key(plan.path),plan=plan)
        super().__init__(parent,Batch(document,TO_CODE,entries=[entry]))

    def build_body(self,master):
        result = super().build_body(master)
        self.choices = self.reviews[self.plan.card['id']].choices
        return result

    def apply(self):
        self.result = self.reviews[self.plan.card['id']].selection()
