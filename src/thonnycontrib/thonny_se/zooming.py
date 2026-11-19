# SPDX-FileCopyrightText: 2026 Sebastian Ladhoff
# SPDX-License-Identifier: GPL-3.0-only
# See LICENSE in the project root for the full license text.

"""Keep a document coordinate under the pointer while zooming scrollable axes."""
from dataclasses import dataclass
import math


@dataclass(frozen=True)
class ZoomAnchor:
    logical: tuple[float,float]
    viewport: tuple[float,float]


def event_position(canvas,event):
    """Canvas-relative point, including events from children and negative desktops."""
    try:
        x=float(event.x_root)-canvas.winfo_rootx()
        y=float(event.y_root)-canvas.winfo_rooty()
    except (AttributeError,TypeError,ValueError):
        try:
            widget=event.widget
            x=widget.winfo_rootx()+float(event.x)-canvas.winfo_rootx()
            y=widget.winfo_rooty()+float(event.y)-canvas.winfo_rooty()
        except (AttributeError,TypeError,ValueError):return None
    if (math.isfinite(x) and math.isfinite(y)
            and 0<=x<canvas.winfo_width() and 0<=y<canvas.winfo_height()):
        return x,y
    return None


def capture_anchor(canvas,zoom,position):
    if position is None:return None
    x,y=position
    if not (zoom>0 and math.isfinite(zoom) and math.isfinite(x) and math.isfinite(y)):
        return None
    return ZoomAnchor((canvas.canvasx(x)/zoom,canvas.canvasy(y)/zoom),(x,y))


def restore_anchor(canvas,zoom,anchor):
    if anchor is None:return
    region=tuple(map(float,canvas.tk.splitlist(canvas.cget('scrollregion'))))
    if len(region)!=4:return
    for index,(axis,visible) in enumerate((('x',canvas.winfo_width()),('y',canvas.winfo_height()))):
        start,end=region[index],region[index+2]
        extent=end-start
        # Never invent scroll space just to anchor a diagram that fits.
        if extent<=visible:continue
        desired=anchor.logical[index]*zoom-anchor.viewport[index]
        offset=max(start,min(desired,end-visible))
        getattr(canvas,axis+'view_moveto')((offset-start)/extent)
