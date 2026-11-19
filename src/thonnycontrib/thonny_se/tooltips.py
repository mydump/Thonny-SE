# SPDX-FileCopyrightText: 2026 Sebastian Ladhoff
# SPDX-License-Identifier: GPL-3.0-only
# See LICENSE in the project root for the full license text.

"""Position Thonny's existing ToolTip at drawn elements; no alternative renderer."""
import tkinter as tk
from thonny.ui_utils import ToolTip,get_style_configuration


def _options():
    options=get_style_configuration('Tooltip').copy()
    for key,value in dict(background='#ffffe0',foreground='#000000',relief='solid',borderwidth=1,padx=1,pady=0).items():
        options.setdefault(key,value)
    options.update(wraplength=420,justify='left')
    return options


def _top(tip):
    top=getattr(tip,'_tooltip_top',None)
    return top if top is not None else getattr(tip,'canvas',tip.widget).winfo_toplevel()


def _show_thonny(tip,text):
    top=_top(tip)
    before=set(top._tclCommands or ())
    ToolTip.showtip(tip,text)
    if not tip.focus_out_bind_ref:
        # Workbench.bind discards Tk's ID in Thonny 5. Recover only our native handler.
        handlers=[name for name in set(top._tclCommands or ())-before if name.endswith('hidetip')]
        if len(handlers)==1:tip.focus_out_bind_ref=handlers[0]


def _hide_thonny(tip,event=None):
    binding=tip.focus_out_bind_ref
    try:ToolTip.hidetip(tip,event)
    except tk.TclError:pass
    if binding:
        # Thonny 5 checks tipwindow after clearing it, leaving its FocusOut handler.
        try:_top(tip).unbind('<FocusOut>',binding)
        except tk.TclError:pass
    tip.focus_out_bind_ref=None


def attach_tip(widget,text):
    """Use the native Thonny instance on normal widgets, the anchor only on canvases."""
    if isinstance(widget,tk.Canvas):
        tip=CanvasToolTip(widget)
        def enter(event):tip.request(text() if callable(text) else text,event.x_root,event.y_root)
        for sequence in ('<Enter>','<Motion>'):widget.bind(sequence,enter,add=True)
        return tip
    tip=ToolTip(widget,_options())
    tip._tooltip_top=widget.winfo_toplevel()
    def hide(event=None):_hide_thonny(tip,event)
    def enter(event):
        value=text() if callable(text) else text
        if not value:hide();return
        if tip.tipwindow is not None and getattr(tip,'text','')==value:return
        hide()
        _show_thonny(tip,value)
    # Existing dynamic file headers need explicit dismissal before changing their path.
    tip.hide=hide
    for sequence in ('<Enter>','<Motion>'):widget.bind(sequence,enter,add=True)
    for sequence in ('<Leave>','<Unmap>','<Destroy>'):widget.bind(sequence,hide,add=True)
    return tip


class _CanvasAnchor(tk.Frame):
    """Unmapped real widget providing the insertion-box anchor ToolTip expects."""
    def __init__(self,canvas):
        super().__init__(canvas,takefocus=False)
        self.point=(0,0)

    def bbox(self,*args):return (*self.point,0,0)
    def winfo_rootx(self):return self.master.winfo_rootx()
    def winfo_rooty(self):return self.master.winfo_rooty()
    def winfo_height(self):return 0


class CanvasToolTip(ToolTip):
    def __init__(self,canvas):
        self.canvas=canvas
        self.anchor=_CanvasAnchor(canvas)
        super().__init__(self.anchor,_options())
        self._tooltip_top=canvas.winfo_toplevel()
        self.text=''
        self.key=None
        self.suppressed=None
        self.bindings=[(seq,canvas.bind(seq,self.leave,add=True)) for seq in ('<Leave>','<Unmap>')]
        self.bindings.append(('<Destroy>',canvas.bind('<Destroy>',self.destroy,add=True)))

    def request(self,text,x,y,key=None):
        if not text:
            self.suppressed=None
            self.hidetip()
            return
        if key is None:key=text
        if self.suppressed==key:return
        self.suppressed=None
        if self.tipwindow is not None and self.text==text and self.key==key:return
        self.hidetip()
        self.key=key
        self.anchor.point=(x-self.canvas.winfo_rootx(),y-self.canvas.winfo_rooty())
        # Window, label, colours and platform behaviour are all Thonny's implementation.
        _show_thonny(self,text)

    def dismiss(self):
        self.suppressed=self.key
        self.hidetip()

    def leave(self,event=None):
        self.suppressed=None
        self.hidetip()

    def hidetip(self,event=None):
        _hide_thonny(self,event)
        self.key=None
        self.text=''

    hide=hidetip

    def destroy(self,event=None):
        if event is not None and event.widget is not self.canvas:return
        self.hidetip()
        for sequence,binding in self.bindings:
            try:self.canvas.unbind(sequence,binding)
            except tk.TclError:pass
        self.bindings=[]
        try:self.anchor.destroy()
        except tk.TclError:pass
