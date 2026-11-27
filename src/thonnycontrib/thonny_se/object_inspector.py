# SPDX-FileCopyrightText: 2026 Sebastian Ladhoff
# SPDX-License-Identifier: GPL-3.0-only
# See LICENSE in the project root for the full license text.

"""Independent object-bank view; observes completed executions even while hidden."""
from .scrolling import ScrollArea
from .display_context import context_for
from .visual_metrics import Typography, preserve_scroll
from .i18n import tr
from uuid import uuid4
from functools import lru_cache
import time
import tkinter as tk
from tkinter import ttk, font, messagebox

from thonny import get_runner, get_workbench
from thonny.common import InlineCommand

from .ui_style import DARK_CANVAS, ui_color, uses_dark_ui, EDGE, INK, SELECT, SELECTION_FILL, OBJECT_FILL, OBJECT_EDGE, OBJECT_SHADOW, OBJECT_ACTIVE_FILL, OBJECT_FOCUS
from . import retina_icons
from .iconregistry import icon_path, menu_icon
from .diagram_preferences import OBJECT_METHODS, enabled
from .method_layout import minimum_method_width, wrap_method
from .object_bank import ObjectBankLayout, ObjectValueChanges


def member_label(name, class_names=()):
    """UML visibility notation; reverse Python name mangling for display only."""
    for owner in class_names:
        prefix = '_' + owner.lstrip('_') + '__'
        if name.startswith(prefix):
            return '- ' + name[len(prefix):]
    if name.startswith('__') and not name.endswith('__'):
        return '- ' + name.lstrip('_')
    if name.startswith('_'):
        return '# ' + name.lstrip('_')
    return '+ ' + name


