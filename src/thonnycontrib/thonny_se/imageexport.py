# SPDX-FileCopyrightText: 2026 Sebastian Ladhoff
# SPDX-License-Identifier: GPL-3.0-only
# See LICENSE in the project root for the full license text.

"""SVG und PNG aus denselben Canvas-Primitiven wie die Diagrammansicht."""
from .i18n import tr
import io
from math import hypot
from functools import lru_cache
import os
from pathlib import Path
import xml.etree.ElementTree as ET
from tkinter import font as tkfont

from .canvas import StructogramCanvas
from .model import Selection, active_body
from .storage import write_bytes


def snapshot(diagram, *, monochrome=None):
    hidden = StructogramCanvas(diagram, lambda selection: None, lambda: None)
    try:
        hidden.cat_seed = diagram.cat_seed
        hidden.exporting = True
        hidden.monochrome = diagram.monochrome if monochrome is None else monochrome
        root = next(r for r in diagram.regions if r.selection == Selection())
        hidden.render_width = (root.bounds[2]-root.bounds[0])/diagram.zoom
        document = dict(diagram.document, body=active_body(diagram.document['body']))
        hidden.show(document, Selection())
        canvas = hidden.canvas
        extent = tuple(float(v) for v in canvas.cget('scrollregion').split())
        return canvas_scene(canvas, extent[2], extent[3])
    finally:
        hidden.destroy()



def canvas_scene(canvas, width, height):
    scene = []
    for item in canvas.find_all():
        kind = canvas.type(item)
        fill = canvas.itemcget(item, 'fill')
        tags = canvas.gettags(item)
        # Relationship diamonds/triangles carry meaning through their fill.
        # Keep those distinct from the backgrounds of cards and blocks.
        model_fill = (kind in ('rectangle', 'polygon')
                      and not any(tag.startswith('relationship:') for tag in tags)
                      and not ('cat-head' in tags and fill in ('black', '#000000')))
        data = dict(kind=kind, coords=canvas.coords(item), fill=fill, model_fill=model_fill)
        if kind == 'text':
            font = tkfont.Font(root=canvas, font=canvas.itemcget(item, 'font'))
            text = canvas.itemcget(item, 'text')
            limit = float(canvas.itemcget(item, 'width'))
            lines = []
            for paragraph in text.split('\n'):
                line = ''
                for char in paragraph:
                    if line and limit and font.measure(line+char) > limit:
                        split = line.rfind(' ')
                        if split > 0:
                            lines.append(line[:split])
                            line = line[split+1:]+char
                        else:
                            lines.append(line)
                            line = char
                    else:
                        line += char
                lines.append(line)
            if len(lines) == 1 and ('member-label' in tags or 'member-prefix' in tags):
                data['center_y'] = canvas.coords(item)[1]
                data['alignment_group'] = next((tag for tag in tags if tag.startswith('member-row:')), '')
                if 'member-label' in tags:
                    data['alignment_text'] = text
            bbox = canvas.bbox(item)
            data.update(line_widths=[font.measure(line) for line in lines], lines=lines, x=bbox[0]+1, baseline=bbox[1]+font.metrics('ascent')+1,
                        lineheight=font.metrics('linespace'), family=font.actual('family'), weight=font.actual('weight'),
                        slant=font.actual('slant'),
                        pixels=abs(font.actual('size')) if font.actual('size')<0 else font.actual('size')*canvas.winfo_fpixels('1p'))
        else:
            data['width'] = float(canvas.itemcget(item, 'width'))
            data['outline'] = canvas.itemcget(item, 'outline') if kind != 'line' else data['fill']
        if kind == 'line':
            data['capstyle'] = canvas.itemcget(item, 'capstyle')
            dash = canvas.itemcget(item, 'dash')
            if dash:
                data['dash'] = tuple(map(int, dash.split()))
        scene.append(data)
    references = {item['alignment_group']: item['alignment_text'] for item in scene
                  if item.get('alignment_group') and 'alignment_text' in item}
    for item in scene:
        if item.get('alignment_group') in references:
            item['alignment_text'] = references[item['alignment_group']]
    return width, height, scene


def styled_scene(scene, options):
    if options is None:
        return scene
    width, height, items = scene
    styled = []
    for original in items:
        item = dict(original)
        kind = item['kind']
        background = item.get('model_fill', kind in ('rectangle', 'polygon'))
        if options.monochrome:
            # White polygon interiors encode hollow UML diamonds/triangles.
            # They are semantic fills, not foreground ink to turn black.
            hollow = kind == 'polygon' and item.get('fill', '').lower() in ('white', '#ffffff')
            if item.get('fill'):
                item['fill'] = 'white' if background or hollow else 'black'
            if item.get('outline'):
                item['outline'] = 'black'
        if options.transparent_models and background:
            item['fill'] = ''
        styled.append(item)
    return width, height, styled


