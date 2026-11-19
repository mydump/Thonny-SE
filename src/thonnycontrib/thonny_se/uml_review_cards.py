# SPDX-FileCopyrightText: 2026 Sebastian Ladhoff
# SPDX-License-Identifier: GPL-3.0-only
# See LICENSE in the project root for the full license text.

"""Fixed-width UML cards, aligned change rows and retained selection state."""
import tkinter as tk
from tkinter import font, ttk
from thonny import get_workbench

from .i18n import tr
from .uml_batch import TO_CODE
from .uml_review import review_rows, wrap_lines
from .tooltips import CanvasToolTip, attach_tip

CARD_WIDTH = 300
GAP = 72
MARGIN = 8
TOTAL_WIDTH = 2*CARD_WIDTH+GAP+2*MARGIN
INK = '#263342'
EDGE = '#8995a2'
COLORS = {'same':INK, 'update':'#1764c0', 'add':'#207144', 'delete':'#ac3434', 'conflict':'#8c5a0b', 'blocked':'#8c5a0b'}
FILLS = {'same':'white', 'update':'#edf4ff', 'add':'#f0f8f2', 'delete':'#fff1f0', 'conflict':'#fff7e7', 'blocked':'#fff7e7'}


class TransferChoice(ttk.Frame):
    """Normal checkbox with a separate Lucide direction indicator."""
    def __init__(self, parent, variable):
        super().__init__(parent)
        from .iconregistry import menu_icon
        self.variable = variable
        style = ttk.Style(self)
        style.layout('SE.Review.row.TCheckbutton', [
            ('Checkbutton.padding', {'children': [
                ('Checkbutton.focus', {'children': [
                    ('Checkbutton.indicator', {'sticky': ''})]})]})])
        style.configure('SE.Review.row.TCheckbutton', padding=0)
        self.check = ttk.Checkbutton(self, variable=variable,
                                     style='SE.Review.row.TCheckbutton')
        self.check.pack(side='left')
        if not hasattr(parent, '_se_transfer_arrow'):
            parent._se_transfer_arrow = menu_icon(get_workbench(), 'navigation.forward')
        self.arrow_image = parent._se_transfer_arrow
        self.arrow = tk.Label(self, image=self.arrow_image,
                              background=style.lookup('TFrame', 'background'),
                              borderwidth=0, highlightthickness=0, relief='flat',
                              padx=0, pady=0, takefocus=False)
        self.arrow.pack(side='left')
        self.arrow.bind('<Button-1>', self.toggle)
        self.check.bind('<Return>', self.toggle)
        self.check.bind('<KP_Enter>', self.toggle)

    def toggle(self, event=None):
        self.check.focus_set()
        self.check.invoke()
        return 'break'


def group_choice_style(widget, background, foreground, dark):
    """Neutral checkbox indicators, including a gray cross for mixed groups."""
    style = ttk.Style(widget)
    element = 'SE.Review.Neutral.indicator'
    if element not in style.element_names():
        images = []
        for state in ('empty', 'selected', 'mixed'):
            image = tk.PhotoImage(master=widget, width=18, height=18)
            edge = '#aab2bd' if dark else '#687380'
            fill = '#30343a' if dark else '#ffffff'
            image.put(edge, to=(1, 1, 17, 17))
            image.put(fill, to=(2, 2, 16, 16))
            def stroke(points):
                for x,y in points:
                    image.put(edge, to=(x,y,x+2,y+2))
            if state == 'mixed':
                stroke([(x,x) for x in range(5,12)])
                stroke([(x,16-x) for x in range(5,12)])
            elif state == 'selected':
                stroke([(4+i,8+i) for i in range(3)])
                stroke([(7+i,11-i) for i in range(6)])
            images.append(image)
        # Tcl styles retain image names, so their Python wrappers must live too.
        widget.winfo_toplevel()._se_review_choice_images = images
        style.element_create(element, 'image', images[0],
                             ('alternate', images[2]), ('selected', images[1]))
    name = 'SE.Review.Neutral.' + foreground.replace('#','') + '.TCheckbutton'
    style.layout(name, [('Checkbutton.padding', {'sticky':'nswe', 'children':[
        (element, {'side':'left', 'sticky':''}),
        ('Checkbutton.focus', {'side':'left', 'sticky':'w', 'children':[
            ('Checkbutton.label', {'sticky':'nswe'})]})]})])
    style.configure(name, background=background, foreground=foreground)
    style.map(name, background=[('active',background),('!active',background)])
    return name


