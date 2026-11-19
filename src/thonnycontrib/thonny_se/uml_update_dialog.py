# SPDX-FileCopyrightText: 2026 Sebastian Ladhoff
# SPDX-License-Identifier: GPL-3.0-only
# See LICENSE in the project root for the full license text.

"""Source assignment and older callers use the same two-card review."""
from .i18n import tr
from .uml_batch import Batch, Entry, FROM_CODE, file_key
from .uml_batch_dialog import BatchUpdateDialog
from .uml_model import new_document

UPDATE_CLASS_LABEL = tr('Update class from code')


class UmlUpdateDialog(BatchUpdateDialog):
    def __init__(self,parent,card,source,plan,*,header=None,reassign=False,first_link=False):
        self.card,self.source,self.plan = card,source,plan
        self.header,self.reassign = header,reassign
        document = new_document();document['classes']=[card]
        path = source['path']
        entry = Entry(card,path,file_key(path),source=source,plan=plan,header=header)
        caption = tr('Link Python source file') if first_link else tr('Relink Python source file') if reassign else None
        super().__init__(parent,Batch(document,FROM_CODE,entries=[entry]),caption=caption,
                         allow_empty=first_link or source['path'] != card.get('source',{}).get('path'))

    def build_body(self,master):
        result = super().build_body(master)
        self.choices = self.reviews[self.card['id']].choices
        return result

    def apply(self):
        self.result = self.reviews[self.card['id']].selection()