@lru_cache(maxsize=128)
def _export_font(size, weight='normal', slant='roman'):
    """One font choice for numeric SVG layout and raster rendering."""
    from PIL import ImageFont
    paths = ['/System/Library/Fonts/Supplemental/Arial.ttf', '/System/Library/Fonts/Helvetica.ttc',
             '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', str(Path(os.environ.get('WINDIR', 'C:/Windows'))/'Fonts/arial.ttf')]
    chosen = next((path for path in paths if Path(path).exists()), None)
    if chosen and (weight, slant) != ('normal', 'roman'):
        base = Path(chosen)
        variants = {
            'Arial.ttf': ('Arial Bold.ttf', 'Arial Italic.ttf', 'Arial Bold Italic.ttf'),
            'DejaVuSans.ttf': ('DejaVuSans-Bold.ttf', 'DejaVuSans-Oblique.ttf', 'DejaVuSans-BoldOblique.ttf'),
            'arial.ttf': ('arialbd.ttf', 'ariali.ttf', 'arialbi.ttf'),
        }.get(base.name)
        if variants:
            index = (weight == 'bold') + 2*(slant == 'italic') - 1
            variant = base.with_name(variants[index])
            if variant.exists():
                chosen = str(variant)
    return ImageFont.truetype(chosen, size) if chosen else ImageFont.load_default(size=size)


@lru_cache(maxsize=256)
def _ink_midpoint(text, weight, slant):
    # Measure at high resolution to avoid small-font hinting/rounding jumps.
    _, top, _, bottom = _export_font(1024, weight, slant).getbbox(text, anchor='ls')
    return (top+bottom)/2048


def _text_baseline(item):
    if 'center_y' not in item:
        return item['baseline']
    text = item.get('alignment_text', item['lines'][0])
    return item['center_y']-_ink_midpoint(text, item.get('weight','normal'), item.get('slant','roman'))*item['pixels']


def svg_content(scene, *, options=None):
    width, height, items = styled_scene(scene, options)
    ns = 'http://www.w3.org/2000/svg'
    ET.register_namespace('', ns)
    root = ET.Element('{'+ns+'}svg', dict(width=str(width), height=str(height), viewBox=f'0 0 {width} {height}'))
    if options is None or not options.transparent_background:
        ET.SubElement(root, 'rect', dict(width='100%', height='100%', fill='white'))
    for item in items:
        kind, coords = item['kind'], item['coords']
        if kind == 'text':
            text = ET.SubElement(root, 'text', {'fill': item['fill'], 'font-family': "Arial, Helvetica, 'DejaVu Sans', sans-serif", 'font-size': str(item['pixels']), 'font-weight': item.get('weight', 'normal')})
            if item.get('slant') == 'italic':
                text.set('font-style', 'italic')
            for i, line in enumerate(item['lines']):
                y = _text_baseline(item)+i*item['lineheight']
                span = ET.SubElement(text, 'tspan', x=str(item['x']), y=str(y))
                widths = item.get('line_widths', ())
                if i < len(widths) and widths[i] > 0:
                    # Explicit advances preserve Tk layout across font fallback
                    # in browsers/Office without truncating the source text.
                    span.set('textLength', str(widths[i]))
                    span.set('lengthAdjust', 'spacingAndGlyphs')
                span.text = line
            continue
        attrs = {'fill': item['fill'] or 'none', 'stroke': item['outline'] or 'none', 'stroke-width': str(item['width'])}
        if kind == 'rectangle':
            x1, y1, x2, y2 = coords
            ET.SubElement(root, 'rect', dict(attrs, x=str(x1), y=str(y1), width=str(x2-x1), height=str(y2-y1)))
        elif kind == 'oval':
            x1, y1, x2, y2 = coords
            ET.SubElement(root, 'ellipse', dict(attrs, cx=str((x1+x2)/2), cy=str((y1+y2)/2),
                                              rx=str((x2-x1)/2), ry=str((y2-y1)/2)))
        elif kind in ('polygon', 'line'):
            attrs['points'] = ' '.join(f'{x},{y}' for x, y in zip(coords[::2], coords[1::2]))
            if kind == 'line':
                attrs['fill'] = 'none'
                attrs['stroke-linecap'] = {'projecting':'square'}.get(item.get('capstyle','butt'),item.get('capstyle','butt'))
                if item.get('dash'):
                    attrs['stroke-dasharray'] = ' '.join(map(str, item['dash']))
            ET.SubElement(root, 'polygon' if kind == 'polygon' else 'polyline', attrs)
    return ET.tostring(root, encoding='utf-8', xml_declaration=True)


