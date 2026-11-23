# SPDX-FileCopyrightText: 2026 Sebastian Ladhoff
# SPDX-License-Identifier: GPL-3.0-only
# See LICENSE in the project root for the full license text.

"""Native vector surfaces on Aqua, antialiased bitmaps on other Tk backends."""
from itertools import count
from math import ceil
from PIL import Image, ImageDraw, ImageTk
from functools import lru_cache
from .display_context import context_for


def clear_shapes(canvas, group):
    canvas.delete(group)
    if hasattr(canvas, '_se_smooth_images'):
        canvas._se_smooth_images.pop(group, None)


def _native_vectors(canvas):
    return context_for(canvas).state.native_paths


def _make_rounded_image(width,height,radius,fill,outline,stroke=1):
    scale,pad = 3,2
    image = Image.new('RGBA',((width+2*pad)*scale,(height+2*pad)*scale))
    draw=ImageDraw.Draw(image)
    draw.rounded_rectangle((pad*scale,pad*scale,(width+pad)*scale,(height+pad)*scale),
                          radius=radius*scale,fill=fill,outline=outline,width=max(1,round(stroke*scale)))
    return image.resize((width+2*pad,height+2*pad),Image.Resampling.LANCZOS)


_cached_rounded_image = lru_cache(maxsize=16)(_make_rounded_image)


def _rounded_image(width,height,radius,fill,outline,stroke=1):
    # At most 16 * 512 KiB (~8 MiB) of retained Pillow surfaces. Large
    # full-window panels are transient, not another 1x/2x/3x cache entry.
    if (width+4)*(height+4)*4 <= 512*1024:
        return _cached_rounded_image(width,height,radius,fill,outline,stroke)
    return _make_rounded_image(width,height,radius,fill,outline,stroke)


_rounded_image.cache_info = _cached_rounded_image.cache_info


_shape_ids = count()


def _rounded_vector(canvas, x0, y0, x1, y1, radius, fill, outline, group):
    state = context_for(canvas).state
    stroke = state.ui_scale
    # Tk's native arc bounds are quantized to logical integer coordinates.
    # Keep their straight tangents on that same grid: half-pixel snapping
    # otherwise leaves arc/line joins dependent on the panel's position.
    x0,y0,x1,y1 = (round(value) for value in (x0,y0,x1,y1))
    radius = round(radius)
    radius = max(0, min(radius, (x1-x0)/2, (y1-y0)/2))
    # Tk tessellates smooth polygons through integer XPoints. Native arcs
    # retain their curves instead of rounding every intermediate vertex.
    overlap = min(1, radius)
    shape_tag = f"se-rounded-{next(_shape_ids)}"
    tags = (group, shape_tag)
    canvas.create_rectangle(x0+radius-overlap,y0,x1-radius+overlap,y1,
                                    fill=fill,outline='',tags=tags)
    canvas.create_rectangle(x0,y0+radius-overlap,x1,y1-radius+overlap,fill=fill,outline='',tags=tags)
    corners = ((x0,y0,90),(x1-2*radius,y0,0),
               (x1-2*radius,y1-2*radius,270),(x0,y1-2*radius,180))
    for x,y,start in corners:
        bounds = (x,y,x+2*radius,y+2*radius)
        canvas.create_oval(*bounds,fill=fill,outline='',tags=tags)
        canvas.create_arc(*bounds,start=start,extent=90,style='arc',
                          outline=outline,width=stroke,tags=tags)
    for bounds in ((x0+radius,y0,x1-radius,y0),
                   (x1,y0+radius,x1,y1-radius),
                   (x1-radius,y1,x0+radius,y1),
                   (x0,y1-radius,x0,y0+radius)):
        canvas.create_line(*bounds,fill=outline,width=stroke,tags=tags)
    return shape_tag



def rounded(canvas, x0, y0, x1, y1, *, radius, fill, outline, group):
    if _native_vectors(canvas):
        return _rounded_vector(canvas,x0,y0,x1,y1,radius,fill,outline,group)
    width,height = max(1,ceil(x1-x0)),max(1,ceil(y1-y0))
    image = _rounded_image(width,height,radius,fill,outline,context_for(canvas).state.ui_scale)
    return _place(canvas,image,x0-2,y0-2,group)


