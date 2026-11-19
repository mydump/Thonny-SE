# SPDX-FileCopyrightText: 2026 Sebastian Ladhoff
# SPDX-License-Identifier: GPL-3.0-only
# See LICENSE in the project root for the full license text.

"""Independent object-bank view; observes completed executions even while hidden."""
from .scrolling import ScrollArea
from .display_context import context_for
from .visual_metrics import Typography, preserve_scroll
from .i18n import tr
import tkinter as tk
from tkinter import ttk, font

from thonny import get_runner, get_workbench
from thonny.common import InlineCommand

from .ui_style import EDGE, INK, SELECT, SELECTION_FILL, OBJECT_FILL, OBJECT_EDGE, OBJECT_SHADOW
from . import retina_icons
from .iconregistry import icon_path, menu_icon
from .diagram_preferences import OBJECT_METHODS, enabled


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
        self._action_bindings = []
        self.objects = []
        self.expanded = set()
        self.item_limits = {}
        self.canvas.bind('<Configure>', lambda e: self.draw())
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
        text = self._warning_text() if 'stale-warning' in self.canvas.gettags('current') else ''
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
        label = canvas.create_text(left+inset,top+(42 if narrow else 11),text=text,font=self.normal,fill=HINT_TEXT,
            width=max(40,width-inset-28),anchor='nw',tags='stale-warning')
        bounds = canvas.bbox(label)
        self.warning_run_image = get_workbench().get_image('run-current-script')
        action_y = bounds[3]+10
        canvas.create_image(left+inset, action_y+2, image=self.warning_run_image,
                            anchor='nw', tags='stale-warning')
        action_label = canvas.create_text(left+inset+24, action_y, text=action,
            font=self.normal,fill=HINT_TEXT,width=max(40,width-inset-52),
            anchor='nw',tags='stale-warning')
        bottom = max(top+45,canvas.bbox(action_label)[3]+12,
                     action_y+self.warning_run_image.height()+12)
        shape = canvas.create_polygon(left,top+10,left,top,left+10,top,left+width-26,top,
            left+width-16,top,left+width-16,top+10,left+width-16,bottom-10,left+width-16,bottom,
            left+width-26,bottom,left+10,bottom,left,bottom,left,bottom-10,
            smooth=True,fill=HINT_FILL,stipple='gray75',outline=HINT_BORDER,tags='stale-warning')
        canvas.tag_lower(shape,label)
        x,y=left+(17 if compact else 23),top+22 if compact else (top+bottom)/2
        canvas.create_oval(x-10,y-10,x+10,y+10,fill=HINT_BADGE,outline=HINT_INK,tags='stale-warning')
        canvas.create_line(x+2,y-6,x,y+1,fill=HINT_INK,width=3,capstyle='round',tags='stale-warning')
        canvas.create_oval(x-2,y+4,x+1,y+7,fill=HINT_INK,outline='',tags='stale-warning')
        canvas.tag_raise('stale-warning')
        return bottom-top+10

    def _redraw_mapped(self):
        # Switching notebook tabs need not change size or emit Configure.
        if self.canvas.winfo_exists() and self.canvas.winfo_ismapped():
            self.draw()

    def render(self, objects):
        self.objects = objects
        self.draw()

    def _bind_action(self, tag, sequence, callback):
        funcid = self.canvas.tag_bind(tag, sequence, callback)
        self._action_bindings.append((tag, sequence, funcid))

    def draw(self):
        canvas = self.canvas
        # Deleting items does not delete Tkinter's registered Tcl callbacks.
        for tag, sequence, funcid in self._action_bindings:
            canvas.tag_unbind(tag, sequence, funcid)
        self._action_bindings.clear()
        canvas.delete('all')
        # A narrow inspector must not split short method names into fragments.
        show_all = enabled(OBJECT_METHODS)
        method_width = max((self.normal.measure(member_label(name, obj.get('class_names', [obj['class_name']]))+signature)
                            for obj in self.objects for name, signature in obj['methods'].items()), default=0) if show_all else 0
        def nesting(nodes, level=0):
            deepest=level
            for node in nodes:
                if node.get('expanded'):
                    children=[*node.get('references',{}).values(),
                              *(entry['node'] for entry in node.get('items',[]))]
                    deepest=max(deepest,nesting(children,level+1))
            return deepest
        width = max(300+44*nesting(self.objects), canvas.winfo_width(), min(560, method_width+85))
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

        def reference(node, label, left, top, right=width-15):
            counter[0] += 1
            tag = 'reference_'+str(counter[0])
            cycle = node.get('cycle', False)
            opened = node.get('expanded', False)
            suffix = ((tr('{type} · {count} element').format(type=node['class_name'],count=1) if node.get('length') == 1 else tr('{type} · {count} elements').format(type=node['class_name'],count=node.get('length',0)))
                      if node['kind'] == 'container' else node['class_name'])
            if node.get('reference') and not node.get('names'):
                suffix += ' · '+tr('Object {number}').format(number=node['reference'])
            if cycle:
                suffix += ' · '+tr('Back reference')
            aliases = node.get('names', [])
            if aliases and node.get('path', {}).get('steps'):
                suffix += ' · '+tr('also {names}').format(names=', '.join(aliases))
            item = canvas.create_text(left+22, top+5, text=label+' : '+suffix,
                anchor='nw', width=max(150,right-left-30), font=self.normal,fill=INK,tags=(tag,))
            bottom = canvas.bbox(item)[3]+8
            if cycle:
                canvas.create_text(left+9,top+5,text='↩',font=self.normal,fill=SELECT,anchor='n',tags=(tag,))
                return bottom
            cy=top+12
            points = (left+5,cy-3,left+12,cy+4,left+19,cy-3) if opened else (left+7,cy-5,left+13,cy,left+7,cy+5)
            canvas.create_line(*points,fill=SELECT,width=2,tags=(tag,))
            self._bind_action(tag,'<Button-1>',lambda e,n=node:self.toggle_reference(n))
            if not opened:
                return bottom
            child_left = left+22
            y=bottom
            if node.get('limited'):
                return plain(tr('Further contents are not displayed here.'),child_left,y,right)
            if node['kind'] == 'object':
                return object_card(node,child_left,y,label,right-6)+5
            for entry in node.get('items', []):
                content=entry['node'];entry_label='['+entry['label']+']'
                if content['kind']=='scalar':
                    y=plain(entry_label+' = '+content['value'],child_left,y,right)
                else:
                    y=reference(content,entry_label,child_left,y,right)
            if not node.get('items'):
                y=plain(tr('Empty'),child_left,y,right)
            if node.get('remaining'):
                more_tag=tag+'_more'
                item=canvas.create_text(child_left+4,y+4,
                    text=tr('Show {count} more elements').format(count=min(100,node['remaining'])),
                    anchor='nw',font=self.normal,fill=SELECT,tags=(more_tag,),width=max(150,right-child_left-12))
                self._bind_action(more_tag,'<Button-1>',lambda e,n=node:self.show_more(n))
                y=canvas.bbox(item)[3]+9
            canvas.create_line(left+12,bottom,left+12,y-3,fill=OBJECT_EDGE)
            return y+5

        def plain(value,left,y,right=width-15):
            item=canvas.create_text(left+4,y+4,text=value,font=self.normal,fill=INK,
                                   anchor='nw',width=max(150,right-left-12))
            return canvas.bbox(item)[3]+9

        def object_card(obj,left,top,label=None,right=width-15):
            counter[0] += 1
            index=counter[0]
            text_width=max(150,right-left-28)
            tag = f'object_{index}'
            y = top + 14
            def text(value, *, heading=False):
                nonlocal y
                item = canvas.create_text(left + 14, y, anchor='nw', width=text_width,
                    text=value, font=self.bold if heading else self.normal, fill=INK, tags=(tag,))
                y = canvas.bbox(item)[3] + 8
            text(f"{label or ', '.join(obj['names'])} : {obj['class_name']}", heading=True)
            canvas.create_line(left+14, y, right-14, y, fill=OBJECT_EDGE, tags=(tag,))
            y += 10
            owners = obj.get('class_names', [obj['class_name']])
            for name, value in obj['attributes'].items():
                nested = obj.get('references', {}).get(name)
                if nested is None:
                    text(f'{member_label(name, owners)} = {value}')
                else:
                    y=reference(nested,member_label(name,owners),left+10,y,right-10)
            if not obj['attributes']:
                text(tr('No stored attributes'))
            if obj['methods'] and show_all:
                y += 4
                for method_index, (name, signature) in enumerate(obj['methods'].items()):
                    action_tag = f'{tag}_method_{method_index}'
                    row_top = y
                    item = canvas.create_text(left+44, y+9, anchor='nw',
                        width=max(45, text_width-42), text=member_label(name, owners)+signature,
                        font=self.normal, fill=SELECT, tags=(tag, action_tag, 'object_method'))
                    row_bottom = canvas.bbox(item)[3]+9
                    button = rounded(left+10, row_top, right-10, row_bottom,
                        fill='white', outline='#b9cfe8', tags=(tag, action_tag, 'object_method_button'))
                    canvas.tag_lower(button, item)
                    if retina_icons.enabled(canvas):
                        canvas.create_text(left+27, (row_top+row_bottom)/2,
                            text=retina_icons.glyph('class.instantiate'),
                            font=retina_icons.font_for(canvas, self.normal), fill=SELECT,
                            tags=(tag, action_tag, 'object_method'))
                    else:
                        canvas.create_image(left+27, (row_top+row_bottom)/2,
                            image=get_workbench().get_image(icon_path('class.instantiate', size=16)),
                            tags=(tag, action_tag, 'object_method'))
                    self._bind_action(action_tag, '<Enter>', lambda e, b=button:
                        canvas.itemconfigure(b, fill=SELECTION_FILL, outline=SELECT))
                    self._bind_action(action_tag, '<Leave>', lambda e, b=button:
                        canvas.itemconfigure(b, fill='white', outline='#b9cfe8'))
                    self._bind_action(action_tag, '<Button-1>', lambda e, o=obj, n=name: self.call_method(o, n))
                    y = row_bottom + 7
            elif obj['methods']:
                y += 4
                action_tag = f'{tag}_methods'
                row_bottom = y + max(34, self.normal.metrics('linespace')+18)
                button = rounded(left+10, y, right-10, row_bottom,
                    fill='white', outline='#b9cfe8', tags=(tag, action_tag, 'object_methods_dropdown'))
                canvas.create_text(left+23, (y+row_bottom)/2, anchor='w', text=tr('Methods …'),
                    font=self.normal, fill=SELECT, tags=(tag, action_tag))
                arrow_x, arrow_y = right-27, (y+row_bottom)/2
                canvas.create_line(arrow_x-4, arrow_y-2, arrow_x, arrow_y+2, arrow_x+4, arrow_y-2,
                    fill=SELECT, width=2, capstyle='round', joinstyle='round', tags=(tag, action_tag))
                self._bind_action(action_tag, '<Enter>', lambda e, b=button:
                    canvas.itemconfigure(b, fill=SELECTION_FILL, outline=SELECT))
                self._bind_action(action_tag, '<Leave>', lambda e, b=button:
                    canvas.itemconfigure(b, fill='white', outline='#b9cfe8'))
                self._bind_action(action_tag, '<Button-1>', lambda e, o=obj: self.open_methods(o, e))
                y = row_bottom+7
            bottom = y + 6
            shadow = rounded(left+2, top+3, right+2, bottom+3,
                fill=OBJECT_SHADOW, tags=(tag, 'object_shadow'))
            shape = rounded(left, top, right, bottom, fill=OBJECT_FILL,
                outline=OBJECT_EDGE, tags=(tag, 'object_card'))
            canvas.tag_lower(shape)
            canvas.tag_lower(shadow)
            return bottom + 18
        for obj in self.objects:
            if obj.get('kind') == 'container':
                top=reference(obj,', '.join(obj['names']),left,top)+12
            else:
                top=object_card(obj,left,top)
        canvas.configure(scrollregion=(0, 0, width, max(top, canvas.winfo_height())))
        self._draw_warning()
        if width > canvas.winfo_width()+1:
            self.horizontal.grid()
        else:
            self.horizontal.grid_remove()

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
        self.session_hint = False
        self.session_hint_seen = False
        self.session_hint_diagram = None
        from .instantiation import ObjectSession
        self.session = ObjectSession(self)
        from .method_call import MethodCallController
        self.methods = MethodCallController(self)
        workbench.bind('ToplevelResponse', self.completed, True)
        workbench.bind('thonny_se_objects_response', self.received, True)
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
