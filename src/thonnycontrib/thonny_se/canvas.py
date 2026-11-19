# SPDX-FileCopyrightText: 2026 Sebastian Ladhoff
# SPDX-License-Identifier: GPL-3.0-only
# See LICENSE in the project root for the full license text.

"""Nassi-Shneiderman-Darstellung, Symbolpalette und auswählbare Bereiche."""
from .scrolling import ScrollArea
from .zooming import capture_anchor, restore_anchor
from .display_context import context_for
from .visual_metrics import Typography, preserve_scroll
from .i18n import tr
import tkinter as tk
from random import getrandbits
from dataclasses import dataclass
from tkinter import ttk

from .cat_head import draw_cat_head
from .diagram_hint import DiagramHint
from .diagram_preferences import STRUCTOGRAM_CAT_BLOCKS, STRUCTOGRAM_HINTS, enabled
from .model import IF_KINDS, LOOP_KINDS, Selection, body_at, child_bodies
from .ui_style import EDGE, INK, MUTED, SELECT, SELECTION_WIDTH

from .graphics import badge, clear_shapes
from .ui_style import HINT_BADGE, HINT_INK
from .ui_style import NSD_SECTION_FILLS, NSD_DISABLED_FILL, NSD_DISABLED_INK, NSD_DISABLED_EDGE

HEADER = NSD_SECTION_FILLS


@dataclass
class Region:
    bounds: tuple
    selection: Selection