def badge(canvas, x, y, *, radius, fill, outline, group, exclamation=False):
    stroke = context_for(canvas).state.ui_scale
    if _native_vectors(canvas):
        circle = canvas.create_oval(x-radius,y-radius,x+radius,y+radius,
                                    fill=fill,outline=outline,width=stroke,tags=(group,))
        if exclamation:
            canvas.create_line(x+2*stroke,y-5*stroke,x,y+stroke,fill=outline,width=3*stroke,
                               capstyle='round',tags=(group,))
            canvas.create_oval(x-2.3*stroke,y+3.5*stroke,x+.7*stroke,y+6.5*stroke,
                               fill=outline,outline='',tags=(group,))
        return circle
    scale,pad=3,2
    size=ceil(2*radius)+2*pad
    image=Image.new('RGBA',(size*scale,size*scale))
    draw=ImageDraw.Draw(image)
    draw.ellipse((pad*scale,pad*scale,(size-pad)*scale,(size-pad)*scale),
                 fill=fill,outline=outline,width=max(1,round(stroke*scale)))
    if exclamation:
        c=size/2
        draw.line(((c+2*stroke)*scale,(c-5*stroke)*scale,c*scale,(c+stroke)*scale),fill=outline,width=max(1,round(3*stroke*scale)))
        for dx,dy,r in ((2,-5,1.5),(0,1,1.5),(-.8,5,1.5)):
            dx,dy,r = dx*stroke,dy*stroke,r*stroke
            draw.ellipse(((c+dx-r)*scale,(c+dy-r)*scale,(c+dx+r)*scale,(c+dy+r)*scale),fill=outline)
    image=image.resize((size,size),Image.Resampling.LANCZOS)
    return _place(canvas,image,x-size/2,y-size/2,group)


def _place(canvas, image, x, y, group):
    if not hasattr(canvas, '_se_smooth_images'):
        canvas._se_smooth_images={}
    photo=ImageTk.PhotoImage(image,master=canvas)
    canvas._se_smooth_images.setdefault(group,[]).append(photo)
    return canvas.create_image(x,y,image=photo,anchor='nw',tags=(group,))


def clear_icon_images(canvas):
    """Release only images belonging to a drawing that its owner has deleted."""
    canvas._se_icon_images = []


def icon(canvas, x, y, role, face, color, *, pixels=None, tags=()):
    """One semantic icon API: native font, then exact-size SVG, then legacy asset."""
    from . import retina_icons
    if retina_icons.enabled(canvas):
        return canvas.create_text(x,y,text=retina_icons.glyph(role),
                                  font=retina_icons.font_for(canvas,face),fill=color,tags=tags)
    from .iconregistry import catalog,icon_path
    from pathlib import Path
    import tkinter as tk
    from collections import OrderedDict
    pixels = min(256,max(8,round(pixels or face.metrics('linespace'))))
    root=canvas._root()
    if not hasattr(root,'_se_svg_images'):root._se_svg_images=OrderedDict()
    cache=root._se_svg_images
    key=(role,pixels,color)
    image=cache.get(key)
    if image is None:
        entry=catalog()['roles'][role]
        while not entry.get('original') and entry.get('fallback'):
            entry=catalog()['roles'][entry['fallback']]
        source=entry.get('original')
        if source and not context_for(canvas).state.native_paths:
            svg=(Path(__file__).with_name('icons')/source).read_text().replace('currentColor',color)
            try:image=tk.PhotoImage(master=canvas,data=svg,format=('svg','-scaletowidth',pixels))
            except tk.TclError:pass
        if image is None:
            from PIL import Image,ImageTk
            with Image.open(icon_path(role,size=16)) as original:
                image=ImageTk.PhotoImage(original.convert('RGBA').resize((pixels,pixels),Image.Resampling.LANCZOS),master=canvas)
        cache[key]=image
        if len(cache)>64:cache.popitem(last=False)
    else:cache.move_to_end(key)
    if not hasattr(canvas,'_se_icon_images'):canvas._se_icon_images=[]
    canvas._se_icon_images.append(image)
    return canvas.create_image(x,y,image=image,tags=tags)