def raster_content(scene, width, height, format="PNG", *, options=None):
    from PIL import Image, ImageDraw
    if not (32 <= width <= 8192 and 32 <= height <= 8192 and width*height <= 24_000_000):
        raise ValueError(tr('Width/height: 32–8192 pixels, at most 24 megapixels in total.'))
    sw, sh, items = styled_scene(scene, options)
    # Supersampling bleibt begrenzt, auch bei großen Exporten.
    sampling = 2 if width*height <= 6_000_000 else 1
    transparent = options is not None and options.transparent_background
    image = Image.new('RGBA' if transparent else 'RGB', (width*sampling, height*sampling),
                      (0, 0, 0, 0) if transparent else 'white')
    draw = ImageDraw.Draw(image)
    scale = min(width/sw, height/sh)*sampling
    dx, dy = (width*sampling-sw*scale)/2, (height*sampling-sh*scale)/2
    for item in items:
        coords = [(x*scale+dx, y*scale+dy) for x, y in zip(item['coords'][::2], item['coords'][1::2])]
        kind = item['kind']
        if kind == 'text':
            size = max(1, round(item['pixels']*scale))
            face = _export_font(size, item.get('weight','normal'), item.get('slant','roman'))
            baseline = _text_baseline(item)*scale
            for i, line in enumerate(item['lines']):
                x, y = item['x']*scale+dx, baseline+i*item['lineheight']*scale+dy
                widths = item.get('line_widths', ())
                advance = face.getlength(line)
                target = widths[i]*scale if i < len(widths) else advance
                if advance and abs(target-advance) > .5:
                    left, top, right, bottom = face.getbbox(line, anchor='ls')
                    tile = Image.new('RGBA', (max(1,right-left+4), max(1,bottom-top+4)))
                    ImageDraw.Draw(tile).text((2-left,2-top),line,fill=item['fill'],font=face,anchor='ls')
                    ratio = target/advance
                    tile = tile.resize((max(1,round(tile.width*ratio)),tile.height),Image.Resampling.LANCZOS)
                    position = (round(x+(left-2)*ratio),round(y+top-2))
                    if image.mode == "RGBA":
                        image.alpha_composite(tile,position)
                    else:
                        image.paste(tile,position,tile)
                else:
                    draw.text((x,y), line, fill=item['fill'], font=face, anchor='ls')
        else:
            stroke = max(1, round(item['width']*scale))
            if kind == 'rectangle':
                draw.rectangle(coords, fill=item['fill'] or None, outline=item['outline'] or None, width=stroke)
            elif kind == 'oval':
                draw.ellipse(coords, fill=item['fill'] or None, outline=item['outline'] or None, width=stroke)
            elif kind == 'polygon':
                draw.polygon(coords, fill=item['fill'] or None)
                if item['outline']:
                    draw.line(coords+[coords[0]], fill=item['outline'], width=stroke)
            elif kind == 'line':
                if item.get('dash'):
                    on, off = (max(1, round(value*scale)) for value in item['dash'])
                    phase = 0.0
                    for (x1, y1), (x2, y2) in zip(coords, coords[1:]):
                        length = hypot(x2-x1, y2-y1)
                        distance = 0.0
                        while distance < length:
                            remaining = (on if phase < on else on+off)-phase
                            if remaining < 1e-7:
                                phase = float(on) if phase < on else 0.0
                                continue
                            end = min(length,distance+remaining)
                            if phase < on:
                                points = [(x1+(x2-x1)*part/length,y1+(y2-y1)*part/length) for part in (distance,end)]
                                draw.line(points,fill=item['fill'],width=stroke)
                            phase = (phase+end-distance) % (on+off)
                            distance = end

                else:
                    draw.line(coords, fill=item['fill'], width=stroke)
                    if item.get('capstyle') == 'round':
                        radius=stroke/2
                        for x,y in (coords[0],coords[-1]):
                            draw.ellipse((x-radius,y-radius,x+radius,y+radius),fill=item['fill'])
    if sampling != 1:
        image = image.resize((width, height), Image.Resampling.LANCZOS)
    buffer = io.BytesIO()
    image.save(buffer, format=format, **({"lossless": True} if format == "WEBP" else {}))
    return buffer.getvalue()


def png_content(scene, width, height, *, options=None):
    return raster_content(scene, width, height, options=options)


def export_image(path, scene, size=None, kind=None, *, options=None):
    kind = kind or ("png" if size else "svg")
    content = svg_content(scene, options=options) if kind == "svg" else raster_content(scene, *size, format=kind.upper(), options=options)
    write_bytes(path, content)