class StructogramCanvas(ttk.Frame):
    def __init__(self, master, on_select, on_edit):
        super().__init__(master)
        self.document = None
        self.selection = Selection()
        self.on_select, self.on_edit = on_select, on_edit
        self.regions = []
        self.insertion_regions = {}
        self.monochrome = False
        self.exporting = False
        self.render_width = None
        self.zoom = 1.0
        self.cat_seed = getrandbits(64)
        self.typography = Typography(self)
        self._font = self.typography["body"]
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)
        self.canvas = tk.Canvas(self, background="#ffffff", highlightthickness=0,
                                width=640, height=360, takefocus=True)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        vertical = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        vertical.grid(row=0, column=1, sticky="ns")
        horizontal = ttk.Scrollbar(self, orient="horizontal", command=self.canvas.xview)
        horizontal.grid(row=1, column=0, sticky="ew")
        self.info_hint = DiagramHint(self.canvas, STRUCTOGRAM_HINTS)
        from .tooltips import CanvasToolTip
        self.try_tip = CanvasToolTip(self.canvas)
        self._try_info_regions = []
        self._hint_viewport = None
        self.canvas.bind('<Motion>',self._hover_try,add=True)

        def update_scrollbar(scrollbar, *args):
            scrollbar.set(*args)
            viewport=(self.canvas.canvasx(0),self.canvas.canvasy(0),self.canvas.winfo_width(),self.canvas.winfo_height())
            if viewport != self._hint_viewport:
                self._hint_viewport=viewport
                self._refresh_try_tip()
                self.info_hint.draw()

        self.canvas.configure(yscrollcommand=lambda *args: update_scrollbar(vertical, *args),
                              xscrollcommand=lambda *args: update_scrollbar(horizontal, *args))
        self.canvas.bind("<Button-1>", self._click)
        self.canvas.bind("<Double-Button-1>", self._double_click)
        self.canvas.bind("<Configure>", lambda event: self.draw())
        self.canvas.bind("<Map>", lambda event: self.canvas.after_idle(self._redraw_mapped))
        self.scrolling = ScrollArea(self.canvas, self,
            zoom=lambda steps: self.set_zoom(self.zoom + steps*0.1),
            zoom_at=self._zoom_at_pointer)
        self._height_cache = {}
        self._width_cache = {}
        self._body_height_cache = {}
        context_for(self).subscribe(self,self._display_changed)

    def _display_changed(self, state):
        self.typography.refresh(self.zoom)
        if self.winfo_ismapped():preserve_scroll(self.canvas,self.draw)

    def _text(self, *args, **kwargs):
        kwargs.setdefault('font',self._font)
        if 'width' in kwargs:kwargs['width'] *= self.zoom
        return self.canvas.create_text(*args,**kwargs)

    def _redraw_mapped(self):
        # Ein Tab kann ohne Größenänderung sichtbar werden. Nach dem Mapping
        # neu zeichnen, statt auf Configure oder eine Mausbewegung zu warten.
        if self.canvas.winfo_exists() and self.canvas.winfo_ismapped():
            self.draw()

    def _zoom_at_pointer(self,steps,position):
        anchor=capture_anchor(self.canvas,self.zoom,position)
        self.set_zoom(self.zoom+steps*.1,anchor=anchor)

    def set_zoom(self, value, *, anchor=None):
        self.zoom = round(max(0.5, min(2.0, value)), 2)
        self.draw()
        restore_anchor(self.canvas,self.zoom,anchor)
        if hasattr(self, "on_zoom"):
            self.on_zoom(self.zoom)
        return self.zoom

    def show(self, document, selection):
        self.document, self.selection = document, selection
        self.draw()

    def region_at(self, x, y):
        # Kinder überdecken ihre Körper; freie Flächen wählen den Körper.
        for region in reversed(self.regions):
            x1, y1, x2, y2 = region.bounds
            if x1 <= x <= x2 and y1 <= y <= y2:
                return region.selection
        return None

    def _click(self, event):
        self.try_tip.dismiss()
        self.canvas.focus_set()
        selection = self.region_at(self.canvas.canvasx(event.x), self.canvas.canvasy(event.y))
        if selection is not None:
            self.on_select(selection)

    def _double_click(self, event):
        self._click(event)
        if self.selection.index is not None:
            self.on_edit()
        return "break"

    def reveal_selection(self):
        selection = Selection(self.selection.path, self.selection.index, self.selection.at_start)
        region = next((r for r in reversed(self.regions) if r.selection == (Selection(selection.path) if selection.at_start else selection)), None)
        if region is None:
            return
        x1, y1, x2, y2 = self.insertion_regions[selection.path] if selection.index is None and not selection.at_start else region.bounds
        left, top = self.canvas.canvasx(0), self.canvas.canvasy(0)
        width, height = self.canvas.winfo_width(), self.canvas.winfo_height()
        extent = tuple(float(v) for v in self.canvas.cget("scrollregion").split())
        if len(extent) != 4:
            return
        if y1 < top or y2 > top + height:
            self.canvas.yview_moveto(max(0, y1 - 16) / max(extent[3], 1))
        if x1 < left or x2 > left + width:
            self.canvas.xview_moveto(max(0, x1 - 16) / max(extent[2], 1))

    def _text_height(self, text, width):
        key = (text, width)
        if key not in self._height_cache:
            item = self._text(0, 0, text=text or " ", width=max(20, width), anchor="nw")
            bounds = self.canvas.bbox(item)
            self._height_cache[key] = (bounds[3] - bounds[1])/self.zoom if bounds else 16
            self.canvas.delete(item)
        return self._height_cache[key]

    def _label(self, node):
        if node['kind']=='try':return tr('Exception handling')
        if node["kind"] == "repeat":
            return tr('REPEAT {count} TIMES').format(count=node['count'] or 'n')
        if node["kind"] == "for":
            template = (tr('FOR {variable} FROM {start} DOWN TO {end} STEP {step}')
                        if node["direction"] == "down" else
                        tr('FOR {variable} FROM {start} TO {end} STEP {step}'))
            return template.format(variable=node["variable"] or "i", start=node["start"] or "a",
                                   end=node["end"] or "e", step=node["step"] or "s")
        if node["kind"] == "foreach":
            return tr('FOR EACH {element} IN {collection}').format(
                element=node['element'] or 'element', collection=node['collection'] or 'liste')
        if node["kind"] in ("statement", "call"):
            return node["text"] or (tr('Function call') if node["kind"] == "call" else tr('Statement'))
        if node["kind"] == "switch":
            return node["text"] or tr('Selector')
        if node["kind"] in IF_KINDS:
            return node["text"] or tr('Condition')
        return tr('WHILE {condition}').format(condition=node['text'] or tr('Condition'))

    def _branches(self, node):
        branches = child_bodies(node)
        if node["kind"] == "if_single":
            branches.append((None, [], tr('false')))
        return branches

    def _min_width(self, body):
        key = id(body)
        if key in self._width_cache:
            return self._width_cache[key]
        width = 160
        for node in body:
            if node['kind']=='try':
                width=max(width,20+max(self._min_width(b) for _,b,_ in child_bodies(node)))
            elif node["kind"] in IF_KINDS or node["kind"] == "switch":
                width = max(width, sum(self._min_width(b) for _, b, _ in self._branches(node)))
            elif node["kind"] in LOOP_KINDS:
                width = max(width, 20 + self._min_width(node["body"]))
        self._width_cache[key] = width
        return width

    def _head_height(self, node, width):
        if node["kind"] in IF_KINDS or node["kind"] == "switch":
            height = max(76, 2 * self._text_height(self._label(node), width * 0.48) + 40)
            if node["kind"] == "switch":
                height += self._case_label_height(node, width)
            return height
        return max(48, self._text_height(self._label(node), width - 24) + 20)

    def _branch_layout(self, node, width):
        branches = self._branches(node)
        minimum = [self._min_width(body) for _, body, _ in branches]
        extra = (width - sum(minimum)) / len(branches)
        return [(path, body, label, m+extra) for (path, body, label), m in zip(branches, minimum)]

    def _case_label_height(self, node, width):
        return max(self._text_height(label, bw-12) for _, _, label, bw in self._branch_layout(node, width)) + 12

    def _body_height(self, body, width):
        key = (id(body), width)
        if key in self._body_height_cache:
            return self._body_height_cache[key]
        height = 40 if not self.exporting or not body else 0
        for node in body:
            if node['kind']=='try':
                height += sum(header+size for _,_,_,header,size in self._try_sections(node,width))
                continue
            height += self._head_height(node, width)
            if node["kind"] in LOOP_KINDS:
                height += self._body_height(node["body"], width - 20)
            elif node["kind"] in IF_KINDS or node["kind"] == "switch":
                height += max(self._body_height(b, w) for _, b, _, w in self._branch_layout(node, width))
        self._body_height_cache[key] = height
        return height

    def draw(self):
        clear_shapes(self.canvas,'try-info')
        self._try_info_points=[]
        self._try_info_regions=[]
        self.typography.refresh(self.zoom)
        self.canvas.delete("all")
        self.regions.clear()
        self.insertion_regions.clear()
        self._height_cache.clear()
        # Model dictionaries are edited in place. Keep layout caches for one draw only.
        self._width_cache.clear()
        self._body_height_cache.clear()
        if self.document is None:
            return
        body = self.document["body"]
        width = max(480, self.render_width or self.canvas.winfo_width() / self.zoom - 32, self._min_width(body))
        height = self._body_height(body, width)
        cat_blocks = enabled(STRUCTOGRAM_CAT_BLOCKS)
        top = 60 if cat_blocks else 16
        self._render_body(("body",), 16, top, width, height, tr('Diagram'))
        if cat_blocks:
            fill = HEADER[body[0]["kind"]] if body else "#ffffff"
            draw_cat_head(self.canvas, 16, top, 16 + width, self.cat_seed,
                          scale=1.3, fill=fill, bottom=top + height)
        # Auswahlrahmen zuletzt zeichnen, damit er auch Körper vollständig umfasst.
        selections = [self.selection]
        if self.selection.index is not None and self.selection.end_index is not None:
            selections = [Selection(self.selection.path, i) for i in range(self.selection.index, self.selection.end_index+1)]
        for selection in ([] if self.exporting else selections):
            region = next((r for r in reversed(self.regions) if r.selection == (Selection(selection.path) if selection.at_start else selection)), None)
            if region:
                x1, y1, x2, y2 = (self.insertion_regions[selection.path] if selection.index is None and not selection.at_start else region.bounds)
                if selection.at_start:
                    self.canvas.create_line(x1+3, y1+3, x2-3, y1+3, fill=SELECT, width=4, tags="selection")
                else:
                    self.canvas.create_rectangle(x1+2, y1+2, x2-2, y2-2, outline=SELECT, width=SELECTION_WIDTH, tags="selection")
        if not self.exporting and self.selection.index is not None:
            last = self.selection.end_index if self.selection.end_index is not None else self.selection.index
            target = next((r for r in self.regions if r.selection == Selection(self.selection.path, last)), None)
            if target:
                x1, _, x2, y = target.bounds
                self.canvas.create_line(x1+4, y, x2-4, y, fill=SELECT, width=SELECTION_WIDTH, tags="insertion-marker")
        if self.monochrome:
            for item in self.canvas.find_all():
                # Monochrome applies to diagram content, not editor interaction cues.
                if {'selection','insertion-marker'}.intersection(self.canvas.gettags(item)):
                    continue
                if self.canvas.type(item) == "text":
                    self.canvas.itemconfigure(item, fill="#000000")
                elif self.canvas.type(item) == "line":
                    self.canvas.itemconfigure(item, fill="#000000")
                else:
                    self.canvas.itemconfigure(item, outline="#000000")
                    if self.canvas.itemcget(item, "fill"):
                        self.canvas.itemconfigure(item, fill="#ffffff")
        if self.zoom != 1.0:
            self.canvas.scale("all", 0, 0, self.zoom, self.zoom)
            for region in self.regions:
                region.bounds = tuple(value*self.zoom for value in region.bounds)
            self.insertion_regions = {path: tuple(v*self.zoom for v in bounds) for path, bounds in self.insertion_regions.items()}
        if not self.exporting:
            u=self.typography.units
            for cx,cy in self._try_info_points:
                cx,cy=cx*self.zoom,cy*self.zoom
                badge(self.canvas,cx,cy,radius=u(11),fill=HINT_BADGE,
                      outline=HINT_INK,group='try-info',exclamation=True)
                self._try_info_regions.append((cx-u(16),cy-u(16),cx+u(16),cy+u(16)))
        cat_bounds = self.canvas.bbox("cat-head") if cat_blocks else None
        bottom = max((top+height+16)*self.zoom, cat_bounds[3]+16 if cat_bounds else 0)
        self.canvas.configure(scrollregion=(0, 0, (width+32)*self.zoom, bottom))
        self._refresh_try_tip()
        if self.exporting or self.document["body"]:
            self.info_hint.show()
        else:
            self.info_hint.draw()

    def _hover_try(self,event):
        self._try_tip_at(event.x,event.y,event.x_root,event.y_root)

    def _try_tip_at(self,x,y,root_x,root_y):
        if self.exporting or not self.canvas.winfo_ismapped():
            self.try_tip.leave()
            return
        cx,cy=self.canvas.canvasx(x),self.canvas.canvasy(y)
        for key,(left,top,right,bottom) in enumerate(self._try_info_regions):
            if 0<=x<self.canvas.winfo_width() and 0<=y<self.canvas.winfo_height() and left<=cx<=right and top<=cy<=bottom:
                text=tr('Exception handling is an extension, not a standard Nassi–Shneiderman block (DIN 66261).')
                self.try_tip.request(text,root_x,root_y,key=key)
                return
        self.try_tip.leave()

    def _refresh_try_tip(self):
        if not self.canvas.winfo_ismapped():return
        x,y=self.canvas.winfo_pointerxy()
        try:owner=self.canvas.winfo_containing(x,y)
        except (tk.TclError,KeyError):owner=None
        if owner is self.canvas:
            self._try_tip_at(x-self.canvas.winfo_rootx(),y-self.canvas.winfo_rooty(),x,y)
        else:self.try_tip.leave()

    def _try_sections(self,node,width):
        return [(path,body,label,max(32,self._text_height(label,width-24)+16,self.typography.units(30)/self.zoom),
                 self._body_height(body,width-20)) for path,body,label in child_bodies(node)]

    def _paint_disabled(self,marker):
        if marker is None:return
        last=self.canvas.create_line(0,0,0,0,state='hidden')
        for item in range(marker+1,last):
            kind=self.canvas.type(item)
            if kind in ('text','line'):self.canvas.itemconfigure(item,fill=NSD_DISABLED_INK)
            elif kind in ('rectangle','polygon'):
                self.canvas.itemconfigure(item,outline=NSD_DISABLED_EDGE)
                if self.canvas.itemcget(item,'fill'):self.canvas.itemconfigure(item,fill=NSD_DISABLED_FILL)
        self.canvas.delete(marker,last)

    def _render_body(self, path, x, y, width, height, name):
        body = body_at(self.document, path)
        selection = Selection(path)
        self.canvas.create_rectangle(x, y, x+width, y+height, fill="#ffffff", outline=EDGE)
        self.regions.append(Region((x, y, x+width, y+height), selection))
        current_y = y
        for index, node in enumerate(body):
            marker = self.canvas.create_line(0,0,0,0,state='hidden') if not node.get('enabled', True) else None
            if node['kind']=='try':
                parts=self._try_sections(node,width)
                node_height=sum(header+size for _,_,_,header,size in parts)
                self.canvas.create_rectangle(x,current_y,x+width,current_y+node_height,fill=HEADER['try'],outline=EDGE)
                self.regions.append(Region((x,current_y,x+width,current_y+node_height),Selection(path,index)))
                if not self.exporting:
                    self._try_info_points.append((x+width-self.typography.units(20)/self.zoom,current_y+parts[0][3]/2))
                for relative,_,label,header,size in parts:
                    self._text(x+10,current_y+header/2,text=label,width=width-20,fill=INK,anchor='w')
                    current_y+=header
                    self._render_body(path+(index,)+relative,x+20,current_y,width-20,size,label)
                    current_y+=size
                self._paint_disabled(marker)
                continue
            head_height = self._head_height(node, width)
            head = Selection(path, index)
            node_height = head_height
            if node["kind"] in LOOP_KINDS:
                node_height += self._body_height(node["body"], width-20)
                # Kopf und linker Rand bilden eine einzige L-förmige Fläche.
                self.canvas.create_polygon(
                    x, current_y, x+width, current_y,
                    x+width, current_y+head_height, x+20, current_y+head_height,
                    x+20, current_y+node_height, x, current_y+node_height,
                    fill=HEADER["while"], outline=EDGE, tags="loop-shell",
                )
            else:
                if node["kind"] in IF_KINDS or node["kind"] == "switch":
                    node_height += max(self._body_height(b, w) for _, b, _, w in self._branch_layout(node, width))
                self.canvas.create_rectangle(x, current_y, x+width, current_y+head_height,
                                             fill=HEADER[node["kind"]], outline=EDGE)
            # Der ganze Baustein ist die Auswahlfläche. Körper und Kinder werden
            # später darübergelegt und behalten ihre eigenen Trefferbereiche.
            self.regions.append(Region((x, current_y, x+width, current_y+node_height), head))
            if node["kind"] in IF_KINDS or node["kind"] == "switch":
                layout = self._branch_layout(node, width)
                joint = x + (layout[0][3] if node["kind"] in IF_KINDS else sum(item[3] for item in layout[:-1]))
                band = self._case_label_height(node, width) if node["kind"] == "switch" else 0
                triangle_height = head_height-band
                self.canvas.create_line(x, current_y, joint, current_y+triangle_height,
                                        x+width, current_y, fill=EDGE)
                if band:
                    self.canvas.create_line(joint, current_y+triangle_height, joint, current_y+head_height, fill=EDGE)
                self._text((x+width/2+joint)/2, current_y+8, text=self._label(node),
                                        width=width*0.48, fill=INK, anchor="n")
                bx = x
                for column, (_, _, label, bw) in enumerate(layout):
                    self._text(bx+bw/2, current_y+head_height-(band/2 if band else 12),
                                            text=label, width=bw-12, fill=INK)
                    bx += bw
                    if node["kind"] == "switch" and column < len(layout)-2:
                        diagonal_y = current_y + triangle_height * (bx-x) / max(joint-x, 1)
                        self.canvas.create_line(bx, diagonal_y, bx, current_y+head_height, fill=EDGE)
            else:
                self._text(x+12, current_y+head_height/2, text=self._label(node),
                                        width=width-24, fill=INK, anchor="w")
            if node["kind"] == "call":
                self.canvas.create_line(x+8, current_y, x+8, current_y+head_height, fill=EDGE)
                self.canvas.create_line(x+width-8, current_y, x+width-8, current_y+head_height, fill=EDGE)
            current_y += head_height
            if node["kind"] in LOOP_KINDS:
                h = self._body_height(node["body"], width-20)
                self._render_body(path+(index, "body"), x+20, current_y, width-20, h, tr('Loop body'))
                current_y += h
            elif node["kind"] in IF_KINDS or node["kind"] == "switch":
                layout = self._branch_layout(node, width)
                h = max(self._body_height(b, w) for _, b, _, w in layout)
                bx = x
                for relative_path, _, label, bw in layout:
                    if relative_path is None:
                        self.canvas.create_rectangle(bx, current_y, bx+bw, current_y+h, fill="#ffffff", outline=EDGE)
                    else:
                        self._render_body(path+(index,)+relative_path, bx, current_y, bw, h, label)
                    bx += bw
                current_y += h
            self._paint_disabled(marker)
        # Auch gefüllte Körper bleiben unterhalb ihrer Bausteine anklickbar.
        self.insertion_regions[path] = (x, current_y, x+width, y+height)
        if self.exporting:
            return
        self._text(x+width/2, current_y+(y+height-current_y)/2,
                                text=tr('Insert block here') if path == ("body",) else tr('{body} · Insert block').format(body=name), width=width-16, fill=MUTED)
