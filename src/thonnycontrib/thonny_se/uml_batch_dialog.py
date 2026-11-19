# SPDX-FileCopyrightText: 2026 Sebastian Ladhoff
# SPDX-License-Identifier: GPL-3.0-only
# See LICENSE in the project root for the full license text.

"""One file-grouped, two-card review for one or many linked classes."""
from collections import OrderedDict
from pathlib import Path
import tkinter as tk
from tkinter import font, ttk

from thonny import get_workbench
from .dialogs import EditDialog
from .i18n import tr
from .iconregistry import menu_icon
from .scrolling import ScrollArea
from .tooltips import attach_tip
from .uml_transfer_indicator import TransferIndicator
from .uml_batch import TO_CODE
from .uml_review_cards import CardReview, TOTAL_WIDTH, CARD_WIDTH, MARGIN, GAP


def title(direction):
    return tr('Update Python code') if direction == TO_CODE else tr('Update class diagram')


class CodeReview(CardReview):
    def __init__(self,parent,entry,full=False):
        super().__init__(parent,entry,TO_CODE,full)


class DiagramReview(CardReview):
    def __init__(self,parent,entry,full=False):
        from .uml_batch import FROM_CODE
        super().__init__(parent,entry,FROM_CODE,full)


class BatchUpdateDialog(EditDialog):
    def __init__(self,parent,batch,*,caption=None,allow_empty=False,full=False):
        self.batch,self.reviews,self.result = batch,{},None
        self.allow_empty = allow_empty
        self.initial_full = full
        super().__init__(parent,caption or title(batch.direction))

    def _file_header(self,parent,path,*,packed=True):
        row = ttk.Frame(parent)
        if packed:
            row.pack(fill='x',pady=(0,10))
        row.icon = ttk.Label(row)
        row.icon.grid(row=0,column=0,rowspan=2,sticky='n',padx=(0,9),pady=2)
        row.filename = ttk.Label(row,font=self.heading,wraplength=TOTAL_WIDTH-40,justify='left')
        row.filename.grid(row=0,column=1,sticky='w')
        row.folder = ttk.Label(row,font=self.small,foreground=self.muted)
        row.folder.grid(row=1,column=1,sticky='w',pady=(2,0))
        self._set_file_header(row,path)
        row.tips = [attach_tip(label,lambda row=row:row.path or tr('Classes without a source file'))
                    for label in (row.icon,row.filename,row.folder)]
        return row

    def _set_file_header(self,row,path):
        for tip in getattr(row,'tips',[]):
            tip.hide()
        row.path = path
        row.icon.configure(image=menu_icon(get_workbench(),'document.python' if path else 'document.uml'))
        row.filename.configure(text=Path(path).name if path else tr('Classes without a source file'))
        folder = str(Path(path).parent) if path else ''
        clipped = folder
        while clipped and self.small.measure(clipped)>TOTAL_WIDTH-40:
            clipped = '…'+clipped[2:] if clipped.startswith('…') else '…'+clipped[1:]
        row.folder.configure(text=clipped)

    def _sync_sticky(self):
        if not hasattr(self,'file_groups') or not hasattr(self,'sticky_header'):
            return
        visible = [(frame,self.boundary_headers[frame],self.group_paths[frame])
                   for frame,_ in self.file_groups if frame.winfo_manager()]
        if not visible:
            self.sticky_header.place_forget()
            return
        top = self.canvas.canvasy(0)
        index = 0
        for i,(frame,header,path) in enumerate(visible):
            if frame.winfo_y()+header.winfo_y() <= top:
                index = i
            else:
                break
        frame,header,path = visible[index]
        start = frame.winfo_y()+header.winfo_y()
        if self.current_file != path:
            self.current_file = path
            self._set_file_header(self.sticky_header,path)
        if top <= start:
            self.sticky_header.place_forget()
            return
        height = header.winfo_reqheight()
        push = 0
        if index+1 < len(visible):
            next_frame,next_header,_ = visible[index+1]
            distance = next_frame.winfo_y()+next_header.winfo_y()-top
            push = min(0,distance-height)
        self.sticky_header.place(x=0,y=push,width=self.canvas.winfo_width(),height=height)
        self.sticky_header.lift()

    def _scrolled(self,*fractions):
        self.scrollbar.set(*fractions)
        self._sync_sticky()

    def _direction_header(self,master):
        frame = ttk.Frame(master)
        frame.pack(fill='x',pady=(0,5))
        self.transfer_indicator = TransferIndicator(frame,to_code=self.batch.direction==TO_CODE,width=TOTAL_WIDTH,
            source_x=MARGIN+CARD_WIDTH/2,target_x=MARGIN+CARD_WIDTH+GAP+CARD_WIDTH/2)
        self.transfer_indicator.pack(anchor='w',padx=(4,0),pady=(0,3))
        background = ttk.Style(self).lookup('TFrame','background')
        canvas = self.direction_bar = tk.Canvas(frame,width=TOTAL_WIDTH,height=27,highlightthickness=0,background=background)
        canvas.pack(anchor='w',padx=(4,0))
        labels = (tr('Source: Diagram'),tr('Target: Code')) if self.batch.direction==TO_CODE else (tr('Source: Code'),tr('Target: Diagram'))
        for x,text in ((MARGIN,labels[0]),(MARGIN+CARD_WIDTH+GAP,labels[1])):
            canvas.create_text(x+CARD_WIDTH/2,11,text=text,font=self.small,fill=self.muted,anchor='center')
        help_text = tr('Checked changes are copied from the source on the left to the target on the right. All available changes start checked except conflicts.')
        if self.batch.direction==TO_CODE:
            help_text += '\n'+tr('Updated Python files open in Thonny. Save them afterwards as usual.')
        attach_tip(canvas,help_text)
        return frame

    def build_body(self,master):
        self.muted = '#b5beca' if get_workbench().uses_dark_ui_theme() else '#667383'
        self.heading = font.nametofont('TkDefaultFont').copy()
        self.heading.configure(size=self.heading.actual('size')+3,weight='bold')
        self.small = font.nametofont('TkDefaultFont').copy()
        self.small.configure(size=max(9,self.small.actual('size')-1))
        files = OrderedDict()
        for entry in self.batch.entries:
            files.setdefault(entry.key or entry.path or None,[]).append(entry)
        self.current_file = self.batch.entries[0].path if self.batch.entries else ''
        self.mode = tk.StringVar(self,value='full' if self.initial_full else 'changes')
        direction = self._direction_header(master)
        area = ttk.Frame(master);area.pack(fill='both',expand=True)
        background = ttk.Style(self).lookup('TFrame','background')
        ttk.Style(self).configure('SE.Review.row.TCheckbutton',background=background)
        ttk.Style(self).map('SE.Review.row.TCheckbutton',background=[('active',background),('!active',background)])
        self.canvas = tk.Canvas(area,width=TOTAL_WIDTH+18,height=460,highlightthickness=0,background=background)
        scrollbar = self.scrollbar = ttk.Scrollbar(area,orient='vertical',command=self.canvas.yview)
        scrollbar.pack(side='right',fill='y')
        self.canvas.configure(yscrollcommand=self._scrolled);self.canvas.pack(side='left',fill='both',expand=True)
        content = self.content = ttk.Frame(self.canvas,padding=(0,0,10,4))
        window = self.canvas.create_window(0,0,window=content,anchor='nw')
        content.bind('<Configure>',lambda event:self.canvas.configure(scrollregion=self.canvas.bbox('all')))
        self.canvas.bind('<Configure>',lambda event:(self.canvas.itemconfigure(window,width=event.width),self._sync_sticky()))
        self.sticky_header = self._file_header(self.canvas,self.current_file,packed=False)
        self.file_groups = []
        self.group_paths,self.boundary_headers = {},{}
        for key,entries in files.items():
            file_frame = ttk.Frame(content)
            self.group_paths[file_frame] = entries[0].path
            self.boundary_headers[file_frame] = self._file_header(file_frame,entries[0].path)
            blocks = []
            for entry in entries:
                if entry.action == 'already_removed':
                    continue
                if entry.error:
                    error = ttk.Frame(file_frame)
                    ttk.Label(error,text=entry.card['name'],font='TkHeadingFont').pack(anchor='w')
                    ttk.Label(error,text=entry.error,wraplength=TOTAL_WIDTH-20,justify='left').pack(anchor='w',pady=(3,14))
                    blocks.append((error,True))
                    continue
                review = (CodeReview(file_frame,entry,full=self.initial_full) if self.batch.direction==TO_CODE
                          else DiagramReview(file_frame,entry,full=self.initial_full))
                blocks.append((review,review.has_changes));self.reviews[entry.cid]=review
            self.file_groups.append((file_frame,blocks))
        self.empty_label = ttk.Label(self.canvas,text=tr('There are no changes to apply.'),padding=12,anchor='center',justify='center')
        self._show_groups()
        content.update_idletasks()
        self.canvas.configure(height=min(460,max(180,content.winfo_reqheight())))
        self.scrolling = ScrollArea(self.canvas,area,axes='y')
        self.scrolling.bind(self.sticky_header)
        self.scrolling.bind(direction)
        self._sync_sticky()
        return self.canvas

    def _show_groups(self):
        full = self.mode.get() == 'full'
        self.empty_label.place_forget()
        shown = False
        for frame,blocks in self.file_groups:
            frame.pack_forget()
            boundary = self.boundary_headers[frame]
            boundary.pack_forget()
            visible_blocks = []
            visible = False
            for block,changed in blocks:
                block.pack_forget()
                if full or changed:
                    block.pack(fill='x',pady=(0,18));visible=True
                    visible_blocks.append(block)
            if visible:
                boundary.pack(fill='x',pady=(0,10),before=visible_blocks[0])
                frame.pack(fill='x');shown=True
        if not shown:
            self.empty_label.place(relx=.5,rely=.5,anchor='center')
            self.empty_label.lift()

    def _mode_changed(self):
        for review in self.reviews.values():
            review.set_full(self.mode.get()=='full')
        self._show_groups()
        self.scrolling.bind(self.canvas)
        self.update_idletasks()
        self.canvas.configure(height=min(460,max(180,self.content.winfo_reqheight())))
        self.update_idletasks();self.canvas.yview_moveto(0)
        self._sync_sticky()

    def _can_apply(self):
        return self.allow_empty or any(review.selection() for review in self.reviews.values())

    def _update_apply(self,*args):
        if hasattr(self,'apply_button'):
            self.apply_button.configure(state='normal' if self._can_apply() else 'disabled')

    def buttonbox(self):
        actions = ttk.Frame(self, padding=(20, 4, 20, 16), style='SE.TFrame')
        actions.pack(fill='x')
        toolbar = ttk.Frame(actions)
        toolbar.grid(row=0, column=0, sticky='w')
        for value,label in (('changes',tr('Changes only')),('full',tr('Complete classes'))):
            ttk.Radiobutton(toolbar,text=label,variable=self.mode,value=value,
                            command=self._mode_changed,style='SE.TRadiobutton').pack(side='left',padx=(0,16))
        actions.columnconfigure(1, weight=1)
        self._action_button(actions, 2, tr('Cancel'), self.cancel, gap=8)
        self.apply_button = self._action_button(actions, 3, tr('OK'), self.ok)
        self.bind('<Return>', self.ok)
        self.bind('<KP_Enter>', self.ok)
        self.bind('<Escape>', self.cancel)
        for review in self.reviews.values():
            for variable in review.variables.values():
                variable.trace_add('write',self._update_apply)
        self._update_apply()

    def validate(self):
        return bool(self._can_apply())

    def apply(self):
        self.result={cid:review.selection() for cid,review in self.reviews.items()}
