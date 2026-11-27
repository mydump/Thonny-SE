# SPDX-FileCopyrightText: 2026 Sebastian Ladhoff
# SPDX-License-Identifier: GPL-3.0-only
# See LICENSE in the project root for the full license text.

"""UML-Klassenkarten mit direkter Textbearbeitung."""
from .scrolling import ScrollArea
from .zooming import capture_anchor, restore_anchor, event_position
from .display_context import context_for
from .visual_metrics import Typography, preserve_scroll
from .ui_style import DARK_CANVAS, DARK_DIAGRAM_COLORS, UML_SECTION_FILLS, UML_SECTION_INKS
from .ui_style import DARK_MONOCHROME_CANVAS, DARK_MONOCHROME_CONTROLS, DARK_MONOCHROME_INK, DARK_MONOCHROME_SURFACE
from .graphics import clear_shapes, rounded, clear_icon_images, icon
from .i18n import tr
from collections import defaultdict
from math import hypot, floor
import tkinter as tk
from tkinter import ttk, font
from thonny import get_workbench
from thonny.ui_utils import create_tooltip
from .ui_style import DISABLED, EDGE, ERROR, HINT_FILL, INK, MUTED, SELECT, SELECTION_WIDTH, draw_chevron, ui_color
from .cat_head import draw_cat_head
from .diagram_hint import DiagramHint
from .diagram_preferences import uses_dark_diagrams, UML_EARS, UML_HINTS, enabled
from .field_feedback import FieldFeedback
from .uml_model import CLASS_KINDS, COMMENT_MAX_SIZE, COMMENT_MIN_SIZE, initial_upper
from .uml_methods import member_parts, member_text, visible_methods, member_visibility, is_constructor
from .iconregistry import draw_visibility_icon, menu_icon
from . import retina_icons
from .uml_inline_editor import DeleteMemberPanel, InlineMemberEditor
from .uml_edit_panel import DELETE_FILL, PANEL_INSET, PANEL_SURROUND, edit_panel, header_picker, panel_badge
from .uml_gesture_icons import direction_arrow
from .uml_geometry import GRID_ORIGIN, GRID_STEP, curved_points, dragged_bend, magnet
from .uml_relationship_layout import place_label
from .uml_relationships import association_arrow, association_points, card_edge_toward, endpoint_symbol, multiplicity_position, self_relationship_points


ADD_LABELS = {"attributes": tr('+ Add attribute'), "methods": tr('+ Add method')}
ROW_ARROW_HEIGHT = 23


def export_member_text(row, section, class_name):
    """Use the constructor marker in graphics, independently of code/review text."""
    if section == 'methods' and is_constructor(row):
        return 'c ' + ''.join(member_parts(row,section,class_name).values())
    return member_text(row,class_name)


