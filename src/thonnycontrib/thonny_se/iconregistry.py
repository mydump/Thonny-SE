# SPDX-FileCopyrightText: 2026 Sebastian Ladhoff
# SPDX-License-Identifier: GPL-3.0-only
# See LICENSE in the project root for the full license text.

"""Semantische Icon-Namen, unabhängig von Hersteller, Plattform und Dateiname."""
from .i18n import tr
from tkinter import TclError
import json
from functools import lru_cache
from pathlib import Path
from . import retina_icons

_ICON_ROOT = Path(__file__).with_name("icons")


@lru_cache(maxsize=1)
def catalog():
    return json.loads((_ICON_ROOT / "catalog.json").read_text(encoding="utf-8"))


def icon_path(role, *, required=True, dark=False, size=24):
    """Lokale PNG-Ressource für Thonnys get_image/add_command liefern.

    Noch nicht belegte Rollen liefern bei required=False None. Fallbacks sind
    explizit im Katalog; unbekannte Namen und beschädigte Dateien sind Fehler.
    Es gibt keinen Zugriff auf Betriebssystem-Themes oder Downloads zur Laufzeit.
    """
    roles = catalog()["roles"]
    seen = set()
    current = role
    while current is not None:
        if current in seen:
            raise ValueError(tr('Cyclic icon fallback: ') + role)
        seen.add(current)
        entry = roles[current]
        if entry["file"]:
            key = ("dark_" if dark else "")+("menu_" if size==16 else "")+"file"
            path = (_ICON_ROOT / entry.get(key, entry["file"])).resolve()
            if _ICON_ROOT.resolve() not in path.parents or path.suffix.lower() != ".png":
                raise ValueError(tr('Invalid icon resource: ') + role)
            if not path.is_file():
                raise FileNotFoundError(path)
            return str(path)
        current = entry.get("fallback")
    if required:
        raise LookupError(tr('Missing asset for icon role: ') + role)
    return None


def menu_icon(workbench, role, *, dark=None):
    if dark is None:
        dark = workbench.uses_dark_ui_theme()
    image = workbench.get_image(icon_path(role, dark=dark, size=16))
    retina_icons.remember_image(workbench,image,role)
    return image


def tab_role(editor):
    filename = (editor.get_filename() or "").lower()
    if filename.endswith(".uml.json"):
        return "document.uml"
    if filename.endswith(".nsd.json"):
        return "document.structogram"
    if filename.endswith((".png", ".webp", ".svg", ".jpg", ".jpeg", ".gif", ".bmp", ".tif", ".tiff")):
        return "document.image"
    if filename.endswith((".py", ".pyw", ".pyi", ".pyde", ".pyx")) or (
            not filename and getattr(editor.get_text_widget(), "file_type", None) == "python"):
        return "document.python"
    return "document.file"


def update_tab_icon(notebook, editor):
    if not hasattr(editor, "get_filename") or str(editor) not in notebook.tabs():
        return
    from thonny import get_workbench
    workbench = get_workbench()
    if retina_icons.tab(notebook,editor,tab_role(editor)):
        return
    current = notebook.tab(editor, "image")
    previous = getattr(editor, "_thonny_se_tab_icon_state", None)
    # Bereits von einem anderen Plugin gesetzte Tabmotive behalten.
    managed_image = getattr(editor, "_thonny_se_tab_icon_image", None)
    if current and (previous is None or managed_image not in notebook.tk.splitlist(current)):
        editor._thonny_se_tab_icon_state = None
        return
    try:
        dark = workbench.uses_dark_ui_theme()
    except TclError:
        # During theme teardown/rebuild keep the current icon. A later title
        # refresh retries normally instead of failing the whole title update.
        return
    state = (tab_role(editor), dark)
    if state == previous and current:
        return
    image = menu_icon(workbench, state[0], dark=dark)
    notebook.tab(editor, image=image, compound="left")
    editor._thonny_se_tab_icon_image = str(image)
    editor._thonny_se_tab_icon_state = state