class ObjectInspectorSE(ttk.Frame):
    def __init__(self, master):
        super().__init__(master)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.canvas = tk.Canvas(self, background='white', highlightthickness=0, width=340)
        self.canvas.grid(row=0, column=0, sticky='nsew')
        scrollbar = ttk.Scrollbar(self, orient='vertical', command=self.canvas.yview)
        scrollbar.grid(row=0, column=1, sticky='ns')
        horizontal = self.horizontal = ttk.Scrollbar(self, orient='horizontal', command=self.canvas.xview)
        horizontal.grid(row=1, column=0, sticky='ew')
        self.scrollbar = scrollbar
        self.canvas.configure(yscrollcommand=self._scrolled, xscrollcommand=self._xscrolled)
        from .tooltips import CanvasToolTip
        self.warning_tip = CanvasToolTip(self.canvas)
        self.canvas.bind('<Motion>', self._warning_hover, add=True)
        self.typography = Typography(self)
        self.normal = self.typography['body']
        self.bold = self.typography['object_heading']
        self._selection_restore = {}
        self._action_bindings = []
        self._click_actions = {}
        self._toggle_regions = []
        self.objects = []
        self.bank_layout = ObjectBankLayout()
        self.card_bounds = {}
        self.node_regions = []
        self.selected_id = None
        self.focus_ids = set()
        self._focus_job = None
        self.nested_focus = False
        self.value_changes = ObjectValueChanges()
        self._glows = []
        self._pulse_job = None
        self.bind('<Destroy>', self._destroy_feedback, add=True)
        self._card_drag = None
        self._header_tags = set()
        self.canvas.bind('<Button-1>', self._press_card)
        self.canvas.bind('<B1-Motion>', self._drag_card)
        self.canvas.bind('<ButtonRelease-1>', self._drop_card)
        self.canvas.bind('<Escape>', self._escape_selection)
        for sequence in ('<Button-3>', '<Button-2>', '<Control-Button-1>'):
            self.canvas.bind(sequence, self._background_menu)
        self.expanded = set()
        self.item_limits = {}
        self.canvas.bind('<Configure>', lambda e: self.draw())
        self.bind('<<ThemeChanged>>', lambda event: self.after_idle(self._redraw_mapped))
        self.canvas.bind('<Map>', lambda e: self.canvas.after_idle(self._redraw_mapped))
        self.scrolling = ScrollArea(self.canvas, self)
        self.render(get_workbench()._thonny_se_objects.objects)
        context_for(self).subscribe(self,self._display_changed)

    def _display_changed(self, state):
        self.typography.refresh()
        if self.winfo_ismapped():preserve_scroll(self.canvas,self.draw)

    def _scrolled(self, *fractions):
        self.scrollbar.set(*fractions)
        self._draw_warning()

    def _xscrolled(self, *fractions):
        self.horizontal.set(*fractions)
        self._draw_warning()

    def _warning_text(self):
        state = get_workbench()._thonny_se_objects.session.state
        return (tr('The Python interpreter and the diagram contain different program versions. The objects belong to the executed program.')
                + '\n' + tr('Run the diagram to load its current version.')) if state.stale else ''

    def _warning_hover(self, event):
        tags = set(self.canvas.gettags('current'))
        text = (self._warning_text() if 'stale-warning' in tags else
                tr('Drag the card to reorder. Right-click for options.') if tags.intersection(self._header_tags) else '')
        self.warning_tip.request(text, event.x_root, event.y_root)

    def _draw_warning(self):
        from .ui_style import HINT_FILL, HINT_BORDER, HINT_BADGE, HINT_INK, HINT_TEXT
        canvas = self.canvas
        canvas.delete('stale-warning')
        text = self._warning_text()
        if not text or not hasattr(self, 'normal'):
            return 0
        width = max(100, canvas.winfo_width())
        left, top = canvas.canvasx(8), canvas.canvasy(8)
        compact = width < 300
        text, action = text.split('\n', 1)
        if compact:
            text = tr('Python and the diagram contain different program versions.')
        narrow = width < 230
        inset = 12 if narrow else 35 if compact else 45
        label = canvas.create_text(left+inset,top+(42 if narrow else 11),text=text,font=self.normal,fill=ui_color(HINT_TEXT),
            width=max(40,width-inset-28),anchor='nw',tags='stale-warning')
        bounds = canvas.bbox(label)
        self.warning_run_image = get_workbench().get_image('run-current-script')
        action_y = bounds[3]+10
        canvas.create_image(left+inset, action_y+2, image=self.warning_run_image,
                            anchor='nw', tags='stale-warning')
        action_label = canvas.create_text(left+inset+24, action_y, text=action,
            font=self.normal,fill=ui_color(HINT_TEXT),width=max(40,width-inset-52),
            anchor='nw',tags='stale-warning')
        bottom = max(top+45,canvas.bbox(action_label)[3]+12,
                     action_y+self.warning_run_image.height()+12)
        shape = canvas.create_polygon(left,top+10,left,top,left+10,top,left+width-26,top,
            left+width-16,top,left+width-16,top+10,left+width-16,bottom-10,left+width-16,bottom,
            left+width-26,bottom,left+10,bottom,left,bottom,left,bottom-10,
            smooth=True,fill=ui_color(HINT_FILL),stipple='' if uses_dark_ui() else 'gray75',outline=ui_color(HINT_BORDER),tags='stale-warning')
        canvas.tag_lower(shape,label)
        x,y=left+(17 if compact else 23),top+22 if compact else (top+bottom)/2
        canvas.create_oval(x-10,y-10,x+10,y+10,fill=ui_color(HINT_BADGE),outline=ui_color(HINT_INK),tags='stale-warning')
        canvas.create_line(x+2,y-6,x,y+1,fill=ui_color(HINT_INK),width=3,capstyle='round',tags='stale-warning')
        canvas.create_oval(x-2,y+4,x+1,y+7,fill=ui_color(HINT_INK),outline='',tags='stale-warning')
        canvas.tag_raise('stale-warning')
        return bottom-top+10

    def _redraw_mapped(self):
        # Switching notebook tabs need not change size or emit Configure.
        if self.canvas.winfo_exists() and self.canvas.winfo_ismapped():
            self.draw()

    def render(self, objects):
        ids = self.value_changes.observe(objects,time.monotonic())
        if self.selected_id not in ids:
            self.selected_id = None
            self.nested_focus = False
            self.focus_ids.clear()
        self.focus_ids.intersection_update(ids)
        self.objects = self.bank_layout.sync(objects)
        if self._card_drag and self._card_drag['id'] not in self.bank_layout.order:
            self._cancel_card_drag()
        self.draw()
        self._queue_container_focus()

    def _bind_action(self, tag, sequence, callback):
        if sequence == '<Button-1>':
            # Defer clicks until release: every card area can start a drag,
            # including a method button, without accidentally calling it.
            self._click_actions[tag] = callback
            return
        funcid = self.canvas.tag_bind(tag, sequence, callback)
        self._action_bindings.append((tag, sequence, funcid))

    def _bind_toggle(self, tag, box, callback):
        self._bind_action(tag,'<Button-1>',callback)
        # Borders/highlights must not steal clicks from the arrow's target.
        self._toggle_regions.append((box,callback))

    def draw(self):
        canvas = self.canvas
        background = DARK_CANVAS if uses_dark_ui() else "white"
        canvas.configure(background=self._mix(background,'black',.84) if self.nested_focus else background)
        # Deleting items does not delete Tkinter's registered Tcl callbacks.
        for tag, sequence, funcid in self._action_bindings:
            canvas.tag_unbind(tag, sequence, funcid)
        self._action_bindings.clear()
        self._click_actions.clear()
        self._toggle_regions = []
        canvas.delete('all')
        self._selection_restore.clear()
        self.card_bounds = {}
        self.node_regions = []
        self._glows = []
        self._header_tags = set()
        # Identical instances share signatures. Cache only within this draw,
        # so changed fonts, widths and themes cannot leave stale measurements.
        measure = lru_cache(maxsize=2048)(self.normal.measure)
        min_width = lru_cache(maxsize=256)(lambda name, signature:
            minimum_method_width(name, signature, measure))
        wrapped = lru_cache(maxsize=256)(lambda name, signature, width:
            wrap_method(name, signature, measure, width))
        show_all = enabled(OBJECT_METHODS)
        # Keep names, complete parameters and the return type indivisible.
        minimum = self.typography.units(300)
        if show_all:
            minimum = max(minimum, max((min_width(
                member_label(name, obj.get('class_names', [obj['class_name']])), signature)+100
                for obj in self.objects if obj['id'] not in self.bank_layout.collapsed
                for name, signature in obj.get('methods', {}).items()), default=0))
        width = max(minimum, canvas.winfo_width())
        left, right, top = 12, width - 15, 12
        if self._warning_text():
            top += self._draw_warning()
        text_width = max(75, right - left - 28)

        def rounded(x0, y0, x1, y1, *, fill, outline='', tags=(), line_width=1):
            radius = min(12, (y1-y0)/3)
            return canvas.create_polygon(
                x0+radius,y0, x1-radius,y0, x1,y0, x1,y0+radius,
                x1,y1-radius, x1,y1, x1-radius,y1, x0+radius,y1,
                x0,y1, x0,y1-radius, x0,y0+radius, x0,y0,
                smooth=True, splinesteps=24, fill=fill, outline=outline, width=line_width, tags=tags)

        counter = [0]

        def reference(node, label, left, top, right=width-15, *, root=False, value_key=None, background=OBJECT_FILL):
            counter[0] += 1
            tag = 'reference_'+str(counter[0])
            cycle = node.get('cycle', False)
            opened = node.get('expanded', False)
            suffix = node['class_name']
            if node.get('reference') and not node.get('names'):
                suffix += ' · '+tr('Object {number}').format(number=node['reference'])
            if cycle:
                suffix += ' · '+tr('Back reference')
            header_tag = tag+'_header'
            item = canvas.create_text(left+30, top+5, text=label+' : '+suffix,
                anchor='nw', width=max(20,right-left-38), font=self.normal,fill=ui_color(INK),
                tags=(tag, header_tag) if root else (tag,))
            bottom = canvas.bbox(item)[3]+8
            self.node_regions.append(dict(id=node['id'],box=(left,top,right,bottom),nested=not root,reference=True))
            def finish_reference(value):
                canvas.addtag_withtag('node:'+str(node['id']),tag)
                if node.get('kind')=='container':
                    self.node_regions.append(dict(id=node['id'],box=(left,top,right,value),nested=not root,reference=False))
                return value
            hit = canvas.create_rectangle(left,top,right,bottom,fill=ui_color(background),outline='',tags=(tag,))
            canvas.tag_lower(hit,item)
            if value_key is not None and self.value_changes.strength(value_key,time.monotonic())>0:
                glow = rounded(left+24,top+1,right-2,bottom-1,fill=ui_color(OBJECT_ACTIVE_FILL),
                               outline=ui_color(OBJECT_FOCUS),tags=(tag,'value-glow'))
                canvas.tag_lower(glow,item)
                self._glows.append((glow,value_key,node['id'],background))
            if cycle:
                canvas.create_text(left+9,top+5,text='↩',font=self.normal,fill=ui_color(SELECT),anchor='n',tags=(tag,))
                return finish_reference(bottom)
            toggle_tag = tag+'_toggle'
            canvas.create_rectangle(left,top,left+24,bottom,fill=ui_color(background),outline='',tags=(tag,toggle_tag))
            self._expand_arrow(left+12,top+5+self.normal.metrics('linespace')/2,opened,(tag,toggle_tag))
            if root:
                self._bind_header(node, header_tag)
                self._bind_context(node, tag)
                self._bind_toggle(toggle_tag,(left,top,left+24,bottom),lambda e,n=node:self.toggle_reference(n))
            else:
                self._bind_toggle(toggle_tag,(left,top,left+24,bottom),lambda e,n=node:self.toggle_reference(n))
            if not opened:
                return finish_reference(bottom)
            child_left = left+22
            y=bottom
            if node.get('limited'):
                return finish_reference(plain(tr('Further contents are not displayed here.'),child_left,y,right,tags=(tag,),background=background))
            if node['kind'] == 'object':
                return finish_reference(object_card(node,child_left,y,label,right-6)+5)
            for entry in node.get('items', []):
                content=entry['node'];entry_label='['+entry['label']+']'
                if content['kind']=='scalar':
                    y=plain(entry_label+' = '+content['value'],child_left,y,right,tags=(tag,),
                            value_key=(node['id'],tuple(content['path']['steps'][-1])),owner=node['id'],background=background)
                else:
                    y=reference(content,entry_label,child_left,y,right,
                                value_key=(node['id'],tuple(content['path']['steps'][-1])),background=background)
            if not node.get('items'):
                y=plain(tr('Empty'),child_left,y,right,tags=(tag,))
            if node.get('remaining'):
                more_tag=tag+'_more'
                item=canvas.create_text(child_left+4,y+4,
                    text=tr('Show {count} more elements').format(count=min(100,node['remaining'])),
                    anchor='nw',font=self.normal,fill=ui_color(SELECT),tags=(tag,more_tag),width=max(20,right-child_left-12))
                self._bind_action(more_tag,'<Button-1>',lambda e,n=node:self.show_more(n))
                y=canvas.bbox(item)[3]+9
            canvas.create_line(left+12,bottom,left+12,y-3,fill=ui_color(OBJECT_EDGE),tags=(tag,))
            return finish_reference(y+5)

        def plain(value,left,y,right=width-15,*,tags=(),value_key=None,owner=None,background=OBJECT_FILL):
            item=canvas.create_text(left+4,y+4,text=value,font=self.normal,fill=ui_color(INK),
                                   anchor='nw',width=max(20,right-left-12),tags=tags)
            bounds = canvas.bbox(item)
            if value_key is not None and self.value_changes.strength(value_key,time.monotonic())>0:
                glow = rounded(left,bounds[1]-3,right,bounds[3]+3,fill=ui_color(OBJECT_ACTIVE_FILL),
                               outline=ui_color(OBJECT_FOCUS),tags=(*tags,'value-glow'))
                canvas.tag_lower(glow,item)
                self._glows.append((glow,value_key,owner,background))
            return bounds[3]+9

        def card_bottom(tag, left, top, right, y, obj, root):
            bottom = y+6
            shadow = rounded(left+2, top+3, right+2, bottom+3,
                fill=ui_color(OBJECT_SHADOW), tags=(tag, 'object_shadow'))
            shape = rounded(left, top, right, bottom, fill=ui_color(OBJECT_FILL),
                outline=ui_color(OBJECT_EDGE), tags=(tag, 'object_card'))
            canvas.tag_lower(shape)
            canvas.tag_lower(shadow)
            canvas.addtag_withtag('node:'+str(obj['id']),tag)
            self.node_regions.append(dict(id=obj['id'],box=(left,top,right,bottom),nested=not root,reference=False))
            return bottom+18

        def object_card(obj,left,top,label=None,right=width-15, *, root=False):
            counter[0] += 1
            index=counter[0]
            text_width=max(20,right-left-28)
            tag = f'object_{index}'
            header_tag = tag+'_header'
            y = top + 14
            def text(value, *, heading=False, value_key=None):
                nonlocal y
                offset = 34 if root and heading else 14
                item = canvas.create_text(left+offset, y, anchor='nw', width=text_width-(offset-14),
                    text=value, font=self.bold if heading else self.normal, fill=ui_color(INK),
                    tags=(tag, header_tag) if root and heading else (tag,))
                bounds = canvas.bbox(item)
                if value_key is not None and self.value_changes.strength(value_key,time.monotonic())>0:
                    glow = rounded(left+10,bounds[1]-3,right-10,bounds[3]+3,
                        fill=ui_color(OBJECT_ACTIVE_FILL),outline=ui_color(OBJECT_FOCUS),tags=(tag,'value-glow'))
                    canvas.tag_lower(glow,item)
                    self._glows.append((glow,value_key,obj['id'],OBJECT_FILL))
                y = bounds[3] + 8
            text(f"{label or ', '.join(obj['names'])} : {obj['class_name']}", heading=True)
            if root:
                self._bind_header(obj, header_tag)
                self._bind_context(obj, tag)
                toggle_tag = tag+'_toggle'
                cx, cy = left+21, top+14+self.normal.metrics('linespace')/2
                collapsed = obj['id'] in self.bank_layout.collapsed
                canvas.create_rectangle(left+6,top+7,left+32,y,fill=ui_color(OBJECT_FILL),outline='',tags=(tag,toggle_tag))
                self._expand_arrow(cx,cy,not collapsed,(tag,toggle_tag))
                self._bind_toggle(toggle_tag,(left+6,top+7,left+32,y),lambda e,o=obj:self.toggle_card(o))
                if collapsed:
                    return card_bottom(tag,left,top,right,y,obj,root)
            canvas.create_line(left+14, y, right-14, y, fill=ui_color(OBJECT_EDGE), tags=(tag,))
            y += 10
            owners = obj.get('class_names', [obj['class_name']])
            for name, value in obj['attributes'].items():
                nested = obj.get('references', {}).get(name)
                if nested is None:
                    text(f'{member_label(name, owners)} = {value}',value_key=(obj['id'],name))
                else:
                    y=reference(nested,member_label(name,owners),left+10,y,right-10,value_key=(obj['id'],name))
            if not obj['attributes']:
                text(tr('No stored attributes'))
            if obj['methods']:
                canvas.create_line(left+14, y, right-14, y, fill=ui_color(OBJECT_EDGE), tags=(tag,))
                y += 10
            if obj['methods'] and show_all:
                y += 4
                for method_index, (name, signature) in enumerate(obj['methods'].items()):
                    action_tag = f'{tag}_method_{method_index}'
                    row_top = y
                    label = member_label(name, owners)
                    item = canvas.create_text(left+44, y+9, anchor='nw',
                        text=wrapped(label, signature, max(45, text_width-42)),
                        font=self.normal, fill=ui_color(SELECT), tags=(tag, action_tag, 'object_method'))
                    row_bottom = canvas.bbox(item)[3]+9
                    button = rounded(left+10, row_top, right-10, row_bottom,
                        fill=ui_color('white'), outline=ui_color('#b9cfe8'), tags=(tag, action_tag, 'object_method_button'))
                    canvas.tag_lower(button, item)
                    if retina_icons.enabled(canvas):
                        canvas.create_text(left+27, (row_top+row_bottom)/2,
                            text=retina_icons.glyph('class.instantiate'),
                            font=retina_icons.font_for(canvas, self.normal), fill=ui_color(SELECT),
                            tags=(tag, action_tag, 'object_method'))
                    else:
                        canvas.create_image(left+27, (row_top+row_bottom)/2,
                            image=get_workbench().get_image(icon_path('class.instantiate', size=16)),
                            tags=(tag, action_tag, 'object_method'))
                    self._bind_action(action_tag, '<Enter>', lambda e, b=button, owner=obj['id']:
                        self._method_hover(b,owner,True))
                    self._bind_action(action_tag, '<Leave>', lambda e, b=button, owner=obj['id']:
                        self._method_hover(b,owner,False))
                    self._bind_action(action_tag, '<Button-1>', lambda e, o=obj, n=name: self.call_method(o, n))
                    y = row_bottom + 7
            elif obj['methods']:
                y += 4
                action_tag = f'{tag}_methods'
                row_bottom = y + max(34, self.normal.metrics('linespace')+18)
                button = rounded(left+10, y, right-10, row_bottom,
                    fill=ui_color('white'), outline=ui_color('#b9cfe8'), tags=(tag, action_tag, 'object_methods_dropdown'))
                canvas.create_text(left+23, (y+row_bottom)/2, anchor='w', text=tr('Methods …'),
                    font=self.normal, fill=ui_color(SELECT), tags=(tag, action_tag))
                arrow_x, arrow_y = right-27, (y+row_bottom)/2
                canvas.create_line(arrow_x-4, arrow_y-2, arrow_x, arrow_y+2, arrow_x+4, arrow_y-2,
                    fill=ui_color(SELECT), width=2, capstyle='round', joinstyle='round', tags=(tag, action_tag))
                self._bind_action(action_tag, '<Enter>', lambda e, b=button, owner=obj['id']:
                    self._method_hover(b,owner,True))
                self._bind_action(action_tag, '<Leave>', lambda e, b=button, owner=obj['id']:
                    self._method_hover(b,owner,False))
                self._bind_action(action_tag, '<Button-1>', lambda e, o=obj: self.open_methods(o, e))
                y = row_bottom+7
            return card_bottom(tag,left,top,right,y,obj,root)
        for obj in self.objects:
            card_top = top
            if obj.get('kind') == 'container':
                top=reference(obj,', '.join(obj['names']),left,top,root=True,background=background)+12
            else:
                top=object_card(obj,left,top,root=True)
            self.card_bounds[obj['id']] = (left,card_top,right,top-(12 if obj.get('kind')=='container' else 18))
        self._apply_object_selection()
        self._paint_value_changes()
        bounds = canvas.bbox('all')
        content_width = max(width, bounds[2]+12 if bounds else width)
        canvas.configure(scrollregion=(0, 0, content_width, max(top, canvas.winfo_height())))
        self._draw_warning()
        if content_width > canvas.winfo_width()+1:
            self.horizontal.grid()
        else:
            self.horizontal.grid_remove()
            canvas.xview_moveto(0)

    def _expand_arrow(self, x, y, opened, tags):
        # The same chevron rotated 90 degrees, for cards and all references.
        x, y = round(x), round(y)
        points = ((x-5,y-3,x,y+3,x+5,y-3) if opened else
                  (x-3,y-5,x+3,y,x-3,y+5))
        return self.canvas.create_line(*points,fill=ui_color(SELECT),width=2,
                                       capstyle='round',joinstyle='round',tags=tags)

    def _bind_header(self, obj, tag):
        self._header_tags.add(tag)
        # A heading click selects; the adjacent arrow owns collapse/expand.

    def _bind_context(self, obj, tag):
        for sequence in ('<Button-3>', '<Button-2>', '<Control-Button-1>'):
            self._bind_action(tag, sequence, lambda event:self._card_menu(obj,event))

    def toggle_card(self, obj):
        if obj.get('kind') == 'container':
            return self.toggle_reference(obj)
        key = obj['id']
        if key in self.bank_layout.collapsed:
            self.bank_layout.collapsed.remove(key)
        else:
            self.bank_layout.collapsed.add(key)
        preserve_scroll(self.canvas,self.draw)
        return 'break'

    def move_card(self, key, index):
        self.bank_layout.move(key,index)
        self.objects = self.bank_layout.sync(self.objects)
        preserve_scroll(self.canvas,self.draw)

    def _background_menu(self, event):
        x, y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
        # Cards already own their context menu through their canvas tags.
        if any(left <= x <= right and top <= y <= bottom
               for left, top, right, bottom in self.card_bounds.values()):
            return 'break'
        return self._card_menu(None, event)

    def _add_instantiation_menu(self, menu):
        session = get_workbench()._thonny_se_objects.session
        submenu = tk.Menu(menu, tearoff=False)
        editor = session.state.owner
        cards = editor.document['classes'] if editor is not None and editor.winfo_exists() else []
        for card in sorted(cards, key=lambda card: card['name'].casefold()):
            if not session.classes.get(card['id'], {}).get('instantiable', False):
                continue
            ready = session.pending is None and session.dialog is None and session.can_instantiate(editor, card['id'])
            submenu.add_command(label=card['name'], state='normal' if ready else 'disabled',
                                 command=lambda cid=card['id']: editor.instantiate_class(cid))
        menu.add_cascade(label=tr('Instantiate object'), menu=submenu,
                         image=menu_icon(get_workbench(),'object.instantiate'), compound='left',
                         state='normal' if submenu.index('end') is not None else 'disabled')
        retina_icons.decorate_menu(submenu)

    def _card_menu(self, obj, event):
        if hasattr(self, 'card_menu'):
            self.card_menu.destroy()
        menu = self.card_menu = tk.Menu(self, tearoff=False)
        self._add_instantiation_menu(menu)
        if obj is not None:
            menu.add_separator()
            collapsed = (not obj.get('expanded') if obj.get('kind')=='container' else
                         obj['id'] in self.bank_layout.collapsed)
            menu.add_command(label=tr('Expand object') if collapsed else tr('Collapse object'),
                             command=lambda:self.toggle_card(obj))
            index = self.bank_layout.order.index(obj['id'])
            menu.add_separator()
            menu.add_command(label=tr('Move up'), state='normal' if index else 'disabled',
                             command=lambda:self.move_card(obj['id'],index-1))
            menu.add_command(label=tr('Move down'),
                state='normal' if index<len(self.bank_layout.order)-1 else 'disabled',
                command=lambda:self.move_card(obj['id'],index+1))
            menu.add_separator()
            controller = get_workbench()._thonny_se_objects
            menu.add_command(label=tr('Remove object'), image=menu_icon(get_workbench(),'edit.delete'),
                compound='left', state='normal' if controller.session.available() and not controller.remove_request else 'disabled',
                command=lambda:controller.remove_object(obj))
        retina_icons.decorate_menu(menu)
        try:
            menu.tk_popup(event.x_root,event.y_root)
        finally:
            menu.grab_release()
        return 'break'

    def _press_card(self, event):
        tags = self.canvas.gettags('current')
        if 'stale-warning' in tags:
            return
        x, y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
        key = next((key for key,box in self.card_bounds.items()
                    if box[0]<=x<=box[2] and box[1]<=y<=box[3]), None)
        if key is None:
            self.select_object(None)
            return
        node = min((region for region in self.node_regions
                    if region['box'][0]<=x<=region['box'][2] and region['box'][1]<=y<=region['box'][3]),
                   key=lambda region:(region['box'][2]-region['box'][0])*(region['box'][3]-region['box'][1]),default=None)
        action = next((callback for box,callback in reversed(self._toggle_regions)
                       if box[0]<=x<=box[2] and box[1]<=y<=box[3]),None)
        if action is None:
            action = next((self._click_actions[tag] for tag in reversed(tags)
                           if tag in self._click_actions),None)
        self._card_drag = dict(id=key,y=event.y_root,last_y=event.y_root,
                               direction=0,active=False,index=None,click=action,
                               selected=node['id'] if node else key,nested=node['nested'] if node else False)
        self.canvas.focus_set()
        return 'break'

    def _drag_card(self, event):
        drag = self._card_drag
        if drag is None:
            return
        movement = event.y_root-drag['last_y']
        if movement:
            drag['direction'] = -1 if movement<0 else 1
        drag['last_y'] = event.y_root
        if not drag['active']:
            if abs(event.y_root-drag['y'])<7:
                return 'break'
            self.canvas.grab_set()
            drag['active'] = True
        if event.y<24:
            self.canvas.yview_scroll(-1,'units')
        elif event.y>self.canvas.winfo_height()-24:
            self.canvas.yview_scroll(1,'units')
        keys = [key for key in self.bank_layout.order if key in self.card_bounds]
        if not keys:
            return 'break'
        y = self.canvas.canvasy(event.y)
        target = min(keys, key=lambda key:max(self.card_bounds[key][1]-y,0,
                                              y-self.card_bounds[key][3]))
        if target == drag['id']:
            drag['index'] = keys.index(target)
        else:
            remaining = [key for key in keys if key!=drag['id']]
            drag['index'] = remaining.index(target)+(1 if drag['direction']>0 else 0)
        box = self.card_bounds[target]
        line_y = box[1]-6 if drag['direction']<0 else box[3]+6
        self.canvas.delete('object-reorder-preview')
        self.canvas.create_line(box[0]+4,line_y,box[2]-4,line_y,
                                fill=ui_color(SELECT),width=2,tags='object-reorder-preview')
        return 'break'

    def _drop_card(self, event):
        drag = self._card_drag
        self._cancel_card_drag()
        if drag and drag['active'] and drag['index'] is not None:
            self.move_card(drag['id'],drag['index'])
        elif drag:
            self.select_object(drag['selected'],drag['nested'])
            if drag['click'] is not None:
                drag['click'](event)
        return 'break' if drag else None

    def _cancel_card_drag(self, event=None):
        if self.canvas.grab_current() is self.canvas:
            self.canvas.grab_release()
        self._card_drag = None
        self.canvas.delete('object-reorder-preview')
        self.canvas.configure(cursor='')
        return 'break'

    def _selected_node(self):
        def find(nodes):
            for node in nodes:
                if node['id']==self.selected_id:
                    return node
                nested = list(node.get('references',{}).values())
                nested.extend(entry['node'] for entry in node.get('items',()) if entry['node']['kind']!='scalar')
                result = find(nested)
                if result is not None:
                    return result
            return None
        return find(self.objects)

    def select_object(self, key, nested=False):
        same = key==self.selected_id
        self.selected_id = key
        if not same or key is None:
            self.focus_ids = {key} if key is not None else set()
        node = self._selected_node()
        container = node is not None and node.get('kind')=='container'
        self.nested_focus = bool(key is not None and (nested or container))
        self._apply_object_selection()
        self._paint_value_changes()
        self._queue_container_focus()

    def _queue_container_focus(self):
        if self._focus_job is None and self.selected_id is not None:
            self._focus_job = self.after_idle(self._refresh_container_focus)

    def _refresh_container_focus(self):
        self._focus_job = None
        node = self._selected_node()
        if node is not None and node.get('kind')=='container':
            candidates = {region['id'] for region in self.node_regions if region['id']!=node['id']}
            get_workbench()._thonny_se_objects.request_container_focus(self,node,candidates)

    def _escape_selection(self, event=None):
        self._cancel_card_drag()
        self.select_object(None)
        return 'break'

    def _mix(self, foreground, background, amount):
        a = self.canvas.winfo_rgb(foreground)
        b = self.canvas.winfo_rgb(background)
        return '#'+''.join(f'{round((x*amount+y*(1-amount))/257):02x}' for x,y in zip(a,b))

    def _dim_color(self, color, key):
        return (self._mix(color,'black',.84)
                if self.nested_focus and key not in self.focus_ids else color)

    def _method_hover(self, item, owner, active):
        fill = ui_color(SELECTION_FILL if active else 'white')
        edge = ui_color(SELECT if active else '#b9cfe8')
        self.canvas.itemconfigure(item,fill=self._dim_color(fill,owner),outline=self._dim_color(edge,owner))

    def _selection_style(self, item, **options):
        original = self._selection_restore.setdefault(item, {})
        for option in options:
            if option not in original:
                original[option] = self.canvas.itemcget(item, option)
        self.canvas.itemconfigure(item, **options)

    def _apply_object_selection(self):
        canvas = self.canvas
        canvas.delete('object-selection')
        # Restore only what the previous selection changed. Geometry, item ids
        # and mouse bindings stay intact; selection never rebuilds the cards.
        for item, options in self._selection_restore.items():
            canvas.itemconfigure(item, **options)
        self._selection_restore.clear()
        background = DARK_CANVAS if uses_dark_ui() else 'white'
        canvas.configure(background=self._mix(background, 'black', .84) if self.nested_focus else background)
        if self.nested_focus:
            for item in canvas.find_all():
                tags = canvas.gettags(item)
                owner = next((int(tag[5:]) for tag in tags if tag.startswith('node:')),None)
                if owner is None or owner in self.focus_ids:
                    continue
                kind = canvas.type(item)
                options = ('fill','outline') if kind in ('rectangle','polygon','oval') else ('fill',) if kind in ('line','text') else ()
                for option in options:
                    color = canvas.itemcget(item,option)
                    if color:self._selection_style(item,**{option:self._dim_color(color,owner)})
        if self.selected_id is None:
            return
        for item in canvas.find_withtag('object_card'):
            if any('node:'+str(key) in canvas.gettags(item) for key in self.focus_ids):
                self._selection_style(item,outline=ui_color(SELECT),width=2)
        for item in canvas.find_withtag('object_shadow'):
            if any('node:'+str(key) in canvas.gettags(item) for key in self.focus_ids):
                self._selection_style(item,fill=self._mix(ui_color(SELECT),ui_color(OBJECT_SHADOW),.28))
        for region in self.node_regions:
            if region['id'] in self.focus_ids and region['reference']:
                left,top,right,bottom = region['box']
                canvas.create_rectangle(left,top,right,bottom,fill='',outline=ui_color(SELECT),width=2,
                    tags=('object-selection','node:'+str(self.selected_id)))

    def _paint_value_changes(self):
        now = time.monotonic()
        active = []
        for item,key,owner,background in self._glows:
            strength = self.value_changes.strength(key,now)
            if strength<=0:
                self.canvas.delete(item)
                continue
            fill = self._mix(ui_color(OBJECT_ACTIVE_FILL),ui_color(background),strength)
            edge = self._mix(ui_color(OBJECT_FOCUS),ui_color(background),strength)
            self.canvas.itemconfigure(item,fill=self._dim_color(fill,owner),outline=self._dim_color(edge,owner))
            active.append((item,key,owner,background))
        self._glows = active
        if active and self._pulse_job is None:
            self._pulse_job = self.after(40,self._pulse_values)

    def _pulse_values(self):
        self._pulse_job = None
        self._paint_value_changes()

    def _destroy_feedback(self, event):
        if event.widget is self:
            for name in ('_pulse_job','_focus_job'):
                job = getattr(self,name)
                if job is not None:
                    self.after_cancel(job)
                    setattr(self,name,None)

    def show_more(self, node):
        self.item_limits[node['expansion_key']] = len(node.get('items', []))+100
        get_workbench()._thonny_se_objects.completed(None)
        return 'break'

    def toggle_reference(self, node):
        key = node.get('expansion_key', node['id'])
        if key in self.expanded:
            self.expanded.remove(key)
        else:
            self.expanded.add(key)
        get_workbench()._thonny_se_objects.completed(None)
        return 'break'

    def open_methods(self, obj, event):
        if hasattr(self, 'method_menu'):
            self.method_menu.destroy()
        menu = self.method_menu = tk.Menu(self, tearoff=False)
        workbench = get_workbench()
        ready = workbench._thonny_se_objects.methods.available()
        for name, signature in obj['methods'].items():
            menu.add_command(label=member_label(name, obj.get('class_names', [obj['class_name']]))+signature,
                image=menu_icon(workbench, 'class.instantiate'), compound='left',
                state='normal' if ready else 'disabled', command=lambda n=name: self.call_method(obj, n))
        retina_icons.decorate_menu(menu)
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()
        return 'break'

    def call_method(self, obj, method):
        get_workbench()._thonny_se_objects.methods.open(self, obj, method)


