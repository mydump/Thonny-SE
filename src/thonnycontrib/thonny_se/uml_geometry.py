# SPDX-FileCopyrightText: 2026 Sebastian Ladhoff
# SPDX-License-Identifier: GPL-3.0-only
# See LICENSE in the project root for the full license text.

"""User-controlled curve geometry and gentle grid snapping."""
import math
from .uml_relationships import card_edge_toward, self_relationship_points

GRID_STEP = 24
GRID_ORIGIN = 8


def magnet(value, *, tolerance=5):
    target = GRID_ORIGIN + round((value-GRID_ORIGIN)/GRID_STEP)*GRID_STEP
    return target if abs(target-value) <= tolerance else value


def dragged_bend(start, end, delta, previous=0, *, tolerance=8):
    dx, dy = (end[0]+end[2]-start[0]-start[2])/2, (end[1]+end[3]-start[1]-start[3])/2
    length = math.hypot(dx,dy)
    if start == end:
        return max(-48, min(1_000_000, previous+delta[0]))
    if not length:
        return previous
    bend = previous + (-dy*delta[0]+dx*delta[1])/length
    return 0 if abs(bend) <= tolerance else max(-1_000_000,min(1_000_000,bend))


def curved_points(start, end, bend):
    if start == end:
        return self_relationship_points(start, bend=bend)
    ax,ay=(start[0]+start[2])/2,(start[1]+start[3])/2
    bx,by=(end[0]+end[2])/2,(end[1]+end[3])/2
    dx,dy=bx-ax,by-ay
    length=math.hypot(dx,dy)
    if not length:
        return (card_edge_toward(start,(bx+1,by)),card_edge_toward(end,(ax-1,ay)))
    control=((ax+bx)/2-dy/length*2*bend,(ay+by)/2+dx/length*2*bend)
    first,last=card_edge_toward(start,control),card_edge_toward(end,control)
    count=min(160,max(24,math.ceil((length+2*abs(bend))/12)))
    return tuple(((1-t)**2*first[0]+2*(1-t)*t*control[0]+t*t*last[0],
                  (1-t)**2*first[1]+2*(1-t)*t*control[1]+t*t*last[1])
                 for t in (index/count for index in range(count+1)))