def install_theme_updates(workbench, graphics):
    """Nur die Plugin-Motive wechseln; Thonnys eigenes Theme unangetastet lassen."""
    mapping = {"thonny_se_new_uml": "document.uml", "undo": "edit.undo", "redo": "edit.redo", "thonny_se_new": "document.structogram",
               "thonny_se_from_python": "import.python", "thonny_se_uml_from_python": "import.python",
               "thonny_se_graphics": "export.image"}
    mapping.update({"thonny_se_export_"+kind: "export."+kind for kind in ("png", "svg", "webp")})
    pending = None

    def refresh():
        nonlocal pending
        pending = None
        dark = workbench.uses_dark_ui_theme()
        for command in workbench._commands:
            role = mapping.get(command["command_id"])
            if role is None:
                continue
            menu = workbench.get_menu(command["menu_name"])
            for index in range((menu.index("end") or 0)+1):
                if menu.type(index) != "separator" and retina_icons.plain(menu.entrycget(index, "label")) == command["command_label"]:
                    if not retina_icons.menu_item(menu,index,role,workbench,command["menu_name"]):
                        menu.entryconfigure(index, image=menu_icon(workbench, role), compound="left")
                    break
            button = workbench._toolbar_buttons.get(command["command_id"])
            if button is not None:
                caption_below = workbench.in_simple_mode() and command['command_id'] in ('thonny_se_new', 'thonny_se_new_uml')
                caption = command['caption'] if caption_below or command['command_id'].startswith('thonny_se_export_') else None
                if retina_icons.toolbar(button,role,caption,caption_below=caption_below):
                    continue
                path = icon_path(role, dark=dark, size=16)
                normal, disabled = workbench.get_image(path), workbench.get_image(path, disabled=True)
                button.configure(image=[normal, "disabled", disabled] if disabled else normal)
        notebook = workbench.get_editor_notebook()
        if notebook is not None:
            for tab in notebook.tabs():
                update_tab_icon(notebook, notebook.nametowidget(tab))
        for index in range(3):
            if not retina_icons.menu_item(graphics,index,'export.image'):
                graphics.entryconfigure(index, image=menu_icon(workbench, "export.image"), compound="left")

    def schedule(event=None):
        nonlocal pending
        if pending is None:
            pending = workbench.after_idle(refresh)

    workbench.bind("<<ThemeChanged>>", schedule, True)
    from .display_context import context_for
    context_for(workbench).subscribe(workbench,schedule)
    refresh()



def paper_icon(widget, visibility, pixels=16):
    """Exact-size light icon for white diagram paper; avoid host auto-upscaling."""
    import tkinter as tk
    pixels = max(8, min(32, round(pixels)))
    root = widget._root()
    if not hasattr(root, "_thonny_se_paper_icons"):
        root._thonny_se_paper_icons = {}
    key = (visibility, pixels)
    if key not in root._thonny_se_paper_icons:
        name = catalog()["roles"]["visibility."+visibility]["asset_name"]
        root._thonny_se_paper_icons[key] = tk.PhotoImage(master=root, file=str(_ICON_ROOT/f"{name}-paper-{pixels}.png"))
    return root._thonny_se_paper_icons[key]


def draw_visibility_icon(canvas, x, y, visibility, font, zoom, *, tags=(), color=None, vector=False):
    from .ui_style import MUTED

    if vector:
        # Same 16x16 source geometry as the bundled visibility SVGs/font glyphs.
        # Plain vectors keep exports independent of installed icon fonts.
        color = color or MUTED
        scale = zoom
        # Export the same source paths at the actual font-glyph advance used
        # on screen, not at a fixed 16-pixel size beside DPI-scaled text.
        if retina_icons.enabled(canvas):
            face = retina_icons.font_for(canvas, font)
            scale = face.measure(retina_icons.glyph("visibility."+visibility))/16
        circle = canvas.create_oval(x-7*scale,y-7*scale,x+7*scale,y+7*scale,
                                   outline=color, fill='', width=scale, tags=tags)
        paths = {'public': [(-3,0,3,0),(0,-3,0,3)],
                 'private': [(-3,0,3,0)],
                 'protected': [(-1.5,-3.5,-2.5,3.5),(2.5,-3.5,1.5,3.5),
                               (-3.5,-1.5,3.5,-1.5),(-3.5,1.5,3.5,1.5)]}
        for x1,y1,x2,y2 in paths[visibility]:
            canvas.create_line(x+x1*scale,y+y1*scale,x+x2*scale,y+y2*scale,
                fill=color,width=(1.5 if visibility=='protected' else 2)*scale,
                capstyle='round',tags=tags)
        return circle
    from .graphics import icon
    return icon(canvas,x,y,"visibility."+visibility,font,color or MUTED,pixels=16*zoom,tags=tags)
