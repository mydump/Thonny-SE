# SPDX-FileCopyrightText: 2026 Sebastian Ladhoff
# SPDX-License-Identifier: GPL-3.0-only
# See LICENSE in the project root for the full license text.

"""Resolution-independent icons from one private font on verified Tk backends.

The historical module name remains for compatibility. Registration uses a
small backend adapter; callers never select assets based on the OS.
"""
from .i18n import tr
import json
import logging
from functools import lru_cache
from pathlib import Path
from tkinter import font, ttk, TclError

_ROOT=Path(__file__).with_name('icons')


@lru_cache(maxsize=1)
def mapping():
    return json.loads((_ROOT/'font-map.json').read_text(encoding='utf-8'))


def enabled(widget):
    root=widget._root()
    if hasattr(root,'_se_vector_icons'):
        return root._se_vector_icons
    root._se_vector_icons=False
    try:
        from .vector_fonts import register_private
        backend = str(root.tk.call('tk','windowingsystem'))
        register_private(_ROOT/'thonny-se-icons.ttf',backend)
        probe=font.Font(root=root,family=mapping()['family'],size=13)
        # Successful API registration is not sufficient: Tk must actually use it.
        root._se_vector_icons=probe.actual('family')==mapping()['family']
    except (OSError,ValueError,KeyError,RuntimeError,TclError):
        logging.getLogger(__name__).exception(tr('Vector icon font unavailable; using the image renderer'))
    return root._se_vector_icons


def glyph(role):
    from .iconregistry import catalog
    seen=set()
    while role and role not in seen:
        seen.add(role)
        if role in mapping()['roles']:
            return mapping()['roles'][role]
        role=catalog()['roles'][role].get('fallback')
    raise LookupError(tr('No vector glyph: ')+str(role))


def font_for(widget, base='TkDefaultFont'):
    root=widget._root()
    # Canvas callers already own a live Font. Read it directly: allocating
    # and deleting a temporary named Tk font per symbol is unnecessary.
    actual=base.actual() if isinstance(base,font.Font) else font.Font(root=root,font=base).actual()
    key=(actual['size'],actual['weight'],actual['slant'])
    if not hasattr(root,'_se_icon_fonts'):
        root._se_icon_fonts={}
    if key not in root._se_icon_fonts:
        root._se_icon_fonts[key]=font.Font(root=root,family=mapping()['family'],size=key[0],weight=key[1],slant=key[2])
    return root._se_icon_fonts[key]


def plain(text):
    if len(text)>1 and text[1]==' ' and 0xE900<=ord(text[0])<0xEA00:
        return text[1:].lstrip()
    return text


def toolbar(button,role,caption=None):
    if not enabled(button):
        return False
    style=ttk.Style(button)
    base_font=style.lookup('Toolbutton','font') or 'TkDefaultFont'
    target=font_for(button,base_font)
    if str(style.lookup('SE.Vector.Toolbutton','font'))!=str(target):
        style.configure('SE.Vector.Toolbutton',font=target)
    button.configure(image='',style='SE.Vector.Toolbutton',text=glyph(role)+(' '+caption if caption else ''))
    return True


def menu_item(menu,index,role,workbench=None,menu_name=None):
    # Windows menu text must keep its normal text font. The private icon font
    # contains only PUA glyphs; relying on native menu font fallback corrupts
    # accented labels. Callers already supply separate image icons as fallback.
    if str(menu.tk.call('tk', 'windowingsystem')) == 'win32':
        return False
    if not enabled(menu):
        return False
    original=menu.entrycget(index,'label')
    label=plain(original)
    # Tk 9 can return an empty string for an unset mnemonic.
    underline_value = menu.entrycget(index, 'underline')
    underline = -1 if underline_value == '' else int(underline_value)
    if original==label and underline>=0:
        menu.entryconfigure(index,underline=underline+2)
    decorated=glyph(role)+' '+label
    menu.entryconfigure(index,image='',label=decorated,font=font_for(menu,'TkMenuFont'))
    if workbench is not None and (menu_name,label) in workbench._menu_item_specs:
        # Keep Thonnys enable/disable testers and later command insertion working.
        workbench._menu_item_specs[menu_name,decorated]=workbench._menu_item_specs[menu_name,label]
    return True


def remember_image(widget,image,role):
    root=widget._root()
    if not hasattr(root,'_se_menu_image_roles'):
        root._se_menu_image_roles={}
    root._se_menu_image_roles[str(image)]=role


def decorate_menu(menu):
    if str(menu.tk.call('tk', 'windowingsystem')) == 'win32':
        return
    if not enabled(menu):
        return
    roles=getattr(menu._root(),'_se_menu_image_roles',{})
    end=menu.index('end')
    for index in range(end+1 if end is not None else 0):
        if menu.type(index)=='separator':
            continue
        image=menu.entrycget(index,'image')
        if image in roles:
            menu_item(menu,index,roles[image])


def tab(notebook,editor,role):
    if not enabled(notebook):
        return False
    current=notebook.tab(editor,'image')
    owned=getattr(editor,'_thonny_se_tab_icon_image',None)
    if current and (not owned or owned not in notebook.tk.splitlist(current)):
        notebook.tab(editor,text=plain(notebook.tab(editor,'text')))
        editor._thonny_se_tab_icon_state=None
        return True
    if not hasattr(notebook,'_se_base_style'):
        notebook._se_base_style=notebook.cget('style') or 'TNotebook'
    base=notebook._se_base_style
    name='SE.Vector.'+base
    style=ttk.Style(notebook)
    base_font=style.lookup(base+'.Tab','font') or 'TkDefaultFont'
    target=font_for(notebook,base_font)
    if str(style.lookup(name+'.Tab','font'))!=str(target):
        style.configure(name+'.Tab',font=target)
    if notebook.cget('style')!=name:
        notebook.configure(style=name)
    notebook.tab(editor,image='',text=glyph(role)+' '+editor.get_title())
    editor._thonny_se_tab_icon_image=None
    editor._thonny_se_tab_icon_state=(role, None)  # Vector tab text follows the notebook theme directly.
    editor._thonny_se_tab_icon_mode='vector'
    return True