class CardReview(ttk.Frame):
    def __init__(self, parent, entry, direction, full=False):
        super().__init__(parent)
        self.entry,self.direction,self.full = entry,direction,full
        self.header,self.rows = review_rows(entry,direction)
        self.has_changes = any(row.kind != 'same' for row in [self.header,*self.rows])
        self.normal = font.nametofont('TkDefaultFont').copy()
        self.bold = self.normal.copy();self.bold.configure(weight='bold')
        self.small = self.normal.copy();self.small.configure(size=max(9,self.normal.actual('size')-1))
        self.variables = {}
        self.choices = [] if direction == TO_CODE else {}
        for row in [self.header,*self.rows]:
            if row.selectable:
                variable = tk.BooleanVar(self,value=row.selected)
                self.variables[id(row)] = variable
                if direction == TO_CODE:
                    self.choices.append((row.key,variable))
                else:
                    self.choices[row.key] = variable
        self.group_buttons = {}
        self.groups = ttk.Frame(self)
        self.groups.pack(anchor='w',pady=(0,7))
        labels = {'add':tr('New entries'), 'update':tr('Changes'), 'delete':tr('Deletions'), 'conflict':tr('Conflicts')}
        background = ttk.Style(self).lookup('TFrame','background')
        dark = get_workbench().uses_dark_ui_theme()
        self.muted = '#b5beca' if dark else '#667383'
        group_colors = {'add':'#79c99a','delete':'#f28c87','conflict':'#e4bc6e','update':'#83b5f4'} if dark else COLORS
        for status,label in labels.items():
            active = [self.variables[id(row)] for row in [self.header, *self.rows]
                      if row.selectable and row.status == status]
            if not active:
                continue
            selected = tk.BooleanVar(self)
            style = group_choice_style(self, background, group_colors[status], dark)
            def choose(values=active,choice=selected):
                checked = choice.get()
                for variable in values:
                    variable.set(checked)
            button = ttk.Checkbutton(self.groups,text=label,variable=selected,style=style,command=choose)
            button.pack(side='left',padx=(0,14))
            self.group_buttons[status] = button
            def sync(*args, values=active, choice=selected, control=button):
                chosen = [value.get() for value in values]
                choice.set(all(chosen))
                control.state(['alternate'] if any(chosen) and not all(chosen) else ['!alternate'])
            for value in active:
                value.trace_add('write',sync)
            sync()
        self.canvas = tk.Canvas(self,width=TOTAL_WIDTH,height=100,highlightthickness=0,
                                background=background)
        self.canvas.pack(anchor='center')
        self.canvas.bind('<Button-1>',self._clicked)
        self.tip = CanvasToolTip(self.canvas)
        self.canvas.bind('<Motion>',self._hover)
        self.row_lookup = {id(row):row for row in [self.header,*self.rows]}
        self.checkboxes = []
        self.draw()

    def selection(self):
        if self.direction == TO_CODE:
            return [change for change,variable in self.choices if variable.get()]
        return {key for key,variable in self.choices.items() if variable.get()}

    def set_full(self, full):
        self.full = full
        self.draw()

    def _layout(self,row,header=False):
        face = self.bold if header else self.normal
        left = wrap_lines(row.after,face.measure,CARD_WIDTH-24)
        right = wrap_lines(row.before,face.measure,CARD_WIDTH-24)
        height = max(30, max(len(left),len(right))*face.metrics('linespace')+12)
        return face,left,right,height

    def _pair(self,row,y,layout,header=False):
        face,left,right,height = layout
        canvas = self.canvas
        right_x = MARGIN+CARD_WIDTH+GAP
        row_tag = 'review-row:'+str(id(row))
        for x,text,lines in ((MARGIN,row.after,left),(right_x,row.before,right)):
            status = row.status if text else 'same'
            canvas.create_rectangle(x+1,y,x+CARD_WIDTH-1,y+height,fill=FILLS[status],outline='',tags=(row_tag,))
            for index,(line,inset) in enumerate(lines):
                if not line:
                    continue
                canvas.create_text(x+CARD_WIDTH/2 if header else x+12+inset,y+(height-max(len(left),len(right))*face.metrics('linespace'))/2+index*face.metrics('linespace'),text=line,
                    font=face,fill=COLORS[status],anchor='n' if header else 'nw',tags=('review-text',row.status,row_tag))
        if row.selectable:
            check = TransferChoice(canvas, self.variables[id(row)])
            self.checkboxes.append(check)
            canvas.create_window(MARGIN+CARD_WIDTH+GAP/2,y+height/2,window=check,anchor='center')
            for control in (check, check.check, check.arrow):
                attach_tip(control,lambda row=row:self._tip_text(row))
        return y+height

    def _tip_text(self,row):
        if row.key is None and row.kind != 'same' and row.note:
            return row.note
        explanation = ''
        if row.kind == 'delete':
            variable = self.variables.get(id(row))
            if variable is not None and variable.get():
                explanation = tr('Will be deleted because this entry is no longer present in the source.')
            else:
                explanation = tr('Suggested for deletion because this entry is no longer present in the source. Select it to delete it.')
        elif row.kind == 'add':
            explanation = tr('New entry: present in the source but not yet in the target.')
        elif row.kind == 'update':
            explanation = tr('Changed entry: the source differs from the target.')
        if row.status == 'conflict':
            explanation = tr('Conflict: both versions were edited. Select this entry to replace the target on the right with the source on the left.') + (' ' + explanation if explanation else '')
        elif row.status == 'blocked':
            explanation = tr('Edit directly in Python')
        return ' '.join(part for part in (explanation, row.note) if part)

    def _hover(self,event):
        text = ''
        row_id = None
        for item in reversed(self.canvas.find_overlapping(event.x,event.y,event.x,event.y)):
            tags = self.canvas.gettags(item)
            row_id = next((int(tag.split(':',1)[1]) for tag in tags if tag.startswith('review-row:')),None)
            if row_id is not None:
                text = self._tip_text(self.row_lookup[row_id])
                break
        self.tip.request(text,event.x_root,event.y_root,key=row_id)

    def _clicked(self,event):
        self.tip.hide()
        for item in reversed(self.canvas.find_overlapping(event.x,event.y,event.x,event.y)):
            for tag in self.canvas.gettags(item):
                if tag.startswith('review-row:'):
                    variable = self.variables.get(int(tag.split(':',1)[1]))
                    if variable is not None:
                        variable.set(not variable.get())
                        return 'break'
        return None

    def draw(self):
        for check in self.checkboxes:
            check.destroy()
        self.checkboxes = []
        self.tip.hide()
        canvas = self.canvas;canvas.delete('all')
        top = 4
        y = self._pair(self.header,top,self._layout(self.header,True),True)
        separators = []
        for section in ('attributes','methods'):
            separators.append(y)
            visible = [row for row in self.rows if row.section == section and (self.full or row.kind != 'same')]
            if not visible:
                y += 12
            for row in visible:
                y = self._pair(row,y,self._layout(row))
        for line_y in separators:
            for x in (MARGIN,MARGIN+CARD_WIDTH+GAP):
                canvas.create_line(x,line_y,x+CARD_WIDTH,line_y,fill=EDGE)
        for x in (MARGIN,MARGIN+CARD_WIDTH+GAP):
            background = canvas.create_rectangle(x,top,x+CARD_WIDTH,y,fill='white',outline='')
            canvas.tag_lower(background)
            canvas.create_rectangle(x,top,x+CARD_WIDTH,y,outline=EDGE,width=1)
        if not any(row.kind!='same' for row in [self.header,*self.rows]):
            canvas.create_text(TOTAL_WIDTH/2,y+12,text=tr('No changes for this class.'),font=self.small,
                               fill='#667383',anchor='n')
            y += self.small.metrics('linespace')+16
        canvas.configure(height=y+3)
