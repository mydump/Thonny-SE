# SPDX-FileCopyrightText: 2026 Sebastian Ladhoff
# SPDX-License-Identifier: GPL-3.0-only
# See LICENSE in the project root for the full license text.

"""A lightweight direction illustration, not a synchronization/progress display."""
import colorsys
import math
import time
import tkinter as tk
from tkinter import font,ttk

from thonny import get_workbench
from . import retina_icons
from .iconregistry import icon_path
from .i18n import tr
from .tooltips import attach_tip


class TransferIndicator(tk.Canvas):
    def __init__(self,parent,*,to_code,width=660,source_x=158,target_x=502):
        background=ttk.Style(parent).lookup('TFrame','background')
        super().__init__(parent,width=width,height=40,background=background,highlightthickness=0)
        self.direction=1
        self.stream_left=source_x+26
        self.stream_span=target_x-source_x-52
        self.job=None
        self.started=time.monotonic()
        self.images=[]
        self.icon_face=font.nametofont('TkDefaultFont').copy();self.icon_face.configure(size=22)
        self.bit_face=font.nametofont('TkFixedFont').copy();self.bit_face.configure(size=10,weight='bold')
        dark=get_workbench().uses_dark_ui_theme()
        ink='#b5beca' if dark else '#667383'
        self.rainbow_saturation=0.62 if dark else 0.80
        self.rainbow_value=0.96 if dark else 0.72
        self.background_rgb=tuple(channel/257 for channel in self.winfo_rgb(background))
        roles=('document.uml','document.python') if to_code else ('document.python','document.uml')
        for x,role in zip((source_x,target_x),roles):
            if retina_icons.enabled(self):
                self.create_text(x,20,text=retina_icons.glyph(role),font=retina_icons.font_for(self,self.icon_face),fill=ink,tags=role)
            else:
                image=get_workbench().get_image(icon_path(role,size=24,dark=dark))
                self.images.append(image);self.create_image(x,20,image=image,tags=role)
        self.bits=[self.create_text(0,0,text=value,font=self.bit_face,fill=ink,tags='transfer-bit')
                   for value in '101001011010100101']
        self.bind('<Map>',self.start)
        self.bind('<Unmap>',self.stop)
        self.bind('<Destroy>',self.stop)
        message=tr('Diagram to code') if to_code else tr('Code to diagram')
        attach_tip(self,message+'\n'+tr('Shows the transfer direction. Changes are applied only after confirmation.'))
        self._paint(0)

    def _blend(self,foreground,amount):
        return '#'+''.join(f'{round(a*255*amount+b*(1-amount)):02x}'
                          for a,b in zip(foreground,self.background_rgb))

    def _paint(self,elapsed):
        left,span=self.stream_left,self.stream_span
        for index,item in enumerate(self.bits):
            progress=(index/len(self.bits)+self.direction*elapsed/5.5)%1
            x=left+span*progress
            y=20+4*math.sin(progress*math.tau*2-self.direction*elapsed*1.5)
            fade=min(1,progress*8,(1-progress)*8)
            self.coords(item,x,y)
            self.itemconfigure(item,fill=self._blend(colorsys.hsv_to_rgb(progress*5/6,self.rainbow_saturation,self.rainbow_value),max(0,fade)))

    def start(self,event=None):
        if event is not None and event.widget is not self:
            return
        if self.job is None:
            self._tick()

    def _tick(self):
        self.job=None
        if self.winfo_exists() and self.winfo_ismapped():
            self._paint(time.monotonic()-self.started)
            self.job=self.after(60,self._tick)

    def stop(self,event=None):
        if event is not None and event.widget is not self:
            return
        if self.job is not None:
            self.after_cancel(self.job)
            self.job=None