class UmlCanvas(ttk.Frame):
    def __init__(self, master, editor):
        super().__init__(master)
        self.editor = editor
        self.zoom = 1.0
        self.diagram_scale = 1.0
        self._scale_job = None
        self._pending_zoom = None
        self._pending_zoom_anchor = None
        self._zoom_job = None
        from .diagram_preferences import UML_GRID
        mode = get_workbench().get_option(UML_GRID, "none")
        self.grid_mode = mode if mode in ("none", "visual", "magnetic") else "none"
        self.relationship_drag = None
        self.pending_relationship_edit = False
        self.exporting = False
        self._colors = {}
        self._export_widths = {}
        self.monochrome = False
        self._dark_monochrome = False
        self.member_selection = None
        self.name_regions = {}
        self.on_zoom = None
        self.canvas = tk.Canvas(self, background="white", highlightthickness=0)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview).grid(row=0, column=1, sticky="ns")
        ttk.Scrollbar(self, orient="horizontal", command=self.canvas.xview).grid(row=1, column=0, sticky="ew")
        self.canvas.configure(yscrollcommand=self._yscroll, xscrollcommand=self._xscroll)
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)
        self.typography = Typography(self)
        self.display_typography = Typography(self)
        self.normal = self.typography['body']
        self.bold = self.typography['heading']
        self.abstract = self.typography['abstract']
        self.method_abstract = self.typography['abstract_method']
        self.display_normal = self.display_typography['body']
        self.display_bold = self.display_typography['heading']
        self.display_abstract = self.display_typography['abstract']
        self.display_method_abstract = self.display_typography['abstract_method']
        self.row_height = self.typography.line_height()
        clear_icon_images(self.canvas)
        self.cards, self.fields, self.notes = {}, {}, {}
        self.save_regions = {}
        self.add_regions = {}
        self.input = None
        self.comment_input = None
        self.comment_note = None
        self.resize_note_from = None
        self.member_editor = None
        self.delete_mode = False
        self.editing = None
        self.drag = None
        self.relationship_origin = None
        self.relationship_pointer = None
        self.info_hint = DiagramHint(self.canvas, UML_HINTS, color=self._color)
        self.intro_context_seen = False
        self.intro_edit_seen = False
        self.relationship_hint_dismissed = False
        self.canvas.bind("<Configure>", self._configured)
        self.canvas.bind("<Button-1>", self._click)
        self.canvas.bind("<Double-Button-1>", self._double_click)
        self.canvas.bind("<Motion>", self._hover)
        self.canvas.bind("<Leave>", lambda e: self.canvas.configure(cursor=""))
        self.canvas.bind("<B1-Motion>", self._drag)
        self.canvas.bind("<ButtonRelease-1>", self._release)
        self.canvas.bind("<Button-3>", self._context)
        self.canvas.bind("<Button-2>", self._context)
        self.canvas.bind("<Control-Button-1>", self._context)
        from .tooltips import CanvasToolTip
        self.save_tip = CanvasToolTip(self.canvas)
        self.canvas.bind("<Escape>", self._escape)
        self.canvas.bind("<Delete>", lambda e: self.editor.delete_selection() if not self.delete_mode else "break")
        self.canvas.bind("<BackSpace>", lambda e: self.editor.delete_selection() if not self.delete_mode else "break")
        self.scrolling = ScrollArea(self.canvas, self,
            zoom=lambda steps: self.request_zoom(self.target_zoom + steps*0.1),
            zoom_at=self._zoom_at_pointer)
        self.bind("<Map>", lambda e: self.after_idle(self.draw))
        context_for(self).subscribe(self,self._display_changed)
        self.bind("<Destroy>",self._zoom_destroyed,add=True)

    def request_diagram_scale(self, value):
        self.diagram_scale = round(max(.5, min(2., float(value))), 3)
        if self._scale_job is None:
            self._scale_job = self.after(16, self._draw_scale)

    def _draw_scale(self):
        self._scale_job = None
        preserve_scroll(self.canvas, self.draw)

    def flush_diagram_scale(self):
        if self._scale_job is not None:
            self.after_cancel(self._scale_job)
            self._draw_scale()

    def _space(self, base):
        # 100% preserves the established UML layout; only padding changes.
        return max(3, round(base/self.diagram_scale))

    @property
    def diagram_normal(self):
        return self.display_bold if self.diagram_scale >= 1.5 else self.display_normal

    @property
    def diagram_abstract_method(self):
        return self.display_abstract if self.diagram_scale >= 1.5 else self.display_method_abstract

    @property
    def layout_normal(self):
        return self.bold if self.diagram_scale >= 1.5 else self.normal

    def _appearance_metrics(self):
        baseline = self.typography.line_height()
        text_height = self.layout_normal.metrics('linespace')
        old_padding = baseline-self.normal.metrics('linespace')
        stroke = max(1, int(2*self.diagram_scale+.5))
        self.row_height = text_height+max(stroke+4, round(old_padding/self.diagram_scale))

    def _style_contours(self):
        stroke = max(1, int(max(1, int(2*self.diagram_scale+.5))*self.zoom+.5))
        for item in self.canvas.find_withtag('drawing'):
            tags = self.canvas.gettags(item)
            kind = self.canvas.type(item)
            # Visibility glyphs and cat artwork keep their own source strokes.
            if {'cat-head', 'comment-resize'}.intersection(tags) or any(tag.startswith('member-row:') for tag in tags):
                continue
            if kind in ('line', 'rectangle', 'polygon', 'oval'):
                ink = self.canvas.itemcget(item, 'fill' if kind == 'line' else 'outline')
                if ink:
                    selected = ('class_selection' in tags or ink == self._color(SELECT))
                    self.canvas.itemconfigure(item, width=stroke+2 if selected else stroke)
            coordinates = self.canvas.coords(item)
            if coordinates:
                self.canvas.coords(item, *(round(v) for v in coordinates))

    def _wheel_zoom(self, event):
        self._zoom_at_pointer(1 if event.delta>0 else -1,event_position(self.canvas,event))
        return "break"

    def _zoom_at_pointer(self,steps,position):
        anchor=capture_anchor(self.canvas,self.zoom,position)
        self.request_zoom(self.target_zoom+steps*.1,anchor=anchor)

    @property
    def target_zoom(self):
        return self.zoom if self._pending_zoom is None else self._pending_zoom

    def request_zoom(self,value, *, anchor=None):
        value=round(max(0.5,min(2.0,value)),4)
        self._pending_zoom=value
        self._pending_zoom_anchor=anchor
        if self.on_zoom:self.on_zoom(value)
        if self._zoom_job is None:
            self._zoom_job=self.after(16,self._apply_zoom_request)

    def _apply_zoom_request(self):
        target=self._pending_zoom
        anchor=self._pending_zoom_anchor
        self._pending_zoom=self._zoom_job=self._pending_zoom_anchor=None
        if target is not None:
            if anchor is None:self.set_zoom(target)
            else:self.set_zoom(target,anchor=anchor)

    def _zoom_destroyed(self,event):
        if event.widget is self and self._scale_job is not None:
            self.after_cancel(self._scale_job)
            self._scale_job = None
        if event.widget is self and self._zoom_job is not None:
            self.after_cancel(self._zoom_job)
            self._zoom_job=self._pending_zoom=self._pending_zoom_anchor=None

    def set_zoom(self, value, *, anchor=None):
        if self._zoom_job is not None:
            self.after_cancel(self._zoom_job)
            self._zoom_job=self._pending_zoom=self._pending_zoom_anchor=None
        value=round(max(0.5,min(2.0,value)),4)
        if value==self.zoom:
            if self.on_zoom:self.on_zoom(value)
            return
        self.zoom=value
        previous_fonts=self._select_zoom_fonts()
        self.draw()
        restore_anchor(self.canvas,self.zoom,anchor)
        if self.on_zoom:
            self.on_zoom(self.zoom)

    def action_font(self):
        fonts=self.display_typography.fonts
        if 'action' not in fonts:
            values=self.display_normal.actual()
            size=values['size']
            fonts['action']=font.Font(root=self,**{**values,'size':size+2 if size>0 else size-2,'weight':'bold'})
        return fonts['action']

    def _fit_zoom_fonts(self):
        if self.zoom == 1:
            self.display_typography.select_zoom(1)
            return
        size = self.normal.actual('size')
        pixels = abs(size) if size < 0 else size*self.winfo_fpixels('1p')
        pixels = max(1, round(pixels*self.zoom))
        samples = {'body': [], 'heading': [], 'abstract': [], 'abstract_method': []}
        from .uml_python_semantics import abstract_method
        member_role = 'heading' if self.diagram_scale >= 1.5 else 'body'
        abstract_role = 'abstract' if self.diagram_scale >= 1.5 else 'abstract_method'
        for card in self.editor.document['classes']:
            samples['abstract' if card.get('class_kind') == 'abstract' else 'heading'].append(card['name'])
            samples['body'].extend(self._header_details(card))
            for section, rows in (('attributes', card['attributes']), ('methods', self._methods(card))):
                for row in rows:
                    role = abstract_role if section == 'methods' and abstract_method(card, row) else member_role
                    samples[role].append(self._member_signature(row, section, card['name']))
        limits = {role: [self.typography[role].measure(text)*self.zoom+1 for text in texts]
                  for role, texts in samples.items()}
        while True:
            self.display_typography.select_zoom(self.zoom, pixel_size=pixels)
            fits = all(self.display_typography[role].metrics('linespace') <=
                       self.typography[role].metrics('linespace')*self.zoom+1 and
                       all(self.display_typography[role].measure(text) <= limit
                           for text, limit in zip(texts, limits[role]))
                       for role, texts in samples.items())
            if fits or pixels == 1:
                return
            pixels -= 1

    def _select_zoom_fonts(self):
        old={str(self.display_normal):'body',str(self.display_bold):'heading',
             str(self.display_abstract):'abstract',str(self.display_method_abstract):'abstract_method'}
        # Keep old variants alive until native entry/label bindings are updated.
        previous=(self.display_normal,self.display_bold,self.display_abstract,self.display_method_abstract)
        member=getattr(self,"member_editor",None)
        old_action=getattr(member,"action_font",None)
        if old_action is not None:
            old[str(old_action)]="action"
            previous=(*previous,old_action)
        self._fit_zoom_fonts()
        self.display_normal=self.display_typography['body']
        self.display_bold=self.display_typography['heading']
        self.display_abstract=self.display_typography['abstract']
        self.display_method_abstract=self.display_typography['abstract_method']
        if old_action is not None:member.action_font=self.action_font()
        if all(str(self.display_typography[role])==name for name,role in old.items()):return previous
        def update(widget):
            # Fetch only the font, not Tk's full option metadata on every zoom.
            # Containers without a font option still need their children visited.
            try:
                role=old.get(str(widget.cget('font')))
            except tk.TclError:
                role=None
            if role:widget.configure(font=self.display_typography[role])
            for child in widget.winfo_children():update(child)
        member=getattr(self,'member_editor',None)
        panel=member or getattr(self,'input_frame',None)
        if panel is not None and panel.winfo_exists():update(panel)
        return previous

    def _display_changed(self, state):
        self.typography.refresh()
        previous_fonts=self._select_zoom_fonts()
        self.row_height = self.typography.line_height()
        if self.winfo_ismapped():
            preserve_scroll(self.canvas,self.draw)

    def _yscroll(self, *args):
        # Scrollbars werden über ihre Tk-Variable gekoppelt, ohne Zeichnung zu erzwingen.
        self.grid_slaves(row=0, column=1)[0].set(*args)
        self._position_member()
        self._draw_relationship_preview()
        self.info_hint.draw()
        self._draw_grid()

    def _xscroll(self, *args):
        self.grid_slaves(row=1, column=0)[0].set(*args)
        self._position_member()
        self._draw_relationship_preview()
        self.info_hint.draw()
        self._draw_grid()

    def _configured(self, event):
        self._position_member()
        self._draw_relationship_preview()
        self.info_hint.draw()
        self._draw_grid()

    def snap_position(self, x, y):
        if self.grid_mode == 'magnetic':
            return magnet(x,tolerance=5/self.zoom),magnet(y,tolerance=5/self.zoom)
        return x,y

    def _draw_grid(self):
        canvas = self.canvas
        canvas.delete('uml-grid')
        if self.exporting or self.grid_mode == 'none':
            return
        left,top=canvas.canvasx(0),canvas.canvasy(0)
        right,bottom=left+canvas.winfo_width(),top+canvas.winfo_height()
        step,origin=GRID_STEP*self.zoom,GRID_ORIGIN*self.zoom
        for axis in (0,1):
            low,high=(left,right) if axis == 0 else (top,bottom)
            first=floor((low-origin)/step)
            for index in range(first,first+int((high-low)/step)+3):
                coordinate=origin+index*step
                points=(coordinate,top,coordinate,bottom) if axis == 0 else (left,coordinate,right,coordinate)
                canvas.create_line(*points,fill=self._color('#edf0f3'),width=1,tags=('uml-grid',))
        canvas.tag_lower('uml-grid')

    def point(self, event):
        return self.canvas.canvasx(event.x)/self.zoom, self.canvas.canvasy(event.y)/self.zoom

    def hit(self, x, y):
        for card in reversed(self.editor.document["classes"]):
            bounds = self.cards.get(card["id"])
            if bounds and bounds[0] <= x <= bounds[2] and bounds[1] <= y <= bounds[3]:
                for (cid, section, row), field in self.fields.items():
                    if cid == card["id"] and field[0] <= x <= field[2] and field[1] <= y <= field[3]:
                        return card["id"], section, row
                if y <= bounds[1] + self.row_height:
                    return card["id"], "name", None
                return card["id"], None, None
        return None, None, None

    def _header_details(self, card):
        if card.get("class_kind") == "interface":
            yield "«interface»"

    def _methods(self, card):
        rows = visible_methods(card)
        if not self.exporting and self.editing is not None and self.editing[:2] == (card['id'], 'methods'):
            current = next((row for row in card['methods'] if row['id'] == self.editing[2]), None)
            if current is not None and current not in rows:
                return [row for row in card['methods'] if row in rows or row is current]
        return rows

    def _member_signature(self, row, section, class_name=None):
        if class_name is None and section == 'methods' and is_constructor(row):
            card = next((card for card in self.editor.document['classes'] if row in card[section]), {})
            class_name = card.get('name', '')
        return ''.join(member_parts(row, section, class_name or '').values())

    def _card_width(self, card, methods):
        if self.exporting and card['id'] in self._export_widths:
            return self._export_widths[card['id']]
        from .uml_python_semantics import abstract_method
        # Layout and relationship anchors use canonical metrics at every zoom.
        # Raster font rounding belongs only to the displayed text.
        normal = self.layout_normal
        face = self.abstract if card.get("class_kind") == "abstract" else self.bold
        def member_width(row, section):
            member_face = normal
            if section == 'methods' and abstract_method(card, row):
                member_face = self.abstract if self.diagram_scale >= 1.5 else self.method_abstract
            text = self._member_signature(row, section, card["name"])
            left, right = self.typography.units(8), self.typography.units(10)
            padding = self.typography.units(46)+self._space(left)-left+self._space(right)-right
            return member_face.measure(text)+padding
        return max(150, face.measure(card["name"])+max(66,2*self._space(40)),
                   *(normal.measure(text)+2*self._space(12) for text in self._header_details(card)),
                   *(member_width(row, section)
                     for section, rows in (("attributes", card["attributes"]), ("methods", methods))
                     for row in rows))

    def arrange_cards(self, cards=None, *, y=24):
        if cards is None:
            cards = self.editor.document["classes"]
        for start in range(0, len(cards), 2):
            row = cards[start:start+2]
            left = row[0]
            left.update(x=24, y=y)
            if len(row) == 2:
                row[1].update(x=48 + self._card_width(left, self._methods(left)), y=y)
            rows = max(self.row_height * (1 + max(1,len(card["attributes"])) + max(1,len(self._methods(card))))
                       + sum(1 for _ in self._header_details(card))*self.normal.metrics("linespace")
                       for card in row)
            y += rows + 24

    def _color(self, color):
        return self._colors.get(color, color)

    def draw(self):
        if not self.exporting and self.zoom != 1:
            previous_fonts = self._select_zoom_fonts()
        self._appearance_metrics()
        dark = not self.exporting and uses_dark_diagrams()
        self._dark_monochrome = dark and self.monochrome
        self._colors = (DARK_MONOCHROME_CONTROLS if self.monochrome else DARK_DIAGRAM_COLORS) if dark else {}
        canvas = self.canvas
        clear_shapes(canvas, "add-control")
        canvas.delete("drawing")
        canvas.delete("member-selection")
        self._name_items = []
        self._symbol_items = []
        clear_icon_images(canvas)
        self.cards, self.fields, self.notes = {}, {}, {}
        self.save_regions = {}
        self.add_regions = {}
        focused = self.editing[0] if self.editing is not None and not self.exporting else None
        background = DARK_MONOCHROME_CANVAS if self._dark_monochrome else DARK_CANVAS if dark else "white"
        if focused is not None and not self._dark_monochrome:
            background = self._color(PANEL_SURROUND)
        canvas.configure(background=background)
        right, bottom = 0, 0
        show_cats = enabled(UML_EARS)
        for card in self.editor.document["classes"]:
            cid, x, y = card["id"], card["x"], card["y"]
            tags = ("drawing", "focus-card") if cid == focused else ("drawing",)
            methods = self._methods(card)
            width = self._card_width(card, methods)
            details = list(self._header_details(card))
            heading_height = self.row_height + len(details)*self.normal.metrics("linespace")
            member_rows = max(1, len(card["attributes"])) + max(1, len(methods))
            height = heading_height + self.row_height * member_rows
            self.cards[cid] = (x, y, x+width, y+height)
            canvas.create_rectangle(x, y, x+width, y+height, fill=self._color("white"), outline="", width=0, tags=(*tags, "class-card"))
            colored = not self.monochrome and (focused is None or cid == focused)
            canvas.create_rectangle(x,y,x+width,y+heading_height,
                fill=self._color(UML_SECTION_FILLS['name']) if colored else self._color('white'),outline='',
                tags=(*tags,'class-header-fill'))
            name_right = x+width-8
            name_y = y
            if card.get("class_kind") == "interface":
                line = self.normal.metrics("linespace")
                canvas.create_text(x+width/2, y+line*.7, text=details.pop(0),
                                   font=self.display_normal, fill=self._color(MUTED), tags=tags)
                name_y += line
            self.fields[cid, "name", None] = (x+self._space(8), name_y+2, name_right, name_y+self.row_height-2)
            title_font = self.display_abstract if card.get("class_kind") == "abstract" else self.display_bold
            name_item = canvas.create_text(x+width/2, name_y+self.row_height/2, text=card["name"], width=max(20,(width-(24 if self.exporting else 66))*self.zoom), font=title_font,
                               fill=self._color(INK), tags=tags)
            self._name_items.append((name_item, (cid, "name", None), card["name"], title_font))
            for index, detail in enumerate(details):
                detail_y = name_y+self.row_height + (index+.2)*self.normal.metrics("linespace")
                canvas.create_text(x+width/2, detail_y, text=detail, font=self.display_normal,
                                   fill=self._color(MUTED), tags=tags)
            cursor = y+heading_height
            for section in ("attributes", "methods"):
                rows = card[section] if section=="attributes" else methods
                section_rows = max(1,len(rows))
                canvas.create_rectangle(x,cursor,x+width,cursor+section_rows*self.row_height,
                    fill=self._color(UML_SECTION_FILLS[section]) if colored else self._color('white'),outline='',
                    tags=(*tags,'class-'+section+'-fill'))
                divider = "#626e7d" if dark else EDGE
                canvas.create_line(x, cursor, x+width, cursor, fill=divider, tags=tags)
                for row in rows:
                    active = self.member_editor is not None and self.editing == (cid, section, row["id"]) and not self.exporting
                    row_height = self.row_height
                    self.fields[cid, section, row["id"]] = (x+self._space(8), cursor+2, x+width-self._space(8), cursor+row_height-2)
                    if active:
                        canvas.create_rectangle(x+2, cursor+2, x+width-2, cursor+row_height-2,
                                                fill=self._color(DELETE_FILL) if self.delete_mode else self._color(UML_SECTION_FILLS[section]) if colored else self._color("white"), outline="", tags=tags)
                    self._draw_member(card, section, row, cursor, tags)
                    cursor += row_height
                if not rows:
                    cursor += self.row_height
                # A virtual add-row anchors keyboard navigation and the editor,
                # without increasing card geometry or covering a real text row.
                if not self.exporting:
                    self.fields[cid, section, None] = (x+self._space(8), cursor-self.row_height+2,
                                                       x+width-self._space(8), cursor-2)
            # Paint the contour last, over full-bleed section fills, including at zoom.
            canvas.create_rectangle(x,y,x+width,y+height,fill='',outline=self._color(EDGE),width=1,
                                    tags=(*tags,'class-border'))
            if show_cats:
                draw_cat_head(canvas, x, y, x + width, cid, scale=0.64,
                              stroke=max(1, int(2*self.diagram_scale+.5)), zoom=self.zoom,
                              fill=self._color(UML_SECTION_FILLS['name']) if colored else self._color('white'),
                              bottom=y + height, tags=tags, ink=self._color(EDGE),
                              detail=self._color("#ffffff"))
            if not self.exporting:
                tracker = getattr(self.editor, 'source_status', None)
                state = tracker.states.get(cid, 'new' if not card.get('source') else '') if tracker else 'new' if not card.get('source') else ''
                if state:
                    from . import retina_icons
                    from .iconregistry import icon_path
                    center_y = name_y+self.row_height/2
                    if retina_icons.enabled(self):
                        canvas.create_text(x+width-18, center_y, text=retina_icons.glyph('document.save'),
                            font=retina_icons.font_for(self, self.display_normal),
                            fill=DARK_MONOCHROME_INK if self._dark_monochrome else self._color(MUTED),
                            tags=(*tags, 'source-save'))
                    else:
                        self.save_image = get_workbench().get_image(icon_path('document.save',size=16,dark=dark))
                        canvas.create_image(x+width-18, center_y,image=self.save_image,tags=(*tags, 'source-save'))
                    self.save_regions[cid] = (x+width-32,center_y-14,x+width-4,center_y+14,state)
            if not self.exporting and cid in self.editor.selected_class_ids():
                canvas.create_rectangle(x-2, y-2, x+width+2, y+height+2, outline=self._color(SELECT), width=SELECTION_WIDTH, tags=(*tags, "class_selection"))
            right, bottom = max(right, x+width+60), max(bottom, y+height+60)
        if self.relationship_origin not in self.cards:
            self.relationship_origin = None
        self._draw_comments()
        self._draw_relationships()
        if focused is not None:
            self._dim_background()
            canvas.tag_raise("focus-card")
        if self.monochrome:
            self._apply_monochrome()
        canvas.scale("drawing", 0, 0, self.zoom, self.zoom)
        self._style_contours()
        self._draw_add_controls()
        drawing = canvas.bbox("drawing")
        if drawing:
            right, bottom = max(right*self.zoom, drawing[2]+12), max(bottom*self.zoom, drawing[3]+12)
        top = min(0, drawing[1]-8) if drawing else 0
        canvas.configure(scrollregion=(min(0,drawing[0]-8) if drawing else 0, top, max(right, canvas.winfo_width()), max(bottom, canvas.winfo_height())))
        self._draw_name_selection()
        self._draw_grid()
        self._position_member()
        self._update_intro()

    def _draw_add_controls(self):
        if self.exporting or self.delete_mode:
            return
        selected = self.editor.selected_class_ids()
        if self.editing is not None:
            selected = selected | {self.editing[0]}
        for cid in selected:
            if cid not in self.cards:
                continue
            right = self.cards[cid][2]
            for section in ('attributes', 'methods'):
                field = (cid, section, None)
                box = self.fields[field]
                cy = (box[1]+box[3])/2
                u = self.typography.units
                bounds = (right+u(5), cy-u(12), right+u(37), cy+u(12))
                self.add_regions[field] = bounds
                tags = ('drawing', 'add-control')
                accent = self._color(UML_SECTION_INKS[section])
                # Draw UI surfaces in final display coordinates, like the editor
                # overlay: scaling a contour afterwards defeats pixel alignment
                # and cannot resize raster fallbacks on Windows/X11.
                display_bounds = tuple(value*self.zoom for value in bounds)
                surface = rounded(self.canvas, *display_bounds, radius=u(5)*self.zoom,
                        fill=self._color(UML_SECTION_FILLS[section]), outline=accent, group='add-control')
                self.canvas.addtag_withtag('drawing', 'add-control')
                # Center on the rendered contour after its pixel alignment,
                # rather than rounding the glyph and its container separately.
                left, top, right_edge, bottom = self.canvas.bbox(surface)
                icon(self.canvas, (left+right_edge)/2, (top+bottom)/2, 'edit.add', self.display_normal,
                     accent, pixels=u(16)*self.zoom, tags=tags)

    def _add_at(self, event):
        x, y = self.point(event)
        return next((field for field, box in self.add_regions.items()
                     if box[0] <= x <= box[2] and box[1] <= y <= box[3]), None)

    def _draw_name_selection(self):
        canvas = self.canvas
        self.name_regions = {}
        for item, field, name, face in self._name_items:
            box = canvas.bbox(item)
            if box is None:
                continue
            self.name_regions[field] = tuple(box)
        self.symbol_regions = {field: tuple(canvas.bbox(item)) for item, field in self._symbol_items
                               if canvas.bbox(item) is not None}
        field = self.member_selection
        if field not in self.name_regions:
            self.member_selection = None
        if field in self.name_regions and self.editor.selection == field[0] and self.editing is None and not self.exporting:
            item = next(item for item, key, _, _ in self._name_items if key == field)
            canvas.itemconfigure(item, fill=self._color(SELECT), tags=(*canvas.gettags(item), 'member-selection'))

    def _name_at(self, x, y):
        for field, box in reversed([*self.name_regions.items(), *self.symbol_regions.items()]):
            if box[0] <= x*self.zoom <= box[2] and box[1] <= y*self.zoom <= box[3]:
                return field
        return None

    def _apply_monochrome(self):
        """Render the model in grayscale, retaining editor selection cues."""
        canvas = self.canvas
        ink = DARK_MONOCHROME_INK if self._dark_monochrome else "#000000"
        surface = DARK_MONOCHROME_SURFACE if self._dark_monochrome else "#ffffff"
        selection = self._color(SELECT)
        for item in canvas.find_withtag("drawing"):
            tags = canvas.gettags(item)
            if "class_selection" in tags or "source-save" in tags or "add-control" in tags:
                continue
            kind = canvas.type(item)
            if 'cat-head' in tags:
                if kind == 'line':
                    canvas.itemconfigure(item, fill=surface if 'cat-seam' in tags else ink)
                else:
                    if canvas.itemcget(item, 'outline'):
                        canvas.itemconfigure(item, outline=ink)
                    if canvas.itemcget(item, 'fill'):
                        canvas.itemconfigure(item, fill=surface)
                continue
            options = ("fill", "outline") if kind in ("rectangle", "polygon", "oval") else ("fill",) if kind in ("text", "line") else ()
            for option in options:
                value = canvas.itemcget(item, option)
                if not value:
                    continue
                if value == selection and ("selected-member-icon" in tags or any(tag.startswith("relationship:") for tag in tags)):
                    continue
                if option == "fill" and kind in ("rectangle", "polygon", "oval"):
                    # Preserve filled diamonds and dark details, remove pastel fills.
                    rgb = canvas.winfo_rgb(value)
                    filled_symbol = "relationship-filled" in tags
                    if self._dark_monochrome and "relationship-hollow" in tags:
                        value = DARK_MONOCHROME_CANVAS
                    else:
                        value = ink if filled_symbol or max(rgb) < 32768 else surface
                else:
                    value = ink
                canvas.itemconfigure(item, **{option: value})

    def _dim_background(self):
        canvas = self.canvas
        colors = {}
        for item in canvas.find_withtag("drawing"):
            if "focus-card" in canvas.gettags(item):
                continue
            kind = canvas.type(item)
            options = ("fill", "outline") if kind in ("rectangle", "polygon") else ("fill",) if kind in ("text", "line") else ()
            for option in options:
                color = canvas.itemcget(item, option)
                if not color:
                    continue
                if color not in colors:
                    rgb = [round(component / 257 * .84) for component in canvas.winfo_rgb(color)]
                    colors[color] = "#{:02x}{:02x}{:02x}".format(*rgb)
                canvas.itemconfigure(item, **{option: colors[color]})

    def _draw_comments(self):
        canvas = self.canvas
        notes = self.editor.document["comments"]
        if self.comment_input is not None and self.new_comment:
            notes = [*notes, self.comment_note]
        for note in notes:
            x, y = note["x"], note["y"]
            tags = ("drawing", "comment")
            width = note.get("width")
            editing = self.comment_note is note
            text = canvas.create_text(x+self._space(10), y+self._space(8), text=note["text"] or " ", anchor="nw",
                                      width=(width-2*self._space(15) if width else 240)*self.zoom,
                                      font=self.diagram_normal, fill=self._color(INK), tags=tags)
            left, top, right, bottom = canvas.bbox(text)
            if width is None:
                width = max(250 if editing and self.new_comment else 86, (right-left)/self.zoom + 2*self._space(14))
            height = max(note.get("height", 0), (bottom-top)/self.zoom + 2*self._space(8))
            if editing:
                height = max(76, height)
                canvas.itemconfigure(text, state="hidden")
            right, bottom = x+width, y+height
            self.notes[note["id"]] = (x, y, right, bottom)
            selected = self.editor.selection == note["id"] and not self.exporting
            edge = self._color(SELECT) if selected else self._color(EDGE)
            shape = canvas.create_polygon(x, y, right-12, y, right, y+12, right, bottom, x, bottom,
                                          fill=self._color(HINT_FILL), outline=edge, width=2 if selected else 1, tags=tags)
            canvas.tag_lower(shape, text)
            canvas.create_line(right-12, y, right-12, y+12, right, y+12, fill=edge, tags=tags)
            if not self.exporting:
                for offset in (6, 11):
                    canvas.create_line(right-offset, bottom-3, right-3, bottom-offset, fill=edge, tags=(*tags, "comment-resize"))
            if note["target"] in self.cards:
                points = association_points(self.notes[note["id"]], self.cards[note["target"]])
                connector = canvas.create_line(*(value for point in points for value in point),
                                               fill=self._color(EDGE), dash=(4, 4), tags=tags)
                canvas.tag_lower(connector, shape)
                if canvas.find_withtag("class-card"):
                    canvas.tag_lower(connector, "class-card")

    def _note_at(self, x, y):
        notes = self.editor.document["comments"]
        if self.comment_input is not None and self.new_comment:
            notes = [*notes, self.comment_note]
        return next((note for note in reversed(notes)
                     if (bounds := self.notes.get(note["id"]))
                     and bounds[0] <= x <= bounds[2] and bounds[1] <= y <= bounds[3]), None)

    def _draw_relationships(self):
        canvas = self.canvas
        self.relationship_labels = []
        groups = defaultdict(list)
        for relation in self.editor.document["relationships"]:
            pair = tuple(sorted((relation["start"], relation["end"])))
            groups[pair].append(relation)
        for pair, relations in groups.items():
            for index, relation in enumerate(relations):
                lane = index if pair[0] == pair[1] else index - (len(relations)-1)/2
                if relation["start"] != pair[0]:
                    lane = -lane
                self._draw_relationship(relation, lane)
        # Exact segments also cover curved paths; their bounding rectangles would
        # unnecessarily block large parts of the diagram.
        segments = []
        for item in canvas.find_withtag("relationship-geometry"):
            coords = canvas.coords(item)
            points = list(zip(coords[::2], coords[1::2]))
            if canvas.type(item) == "polygon":
                points.append(points[0])
            segments.extend(zip(points, points[1:]))
        occupied = [*self.cards.values(), *self.notes.values()]
        for item in self.relationship_labels:
            bounds = canvas.bbox(item)
            if bounds is None:
                continue
            # Fonts are already zoomed, canvas coordinates are scaled below.
            # Convert the real text bounds back to diagram units first.
            x, y = canvas.coords(item)
            scale = self.zoom
            center = (x+((bounds[0]+bounds[2])/2-x)/scale,
                      y+((bounds[1]+bounds[3])/2-y)/scale)
            size = ((bounds[2]-bounds[0])/scale, (bounds[3]-bounds[1])/scale)
            position, box = place_label(center, size, occupied, segments)
            canvas.move(item, position[0]-center[0], position[1]-center[1])
            occupied.append(box)
        if groups:
            canvas.tag_lower("relationship-line", "class-card")

    def _relationship_card_bounds(self, bounds):
        # Cards store the centreline of their outline. Attach to its painted
        # outer edge, using canonical metrics shared by the view and export.
        inset = max(1, int(2*self.diagram_scale+.5)) / 2
        left, top, right, bottom = bounds
        return left-inset, top-inset, right+inset, bottom+inset

    def _draw_relationship(self, relation, lane):
        canvas = self.canvas
        start_bounds = self._relationship_card_bounds(self.cards[relation["start"]])
        end_bounds = self._relationship_card_bounds(self.cards[relation["end"]])
        points = association_points(start_bounds, end_bounds, lane)
        if relation['start'] == relation['end']:
            points = self_relationship_points(start_bounds, lane, relation.get('bend',0))
        elif relation.get('bend'):
            points = curved_points(start_bounds, end_bounds, relation['bend'])
        selected = relation["id"] == self.editor.selection and not self.exporting
        color = self._color(SELECT) if selected else self._color(EDGE)
        text_color = self._color(SELECT) if selected else self._color(INK)
        thickness = 3 if selected else 1.5
        tags = ("drawing", "relationship:" + relation["id"])
        canvas.create_line(*(coordinate for point in points for coordinate in point),
                           fill=color, width=thickness, joinstyle="round",
                           dash=(7, 5) if relation["kind"] == "realization" else (),
                           tags=(*tags, "relationship-line", "relationship-geometry"))
        if relation["label"]:
            first, last = (points[len(points)//2-1],points[len(points)//2]) if relation.get('bend') else max(
                zip(points, points[1:]), key=lambda pair: hypot(pair[1][0]-pair[0][0], pair[1][1]-pair[0][1]))
            x, y = (first[0]+last[0])/2, (first[1]+last[1])/2
            vertical = abs(last[1]-first[1]) > abs(last[0]-first[0])
            self.relationship_labels.append(canvas.create_text(x+6 if vertical else x, y if vertical else y-5,
                               anchor="w" if vertical else "s", text=relation["label"],
                               font=self.diagram_normal, fill=text_color, tags=tags))
        kind = relation["kind"]
        symbol_end = "end" if kind in ("inheritance", "realization") else "start" if kind != "association" else None
        for key, first, next_point in (("start", points[0], points[1]), ("end", points[-1], points[-2])):
            if key == symbol_end:
                shape = endpoint_symbol(kind, first, next_point, scale=context_for(self).state.ui_scale)
                if shape:
                    hollow_fill = canvas.cget("background") if self._colors and not self.monochrome else "white"
                    symbol_tags = ("relationship-filled",) if kind == "composition" else ()
                    if self._dark_monochrome and kind != "composition":
                        symbol_tags = ("relationship-hollow",)
                    canvas.create_polygon(*shape, fill=color if kind == "composition" else hollow_fill,
                                          outline=color, width=thickness, tags=(*tags, "relationship-geometry",
                                          *symbol_tags))
            navigable = relation["direction"] in (key, "both")
            if navigable:
                shape = association_arrow(first, next_point, scale=context_for(self).state.ui_scale)
                if shape:
                    canvas.create_line(*shape, fill=color, width=thickness, tags=(*tags, "relationship-geometry"))
            for suffix, side in (("multiplicity", 1), ("role", -1)):
                text = relation[key + "_" + suffix]
                if text:
                    width = self.layout_normal.measure(text)
                    x, y = multiplicity_position(first, next_point, width, side=side,
                                                 clearance=self.typography.units(18) if key == symbol_end or navigable else 0)
                    self.relationship_labels.append(canvas.create_text(max(width/2+4, x), max(10, y), text=text,
                                       fill=text_color, font=self.diagram_normal, tags=tags))

    def _relationship_at(self, event):
        x, y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
        for item in reversed(self.canvas.find_overlapping(x-5, y-5, x+5, y+5)):
            for tag in self.canvas.gettags(item):
                if tag.startswith("relationship:"):
                    return tag.split(":", 1)[1]
        return None

    def _start_relationship(self, cid):
        self.relationship_origin = cid
        self.relationship_hint_dismissed = False
        x, y = self.canvas.winfo_pointerxy()
        self.relationship_pointer = x-self.canvas.winfo_rootx(), y-self.canvas.winfo_rooty()
        self.canvas.focus_set()
        self._update_intro()

    def _draw_relationship_preview(self):
        canvas = self.canvas
        tag = "relationship-preview"
        canvas.delete(tag)
        bounds = self.cards.get(self.relationship_origin)
        if self.exporting or bounds is None or self.relationship_pointer is None:
            return
        x, y = self.relationship_pointer
        x = canvas.canvasx(max(0, min(x, canvas.winfo_width()-1)))
        y = canvas.canvasy(max(0, min(y, canvas.winfo_height()-1)))
        bounds = self._relationship_card_bounds(bounds)
        scaled = tuple(value*self.zoom for value in bounds)
        if scaled[0] <= x <= scaled[2] and scaled[1] <= y <= scaled[3]:
            points = self_relationship_points(bounds)
            coordinates = tuple(value*self.zoom for point in points for value in point)
        else:
            start = card_edge_toward(scaled, (x, y))
            coordinates = (*start, x, y)
        canvas.create_line(*coordinates, fill=self._color(SELECT), width=2, dash=(6, 4), tags=tag)
        if canvas.find_withtag(DiagramHint.TAG):
            canvas.tag_lower(tag, DiagramHint.TAG)

    def _edit_selected_relationship(self):
        relation = next(item for item in self.editor.document["relationships"] if item["id"] == self.editor.selection)
        self.editor.edit_relationship(relation["start"], relation["end"], relation=relation)

    def _update_intro(self):
        self._draw_relationship_preview()
        text = ""
        objects = getattr(get_workbench(), "_thonny_se_objects", None)
        if not self.exporting and self.editing is None:
            if self.relationship_origin in self.cards:
                if not self.relationship_hint_dismissed:
                    text = tr('Click the target class (or the same class) · Esc to cancel')
            elif self.editor.execution_hint_visible:
                text = tr('Before instantiating objects, click')
            elif not self.editor.document["classes"] and not self.editor.document["comments"]:
                if not self.intro_context_seen:
                    text = tr('Right-click for the context menu')
            elif not self.intro_edit_seen:
                text = tr('Double-click a class row to edit it')
        image = None
        if text and self.editor.execution_hint_visible and self.relationship_origin not in self.cards:
            self.run_hint_image = get_workbench().get_image('run-current-script')
            image = self.run_hint_image
        self.info_hint.show(text, image=image)

    def dismiss_click_hint(self, event=None):
        self.editor.execution_hint_visible = False
        objects = getattr(get_workbench(), "_thonny_se_objects", None)
        if objects is not None and objects.session_hint_diagram is self:
            objects.session_hint = False
        if self.editor.document["classes"] or self.editor.document["comments"]:
            self.intro_edit_seen = True
        if self.relationship_origin is not None:
            self.relationship_hint_dismissed = True
        self._update_intro()

    def _draw_member(self, card, section, row, y, tags):
        canvas = self.canvas
        u = self.typography.units
        left = card["x"] + self._space(u(8))
        center = y + self.row_height/2
        visibility = member_visibility(row, section)
        selected = (self.member_selection == (card['id'], section, row['id'])
                    and self.editor.selection == card['id'] and self.editing is None and not self.exporting)
        monochrome_ink = DARK_MONOCHROME_INK if self._dark_monochrome else "#000000"
        icon_color = self._color(SELECT) if selected else monochrome_ink if self.monochrome else self._color(MUTED)
        row_tags = (*tags, 'member-row:'+card['id']+':'+row['id'])
        icon_tags = (*row_tags, 'selected-member-icon') if selected else row_tags
        from .uml_python_semantics import abstract_method
        face = self.diagram_abstract_method if section == 'methods' and abstract_method(card,row) else self.diagram_normal
        if section == "methods" and is_constructor(row):
            symbol_item = canvas.create_text(left+u(12), center, text="c", font=self.diagram_normal, fill=icon_color, tags=(*icon_tags, "member-prefix"))
        else:
            symbol_item = draw_visibility_icon(canvas, left+u(12), center, visibility, self.diagram_normal, self.zoom*context_for(self).state.ui_scale,
                                 tags=icon_tags, color=icon_color, vector=self.exporting)
        self._symbol_items.append((symbol_item, (card['id'], section, row['id'])))
        parts = member_parts(row, section, card['name'])
        name_item = canvas.create_text(left+u(28), center, anchor="w", text=''.join(parts.values()),
                           font=face, fill=self._color(INK), tags=(*row_tags, "member-label"))
        name = parts['name']
        self._name_items.append((name_item, (card['id'], section, row['id']), name, face))

    def _position_member(self):
        self._position_comment()
        canvas = self.canvas
        canvas.delete("member-drag-preview")
        editor = getattr(self, "member_editor", None)
        entry = getattr(self, "input", None)
        if (editor is None and entry is None) or self.editing not in self.fields:
            clear_shapes(canvas,"member-panel-surface")
            self._member_surface_key=None
            return
        left, top, right, bottom = (value*self.zoom for value in self.fields[self.editing])
        # The native widget is inset from its drawn surround. Reserve that
        # surround plus its stroke on every viewport edge, including at HiDPI.
        margin = self.typography.units(6)+self.typography.units(3)
        max_width = max(1, canvas.winfo_width()-2*margin)
        max_height = max(1, canvas.winfo_height()-2*margin)
        min_x, min_y = canvas.canvasx(0)+margin, canvas.canvasy(0)+margin
        max_x = min_x + max_width
        minimum_width = (right-left)*1.18
        grip = getattr(editor, "grip", None)
        if grip is not None and editor.reorder_mode:
            self._position_grip_preview(editor, grip, top, min_x, min_y, max_x, max_height)
            return

        center = (left+right)/2
        if editor is None:
            width = min(max_width, self.input_frame.winfo_reqwidth())
            height = self.input_frame.winfo_reqheight()
            widget = self.input_frame
        else:
            width, height = editor.preferred_size(max_width, minimum_width, max_height)
            widget = editor
        height = min(max_height, height)
        x = max(min_x, min(center-width/2, max_x-width))
        y = max(min_y, min((top+bottom-height)/2, min_y+max_height-height))
        self._place_editor(widget, x, y, width, height)

    def _place_editor(self, widget, x, y, width, height):
        # Native geometry is integral; draw its surround from these same bounds.
        placement=(round(x-self.canvas.canvasx(0)),round(y-self.canvas.canvasy(0)),round(width),round(height))
        x, y = self.canvas.canvasx(placement[0]), self.canvas.canvasy(placement[1])
        width, height = placement[2:]
        if hasattr(widget,'_panel_surface'):
            fill,accent=widget._panel_surface
            gap=self.typography.units(6)
            radius=self.typography.units(12)
            # Snapped vector coordinates depend on the backing pixel density.
            # A display change must invalidate the contour even without a move.
            key=(x,y,width,height,fill,accent,gap,radius,context_for(self).state)
            if (getattr(self,'_member_surface_key',None)!=key
                    or not self.canvas.find_withtag('member-panel-surface')):
                clear_shapes(self.canvas,'member-panel-surface')
                rounded(self.canvas,x-gap,y-gap,x+width+gap,y+height+gap,
                        radius=radius,fill=fill,outline=accent,group='member-panel-surface')
                self._member_surface_key=key
            self.canvas.tag_raise('member-panel-surface')
        if getattr(widget,'_se_last_placement',None)!=placement or widget.winfo_manager()!='place':
            widget.place(in_=self.canvas,x=placement[0],y=placement[1],width=placement[2],height=placement[3])
            widget._se_last_placement=placement
        tk.Misc.tkraise(widget)  # Canvas.lift raises items, not the widget.

    def repaint_after_overlay(self):
        def redraw():
            if self.winfo_exists() and self.winfo_ismapped():
                self.draw()

        get_workbench().after_idle(redraw)

    def _position_grip_preview(self, editor, grip, top, min_x, min_y, max_x, max_height):
        canvas = self.canvas
        tag = "member-drag-preview"
        card_left, _, card_right, _ = (value*self.zoom for value in self.cards[editor.cid])
        width = grip.winfo_reqwidth()+2*PANEL_INSET
        height = grip.winfo_reqheight()+8
        anchor_x, anchor_y = editor.reorder_anchor
        x = max(min_x, min(canvas.canvasx(anchor_x), max_x-width))
        y = max(min_y, min(canvas.canvasy(anchor_y), min_y+max_height-height))
        self._place_editor(editor, x, y, width, height)
        directions = (-1, 1) if not editor.can_reorder() else (grip.direction,) if grip.direction else ()
        for direction in directions:
            center = x+width/2
            arrow_y = y-34 if direction < 0 else y+height+34
            arrow_y = max(min_y+15, min(arrow_y, min_y+max_height-15))
            direction_arrow(canvas, center, arrow_y, direction, 30, self._color(SELECT), tags=tag)
            if not editor.can_reorder():
                canvas.create_line(center-17, arrow_y+17, center+17, arrow_y-17,
                                   fill=self._color(SELECT), width=3, tags=tag)
        if grip.preview_row is not None:
            _, target_top, _, target_bottom = self.fields[editor.cid, editor.section, grip.preview_row]
            line_y = (target_top-2)*self.zoom if target_top*self.zoom < top else (target_bottom+2)*self.zoom
            canvas.create_line(card_left+3, line_y, card_right-3, line_y, fill=self._color(SELECT), width=SELECTION_WIDTH, tags=tag)
            for endpoint in (card_left+3, card_right-3):
                canvas.create_oval(endpoint-3, line_y-3, endpoint+3, line_y+3, fill=self._color(SELECT), outline="", tags=tag)

    def snapshot(self):
        self.flush_diagram_scale()
        from types import SimpleNamespace
        from .imageexport import canvas_scene
        hidden = UmlCanvas(self, SimpleNamespace(document=self.editor.document, selection=None))
        try:
            hidden.exporting = True
            hidden.diagram_scale = self.diagram_scale
            hidden.row_height = self.row_height
            # Export uses the same canonical layout metrics as the view;
            # displayed glyphs alone are fitted to the target pixel grid.
            for target, source in ((hidden.normal, self.normal), (hidden.bold, self.bold),
                                   (hidden.abstract, self.abstract), (hidden.method_abstract, self.method_abstract),
                                   (hidden.display_normal, self.normal), (hidden.display_bold, self.bold),
                                   (hidden.display_abstract, self.abstract),
                                   (hidden.display_method_abstract, self.method_abstract)):
                target.configure(**source.actual())
            hidden._export_widths = {card['id']: hidden._card_width(card, hidden._methods(card))
                                     for card in self.editor.document['classes']}
            hidden.draw()
            bounds = hidden.canvas.bbox("drawing")
            if bounds is None:
                raise ValueError(tr('The UML diagram is empty.'))
            left, top, right, bottom = bounds
            hidden.canvas.move("drawing", 16-left, 16-top)
            return canvas_scene(hidden.canvas, right-left+32, bottom-top+32)
        finally:
            hidden.destroy()

    def begin_edit(self, cid, section="name", row=None, before=None):
        if section=="methods" and row is not None and not any(r["id"]==row for r in self.editor.card(cid)["methods"]):
            return
        deleting = self.delete_mode and section in ("attributes", "methods") and row is not None
        if not self.finish_edit():
            return
        self.delete_mode = deleting
        self.drag = None
        self.canvas.configure(cursor="")
        self.editor.selection = cid
        self.editor._multi_selection = set()
        self.editing = (cid, section, row)
        self.intro_edit_seen = True
        self._update_intro()
        if deleting:
            self.member_editor = DeleteMemberPanel(self, cid, section, row)
            self.member_editor.update_idletasks()
            self.draw()
            self.member_editor.switch.focus_set()
            return
        if section in ("attributes", "methods"):
            self.member_editor = InlineMemberEditor(self, cid, section, row)
            self.draw()
            self.member_editor.name_entry.focus_set()
            self.member_editor.name_entry.selection_range(0, "end")
            return
        self.before = before
        card = self.editor.card(cid)
        self.original_text = card["name"]
        self.input_frame = tk.Frame(self)
        header_panel = edit_panel(self.input_frame, section="name", color=self._color)
        self.navigation_arrow(header_panel, -1).pack(side="top")
        self.navigation_arrow(header_panel, 1).pack(side="bottom")
        self.original_header, self.header_baseline = self.editor.class_header_settings(cid)
        self.original_kind = tr(CLASS_KINDS[card.get("class_kind", "class")])
        self.header_kind = tk.StringVar(self.input_frame, value=self.original_kind)
        self.header_bases = tk.StringVar(self.input_frame, value=self.original_header["bases"])
        header_controls = tk.Frame(header_panel, background=self._color(UML_SECTION_FILLS["name"]))
        header_controls.pack(fill="x", padx=8, pady=4)
        panel_badge(header_controls, "name", self.display_bold, color=self._color).pack(side="left", padx=(0, 6))
        kind_frame, kind_field = header_picker(header_controls, self.header_kind, tuple(tr(label) for label in CLASS_KINDS.values()), width=16, color=self._color)
        kind_frame.pack(side="left", padx=(0, 5))
        self.input = tk.Text(header_controls, width=12, height=1, wrap="none", undo=True, borderwidth=0,
                             background=self._color("white"), foreground=self._color(INK), insertbackground=self._color(INK),
                             cursor="xterm", font=self.display_bold, padx=5, pady=2)
        self.input.pack(side="left", fill="x", expand=True)
        tk.Label(header_controls, text=tr('inherits from'), background=self._color(UML_SECTION_FILLS["name"]), foreground=self._color(INK),
                 padx=7).pack(side="left")
        choices = ("", *(item.get("header", {}).get("name", item["name"])
                         for item in self.editor.document["classes"] if item["id"] != cid))
        bases_frame, bases_field = header_picker(header_controls, self.header_bases, choices, width=13, editable=True, color=self._color)
        bases_frame.pack(side="left")
        for field in (kind_field, bases_field):
            field.bind("<Return>", lambda event: self._commit_event())
            field.bind("<KP_Enter>", lambda event: self._commit_event())
            field.bind("<Escape>", lambda event: self._cancel_event())
        for variable in (self.header_kind, self.header_bases):
            variable.trace_add("write", lambda *args: self.editor.update_title())
        self.scrolling.bind(self.input_frame)
        self.bind_row_navigation(self.input)
        self.input_feedback = FieldFeedback(self.input, tr('Class name'))
        self.input.insert("1.0", self.original_text)
        self.input.edit_reset()
        self.input.edit_modified(False)
        self.input.bind("<Button-1>", self.dismiss_click_hint, add=True)
        self.input.bind("<Return>", lambda e: self._commit_event())
        self.input.bind("<KP_Enter>", lambda e: self._commit_event())
        self.input.bind("<Escape>", lambda e: self._cancel_event())
        def focus_field(widget):
            widget.focus_set()
            return "break"

        kind_field.bind("<Tab>", lambda event: focus_field(self.input))
        self.input.bind("<Tab>", lambda event: focus_field(bases_field))
        bases_field.bind("<Tab>", lambda event: self._tab(1))
        for key in ("<Shift-Tab>", "<ISO_Left_Tab>"):
            kind_field.bind(key, lambda event: self._tab(-1))
            self.input.bind(key, lambda event: focus_field(kind_field))
            bases_field.bind(key, lambda event: focus_field(self.input))
        self.input.bind("<<Modified>>", self._modified)
        self.input_frame.update_idletasks()
        self.draw()
        self.input.focus_set()
        self.input.tag_add("sel", "1.0", "end-1c")
        self.input.mark_set("insert", "end-1c")
        self.after_idle(self._position_member)

    def _modified(self, event):
        if self.input is None or not self.input.edit_modified():
            return
        text = self.input.get("1.0", "end-1c")
        normalized = initial_upper(text)
        if self.editing[1] == "name" and text != normalized:
            caret = self.input.index("insert")
            self.input.delete("1.0", "end")
            self.input.insert("1.0", normalized)
            self.input.mark_set("insert", caret)
        self.input.edit_modified(False)
        self.input_feedback.set_error()
        self.editor.update_title()
        get_workbench()._update_toolbar()

    def begin_comment(self, note, *, new):
        if self.comment_note is note or not self.finish_edit():
            return
        self.comment_note, self.new_comment = note, new
        self.comment_selection = self.editor.selection
        self.editor.selection = note["id"]
        self.comment_input = tk.Text(self, wrap="word", undo=True, borderwidth=0,
                                     background=self._color(HINT_FILL), foreground=self._color(INK), insertbackground=self._color(INK),
                                     font=self.display_normal, padx=2, pady=2)
        self.scrolling.bind(self.comment_input)
        self.comment_feedback = FieldFeedback(self.comment_input, tr('Ctrl+Enter to apply · Esc to cancel'))
        self.comment_input.insert("1.0", note["text"])
        self.comment_input.edit_reset()
        self.comment_input.edit_modified(False)
        self.comment_input.bind("<<Modified>>", self._comment_modified)
        for key in ("<Control-Return>", "<Command-Return>", "<Control-KP_Enter>", "<Command-KP_Enter>"):
            self.comment_input.bind(key, lambda event: self._commit_event())
        self.comment_input.bind("<Escape>", lambda event: self._cancel_event())
        self.draw()
        self.comment_input.focus_set()

    def _comment_modified(self, event):
        if self.comment_input is not None and self.comment_input.edit_modified():
            self.comment_input.edit_modified(False)
            self.comment_feedback.set_error()
            self.editor.update_title()

    def _finish_comment(self, cancel):
        note, widget = self.comment_note, self.comment_input
        text = widget.get("1.0", "end-1c").strip()
        if not cancel and (len(text) > 1000 or "\0" in text or (not text and not self.new_comment)):
            self.comment_feedback.set_error(tr('Please enter a comment of 1 to 1000 characters.'))
            widget.focus_set()
            return False
        self.comment_note = self.comment_input = None
        widget.destroy()
        self.repaint_after_overlay()
        if cancel or not text:
            self.editor.selection = self.comment_selection
            self.editor._refresh()
            return True
        before = self.editor._snapshot()
        before = before[0], self.comment_selection
        note["text"] = text
        if self.new_comment:
            self.editor.document["comments"].append(note)
        self.editor._record(before)
        return True

    def _position_comment(self):
        if self.comment_input is None:
            return
        bounds = self.notes.get(self.comment_note["id"])
        if bounds is None:
            return
        x, y, right, bottom = (value*self.zoom for value in bounds)
        inset = 8*self.zoom
        self._place_editor(self.comment_input, x+inset, y+inset,
                           max(1, right-x-3*inset), max(1, bottom-y-2*inset))

    def pending(self):
        if self.comment_input is not None:
            return self.comment_input.get("1.0", "end-1c").strip() != self.comment_note["text"]
        if self.member_editor is not None:
            return self.member_editor.dirty
        return self.input is not None and (
            self.before is not None or self.input.get("1.0", "end-1c") != self.original_text
            or self.header_kind.get() != self.original_kind
            or self.header_bases.get() != self.original_header["bases"]
        )

    def finish_edit(self, cancel=False):
        if self.comment_input is not None:
            return self._finish_comment(cancel)
        if self.member_editor is not None:
            result = self.member_editor.commit(cancel=cancel)
            if result and self.delete_mode:
                self.delete_mode = False
                self.draw()
            return result
        if self.input is None:
            return True
        cid, section, row_id = self.editing
        before = self.before if self.before is not None else self.editor._snapshot()
        text = self.input.get("1.0", "end-1c").strip()
        if not cancel:
            try:
                self.editor.validate_text(cid, section, text)
                kind = next(key for key, label in CLASS_KINDS.items() if tr(label) == self.header_kind.get())
                candidate = self.editor.changed_class_header(
                    cid, text, self.original_header, self.header_baseline, self.header_bases.get().strip(), kind
                )
            except ValueError as exc:
                self.input_feedback.set_error(str(exc))
                self.input.focus_set()
                return False
        self.input_frame.destroy()
        self.repaint_after_overlay()
        self.input, self.editing = None, None
        if cancel:
            if self.before is not None:
                self.editor.document, self.editor.selection = before
            self.editor._refresh()
            return True
        for current in self.editor.document['classes']:
            updated = next(card for card in candidate['classes'] if card['id'] == current['id'])
            if current != updated:
                current.clear()
                current.update(updated)
        self.editor.document["relationships"] = candidate["relationships"]
        self.editor._record(before)
        return True

    def toggle_delete_mode(self):
        if self.editing is None or self.editing[1] == "name" or self.editing[2] is None:
            return
        current = self.editing
        enable = not self.delete_mode
        if self.finish_edit():
            self.delete_mode = enable
            self.begin_edit(*current)

    def delete_current_member(self):
        if not self.delete_mode or self.editing is None:
            return
        cid, section, row_id = self.editing
        order = self._edit_order(cid)
        index = order.index(self.editing)
        neighbors = order[index+1:] + list(reversed(order[:index]))
        before = self.editor._snapshot()
        card = self.editor.card(cid)
        self.finish_edit()
        card[section] = [item for item in card[section] if item["id"] != row_id]
        if section == "attributes":
            card["methods"] = [item for item in card["methods"]
                               if item.get("accessor", {}).get("attribute") != row_id]
        self.editor._record(before)
        self.delete_mode = True
        remaining = self._edit_order(cid)
        target = next((row for row in neighbors if row in remaining), None)
        if target is None:
            self.delete_mode = False
            self.canvas.focus_set()
        else:
            self.begin_edit(*target)

    def _edit_order(self, cid):
        card = self.editor.card(cid)
        fields = [(cid, "name", None)]
        for section in ("attributes", "methods"):
            fields.extend((cid, section, row["id"]) for row in (card[section] if section=="attributes" else self._methods(card)))
            fields.append((cid, section, None))
        return [field for field in fields if field[2] is not None] if self.delete_mode else fields

    def bind_row_navigation(self, widget):
        widget.bind("<Up>", lambda event: self._navigate_row(-1))
        widget.bind("<Down>", lambda event: self._navigate_row(1))

    def navigation_arrow(self, parent, direction):
        accent, hover = (ERROR, "#8f2019") if self.delete_mode else (SELECT, "#124e9e")
        background = parent.cget("background")
        color = self._color if self.editing is not None and self.editing[1] == "name" else ui_color
        accent, hover = color(accent), color(hover)
        arrow = tk.Canvas(parent, width=42, height=ROW_ARROW_HEIGHT, background=background, highlightthickness=0)
        enabled = self._adjacent_row(direction) is not None or (
            direction > 0 and not self.delete_mode and self.editing is not None
            and self.editing[1] in ('attributes','methods') and self.editing[2] is None)

        def draw(event):
            arrow.delete("all")
            x, y = event.width/2, event.height/2
            disabled = color(DISABLED)
            draw_chevron(arrow, x, y, direction, accent if enabled else disabled,
                         tags=("chevron", "insert"))

        arrow.bind("<Configure>", draw)
        if enabled:
            create_tooltip(arrow, tr('Previous row (↑)') if direction < 0 else tr('Next row (↓)'))
            arrow.bind("<Enter>", lambda event: arrow.itemconfigure("chevron", fill=hover), add=True)
            arrow.bind("<Leave>", lambda event: arrow.itemconfigure("chevron", fill=accent), add=True)
            arrow.bind("<Button-1>", lambda event: self._navigate_row(direction))
        return arrow

    def _adjacent_row(self, direction):
        if self.editing is None:
            return None
        order = self._edit_order(self.editing[0])
        index = order.index(self.editing) + direction
        return order[index] if 0 <= index < len(order) else None

    def _navigate_row(self, direction):
        current = self.editing
        if current is None:
            return "break"
        before = self._edit_order(current[0])
        previous_index = before.index(current)
        deleting = self.delete_mode
        if not self.finish_edit():
            return "break"
        self.delete_mode = deleting
        order = self._edit_order(current[0])
        # Committing a new member inserts it immediately before the add-row.
        # Navigate from that new member, rather than the old add-row position.
        anchor = current
        if current[2] is None and current[1] in ('attributes','methods'):
            anchor = next((field for field in order if field[1] == current[1]
                           and field[2] is not None and field not in before), current)
        index = (order.index(anchor)+direction if anchor in order
                 else previous_index if direction > 0 else previous_index-1)
        if 0 <= index < len(order):
            self.begin_edit(*order[index])
        elif current in order:
            self.begin_edit(*current)
        return "break"

    def _tab(self, direction):
        current = self.editing
        if current is None:
            return "break"
        old_order = self._edit_order(current[0])
        old_index = old_order.index(current)
        deleting = self.delete_mode
        if not self.finish_edit():
            return "break"
        self.delete_mode = deleting
        order = self._edit_order(current[0])
        # Leere vorhandene Zeilen können beim Übernehmen entfernt werden.
        if current in order:
            index = order.index(current) + direction
        else:
            index = old_index if direction > 0 else old_index - 1
        self.begin_edit(*order[index % len(order)])
        return "break"

    def _commit_event(self):
        if self.finish_edit():
            self.canvas.focus_set()
        return "break"

    def _cancel_event(self):
        self.dismiss_click_hint()
        self.finish_edit(cancel=True)
        self.canvas.focus_set()
        return "break"

    def _save_at(self, event):
        x, y = self.point(event)
        return next(((cid, region[4]) for cid, region in self.save_regions.items()
                     if region[0] <= x <= region[2] and region[1] <= y <= region[3]), None)

    def _hover(self, event):
        from .uml_source_status import MESSAGES
        add = self._add_at(event)
        if add is not None:
            self.save_tip.request(ADD_LABELS[add[1]], event.x_root, event.y_root, key=('add', add))
            self.canvas.configure(cursor="")
            return
        hit = self._save_at(event)
        self.save_tip.request(MESSAGES[hit[1]] if hit else '',event.x_root,event.y_root,key=hit)
        self.canvas.configure(cursor="")
        if self.relationship_origin is not None:
            self.relationship_pointer = event.x, event.y
            self._draw_relationship_preview()

    def _click(self, event):
        add = self._add_at(event)
        if add is not None:
            self.save_tip.hide()
            self.drag = None
            self.begin_edit(*add)
            return 'break'
        save = self._save_at(event)
        if save is not None:
            self.save_tip.hide()
            self.drag = None
            self.editor.persist_class(save[0])
            return 'break'
        self.pending_relationship_edit = False
        self.dismiss_click_hint()
        x, y = self.point(event)
        cid, section, row = self.hit(x, y)
        self.member_selection = self._name_at(x, y)
        note = self._note_at(x, y)
        if cid not in self.editor.selected_class_ids() or note is not None:
            self.editor._multi_selection = set()
        note_bounds = self.notes[note["id"]] if note is not None else None
        self.resize_note_from = None
        if self.editing is not None and note is None and cid and section:
            target = (cid, section, row)
            if self.delete_mode and row is None:
                return "break"
            if target != self.editing:
                self.begin_edit(*target)
            return "break"
        if not self.finish_edit():
            return "break"
        if self.relationship_origin is not None:
            origin = self.relationship_origin
            if cid is not None:
                self.relationship_origin = None
                self._update_intro()
                self.editor.edit_relationship(origin, cid)
            return "break"
        if note is not None and note in self.editor.document["comments"]:
            self.canvas.focus_set()
            self.editor.selection = note["id"]
            left, top, right, bottom = note_bounds
            if x >= right-16 and y >= bottom-16:
                self.resize_note_from = (right-left, bottom-top)
            self.draw()
            self.drag_moved = False
            self.drag = (note["id"], x, y, self.editor._snapshot())
            return "break"
        if cid:
            self.canvas.focus_set()
            self.editor.selection = cid
            self.draw()
            self.drag_moved = False
            self.drag = (cid, x, y, self.editor._snapshot())
        else:
            self.canvas.focus_set()
            relation_id = self._relationship_at(event)
            if relation_id is not None and self.editor.selection == relation_id:
                relation = next(item for item in self.editor.document['relationships'] if item['id'] == relation_id)
                self.relationship_drag = (relation_id,x,y,self.editor._snapshot(),relation.get('bend',0))
            self.editor.selection = relation_id
            self.draw()

    def _double_click(self, event):
        if self._save_at(event) is not None:
            return "break"
        self.relationship_drag=None
        self.dismiss_click_hint()
        self.drag = None
        x, y = self.point(event)
        note = self._note_at(x, y)
        if note is not None:
            self.editor.edit_comment(note=note)
            return "break"
        cid, section, row = self.hit(x, y)
        if self.delete_mode and row is None:
            return "break"
        if cid and section:
            self.begin_edit(cid, section, row)
        elif cid is None:
            relationship = self._relationship_at(event)
            if relationship is not None:
                self.editor.selection = relationship
                relation = next(item for item in self.editor.document['relationships'] if item['id']==relationship)
                self.relationship_drag = (relationship,x,y,self.editor._snapshot(),relation.get('bend',0))
                self.pending_relationship_edit = True
        return "break"

    def _drag(self, event):
        if self.relationship_drag:
            rid,start_x,start_y,before,original = self.relationship_drag
            x,y=self.point(event)
            if hypot(x-start_x,y-start_y)*self.zoom < 3:
                return
            relation=next(item for item in self.editor.document['relationships'] if item['id']==rid)
            bend=dragged_bend(self.cards[relation['start']],self.cards[relation['end']],
                              (x-start_x,y-start_y),original,tolerance=8/self.zoom)
            if bend:
                relation['bend']=bend
            else:
                relation.pop('bend',None)
            self.draw()
            return
        if self.drag:
            cid, start_x, start_y, before = self.drag
            x, y = self.point(event)
            if not self.drag_moved and abs(x-start_x) + abs(y-start_y) < 6:
                return
            self.drag_moved = True
            group = "comments" if cid in self.notes else "classes"
            source = next(c for c in before[0][group] if c["id"] == cid)
            card = next(c for c in self.editor.document[group] if c["id"] == cid)
            if self.resize_note_from is not None:
                for key, size, minimum, delta in zip(
                    ("width", "height"), self.resize_note_from, COMMENT_MIN_SIZE, (x-start_x, y-start_y)
                ):
                    card[key] = min(COMMENT_MAX_SIZE, max(minimum, size+delta))
            else:
                card["x"] = min(1_000_000, max(8, source["x"]+x-start_x))
                card["y"] = min(1_000_000, max(8, source["y"]+y-start_y))
                if group == 'classes':
                    card['x'],card['y']=self.snap_position(card['x'],card['y'])
                    selected = self.editor.selected_class_ids()
                    if len(selected)>1:
                        sources = [c for c in before[0]['classes'] if c['id'] in selected]
                        dx,dy = card['x']-source['x'],card['y']-source['y']
                        dx=max(8-min(c['x'] for c in sources),min(dx,1_000_000-max(c['x'] for c in sources)))
                        dy=max(8-min(c['y'] for c in sources),min(dy,1_000_000-max(c['y'] for c in sources)))
                        positions={c['id']:(c['x']+dx,c['y']+dy) for c in sources}
                        for other in self.editor.document['classes']:
                            if other['id'] in positions:other['x'],other['y']=positions[other['id']]
            self.draw()

    def _release(self, event):
        if self.relationship_drag:
            before=self.relationship_drag[3]
            self.relationship_drag=None
            changed = before[0] != self.editor.document
            if changed:
                self.editor._record(before)
            elif self.pending_relationship_edit:
                self._edit_selected_relationship()
            self.pending_relationship_edit = False
        if self.drag:
            _, _, _, before = self.drag
            self.drag = None
            if self.drag_moved:
                self.editor._record(before)

    def _escape(self, event):
        self.editor._multi_selection = set()
        self.draw()
        self.pending_relationship_edit = False
        if self.relationship_drag:
            self.editor.document,self.editor.selection=self.relationship_drag[3]
            self.relationship_drag=None
            self.editor._refresh()
            return 'break'
        self.dismiss_click_hint()
        if self.delete_mode:
            self.toggle_delete_mode()
            return "break"
        if self.relationship_origin is not None:
            self.relationship_origin = None
            self._update_intro()
        if self.drag:
            self.editor.document, self.editor.selection = self.drag[3]
            self.drag = None
            self.editor._refresh()
            self.canvas.configure(cursor="")
        return "break"

    def _context(self, event):
        self.pending_relationship_edit=False
        self.relationship_drag=None
        from .integration import UML_FILES_LABEL, import_python_uml_files
        from .uml_update_dialog import UPDATE_CLASS_LABEL

        self.intro_context_seen = True
        self.dismiss_click_hint()
        if not self.finish_edit():
            return "break"
        self.drag = None
        self.relationship_origin = None
        x, y = self.point(event)
        note = self._note_at(x, y)
        cid, section, row = self.hit(x, y) if note is None else (None, None, None)
        field = self._name_at(x, y) if cid is not None else None
        if field is not None:
            self.member_selection = field
        elif self.member_selection is not None and self.member_selection[0] != cid:
            self.member_selection = None
        if self.member_selection is not None and self.member_selection[0] == cid:
            _, section, row = self.member_selection
        else:
            section, row = None, None
        relationship = self._relationship_at(event) if cid is None and note is None else None
        selected = self.editor.selected_class_ids()
        if len(selected)>1 and cid is None and note is None and relationship is None:
            cid = self.editor.selection
        if cid not in selected or note is not None or relationship is not None:
            self.editor._multi_selection = set()
        self.editor.selection = note["id"] if note else cid or relationship
        self.draw()
        if hasattr(self, "context_menu"):
            self.context_menu.destroy()
        menu = self.context_menu = tk.Menu(self, tearoff=False)
        workbench = get_workbench()

        def command(label, action, role, enabled=True):
            menu.add_command(label=label, command=action, image=menu_icon(workbench, role),
                             compound="left", state="normal" if enabled else "disabled")

        command(tr('New class'), lambda: self.editor.new_class(x, y), "class.new",
                len(self.editor.document["classes"]) < 200)
        comment_x = self.cards[cid][2]+24 if cid is not None else x
        command(tr('New comment'), lambda: self.editor.edit_comment(comment_x, y, target=cid), "comment.new",
                len(self.editor.document["comments"]) < 200)
        if note is not None:
            command(tr('Edit comment'), lambda: self.editor.edit_comment(note=note), "edit.rename")
        command(UML_FILES_LABEL, lambda: import_python_uml_files(self.editor), "document.open")
        menu.add_separator()
        command(tr('Delete'), self.editor.delete_selection, "edit.delete", self.editor.selection is not None)
        command(tr('Copy'), self.editor.copy_class, "edit.copy", cid is not None)
        command(tr('Cut'), self.editor.cut_class, "edit.cut", cid is not None)
        try:
            self.editor._clipboard_insertion((x,y))
        except (tk.TclError,ValueError,RecursionError,TypeError,KeyError):
            pass
        else:
            command(tr('Paste'), lambda: self.editor.paste_class((x,y)), "edit.paste")
        if relationship is not None:
            menu.add_separator()
            command(tr('Edit relationship …'), self._edit_selected_relationship, "edit.rename")
        if cid is not None:
            menu.add_separator()
            command(tr('Edit class definition …'), lambda: self.editor.edit_class_header(cid), "edit.rename")
            command(tr('Add attribute'), lambda: self.begin_edit(cid, "attributes"), "attribute.add")
            command(tr('Add method'), lambda: self.begin_edit(cid, "methods"), "method.add")
            command(tr('Add relationship …'), lambda: self._start_relationship(cid), "relationship.add",
                    bool(self.editor.document["classes"]))
            linked = "source" in self.editor.card(cid)
            menu.add_separator()
            command(tr('Go to code'), lambda: self.editor.go_to_code(cid,section,row), 'code.goto',
                    linked and (section not in ('attributes','methods') or row is not None))
            menu.add_separator()
            command(tr('Instantiate objects …'), lambda: self.editor.instantiate_class(cid), "object.instantiate",
                    self.editor.card(cid).get('class_kind') not in ('abstract', 'interface')
                    and get_workbench()._thonny_se_objects.session.can_instantiate(self.editor, cid))
            menu.add_separator()
            command(tr('Code from class'), lambda: self.editor.export_python_code(cid), "export.python")
            command(UPDATE_CLASS_LABEL, lambda: self.editor.update_from_python(cid), "import.python", linked)
            command(tr('Update code from class'), lambda: self.editor.update_python_code(cid), "export.python", linked)
            label = tr('Relink Python source file …') if linked else tr('Link Python source file …')
            command(label, lambda: self.editor.update_from_python(cid, reassign=True), "document.open")
        if cid is None and note is None and relationship is None:
            menu.add_separator()
            command(tr('Detect relationships automatically'), self.editor.detect_relationships, "relationship.detect",
                    bool(self.editor.document["classes"]))
            menu.add_separator()
            command(tr('Code from diagram'), self.editor.export_python_code, "export.python",
                    bool(self.editor.document["classes"]))
            linked = any('source' in card for card in [*self.editor.document['classes'], *self.editor.document.get('removed_classes', [])])
            command(tr('Update diagram from code …'), self.editor.update_classes_from_code, 'import.python', linked)
            command(tr('Update code from diagram …'), self.editor.update_code_from_classes, 'export.python', linked)
            command(tr('Relink Python source file …'), self.editor.link_diagram_source, 'document.open',
                    bool(self.editor.document['classes']))
        retina_icons.decorate_menu(menu)
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()
        return "break"