class ObjectController:
    def __init__(self, workbench):
        self.workbench = workbench
        self.objects = []
        self.known_ids = set()
        self.remove_request = None
        self.members_request = None
        self.session_hint = False
        self.session_hint_seen = False
        self.session_hint_diagram = None
        from .instantiation import ObjectSession
        self.session = ObjectSession(self)
        from .method_call import MethodCallController
        self.methods = MethodCallController(self)
        workbench.bind('ToplevelResponse', self.completed, True)
        workbench.bind('thonny_se_objects_response', self.received, True)
        workbench.bind('thonny_se_remove_object_response', self.removed_object, True)
        workbench.bind('thonny_se_container_members_response', self.container_members, True)
        workbench.bind('BackendRestart', self.restart, True)

    def completed(self, event):
        runner = get_runner()
        # This first implementation targets local CPython, not MicroPython.
        if runner and runner.is_waiting_toplevel_command():
            proxy = runner.get_backend_proxy()
            from thonny.plugins.cpython_frontend.cp_front import LocalCPythonProxy
            if isinstance(proxy, LocalCPythonProxy):
                view=self.existing_view()
                runner.send_command(InlineCommand('thonny_se_objects',
                    expanded=list(view.expanded) if view is not None else [],
                    item_limits=view.item_limits if view is not None else {},
                    representation_error=tr('<Representation failed>')))

    def received(self, event):
        if 'objects' not in event:
            return
        objects = event['objects']
        ids = {obj['id'] for obj in objects}
        added = ids - self.known_ids
        self.known_ids = ids
        self.objects = objects
        if added:
            self.workbench.show_view('ObjectInspectorSE', set_focus=False)
        view = self.existing_view()
        if view is not None:
            view.render(objects)
        self.refresh_session_hint()

    def request_container_focus(self, view, node, candidates):
        if not self.session.available():
            return
        request = uuid4().hex
        self.members_request = request,view,node['id']
        get_runner().send_command(InlineCommand('thonny_se_container_members',request_id=request,
            path=node['path'],object_id=node['id'],candidates=list(candidates)))

    def container_members(self, response):
        if not self.members_request or response.get('request_id')!=self.members_request[0]:
            return
        _,view,key = self.members_request
        self.members_request = None
        if view.winfo_exists() and view.selected_id==key:
            view.focus_ids = {key,*response.get('member_ids',())}
            view._apply_object_selection()
            view._paint_value_changes()

    def remove_object(self, obj):
        if self.remove_request or not self.session.available():
            return
        self.remove_request = uuid4().hex
        view = self.existing_view()
        get_runner().send_command(InlineCommand('thonny_se_remove_object',
            request_id=self.remove_request, names=list(obj['names']), object_id=obj['id'],
            expanded=list(view.expanded) if view else [], item_limits=view.item_limits if view else {},
            representation_error=tr('<Representation failed>')))

    def removed_object(self, response):
        if response.get('request_id') != self.remove_request:
            return
        self.remove_request = None
        self.received(response)
        if 'error' in response:
            messagebox.showinfo(tr('Remove object'),
                tr('This object has changed. Please select it again.'),
                parent=self.existing_view() or self.workbench)

    def refresh_session_hint(self):
        diagram = self.session_hint_diagram
        if diagram is not None and diagram.winfo_exists():
            diagram._update_intro()

    def dismiss_session_hint(self):
        self.session_hint = False
        self.refresh_session_hint()

    def existing_view(self):
        try:
            return self.workbench.get_view('ObjectInspectorSE', create=False)
        except RuntimeError:
            return None

    def restart(self, event):
        self.remove_request = None
        self.members_request = None
        self.session_hint = False
        self.refresh_session_hint()
        self.session_hint_diagram = None
        self.session_hint_seen = False
        self.session.restarted()
        self.objects = []
        self.known_ids.clear()
        view = self.existing_view()
        if view is not None:
            view.expanded.clear()
            view.item_limits.clear()
            view._cancel_card_drag()
            view.bank_layout.clear()
            view.value_changes.clear()
            view.selected_id = None
            view.focus_ids.clear()
            view.nested_focus = False
            view.render([])
        self.session.notify()


def install():
    workbench = get_workbench()
    if hasattr(workbench, '_thonny_se_objects'):
        return
    workbench._thonny_se_objects = ObjectController(workbench)
    # Share the existing inspector's notebook instead of opening another split.
    location_option = 'view.ObjectInspectorSE.location'
    location = workbench.get_option('view.ObjectInspector.location', 'se')
    workbench.set_default(location_option, location)
    workbench.set_option(location_option, location)
    workbench.add_view(ObjectInspectorSE, tr('Object inspector SE'), location, visible_by_default=False)
