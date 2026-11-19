# SPDX-FileCopyrightText: 2026 Sebastian Ladhoff
# SPDX-License-Identifier: GPL-3.0-only
# See LICENSE in the project root for the full license text.

"""Edit imported exception clauses without offering a new palette element."""
import copy
import keyword
import tkinter as tk
from tkinter import ttk,messagebox
from .dialogs import EditDialog
from .i18n import tr


class ExceptionDialog(EditDialog):
    def __init__(self,parent,node):
        self.node=node
        self.result=None
        self.values=[]
        super().__init__(parent,tr('Edit exception handling'))

    def build_body(self,master):
        ttk.Label(master,text=tr('This block was imported from Python.')).grid(row=0,column=0,columnspan=2,sticky='w',pady=(0,10))
        ttk.Label(master,text=tr('Exception type')).grid(row=1,column=0,sticky='w')
        ttk.Label(master,text=tr('Exception variable')).grid(row=1,column=1,sticky='w')
        first=None
        for row,handler in enumerate(self.node['handlers'],start=2):
            kind=tk.StringVar(master,value=handler['type']);name=tk.StringVar(master,value=handler['name'])
            field=ttk.Entry(master,textvariable=kind,width=38,style='SE.TEntry')
            field.grid(row=row,column=0,padx=(0,8),pady=4,sticky='ew')
            ttk.Entry(master,textvariable=name,width=18,style='SE.TEntry').grid(row=row,column=1,pady=4,sticky='ew')
            self.values.append((kind,name))
            if first is None:first=field
        ttk.Label(master,text=tr('A blank exception type catches all exceptions.')).grid(row=2+len(self.values),column=0,columnspan=2,sticky='w',pady=(8,0))
        return first

    def validate(self):
        for kind,name in self.values:
            if len(kind.get())>1000 or len(name.get())>200:
                messagebox.showerror(tr('Edit exception handling'),tr('Block text must not exceed {p0} characters.').format(p0=1000),parent=self)
                return False
            if name.get() and (not name.get().isidentifier() or keyword.iskeyword(name.get())):
                messagebox.showerror(tr('Edit exception handling'),tr('Please enter a valid exception variable name.'),parent=self)
                return False
        handlers=[]
        for kind,name in self.values:
            value=kind.get().strip()+(' as '+name.get() if name.get() else '')
            handlers.append(('except*' if self.node.get('starred',False) else 'except')+(' '+value if value else '')+':\n    pass')
        code='try:\n    pass\n'+'\n'.join(handlers)
        if self.node['else'] is not None:code+='\nelse:\n    pass'
        if self.node['finally'] is not None:code+='\nfinally:\n    pass'
        try:compile(code,'<Thonny-SE-Exception>','exec')
        except SyntaxError as exc:
            messagebox.showerror(tr('Edit exception handling'),tr('Exception clause: {message}').format(message=exc.msg),parent=self)
            return False
        return True

    def apply(self):
        handlers=copy.deepcopy(self.node['handlers'])
        for handler,(kind,name) in zip(handlers,self.values):handler.update(type=kind.get().strip(),name=name.get())
        self.result={'handlers':handlers}
