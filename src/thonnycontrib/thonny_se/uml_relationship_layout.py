# SPDX-FileCopyrightText: 2026 Sebastian Ladhoff
# SPDX-License-Identifier: GPL-3.0-only
# See LICENSE in the project root for the full license text.

"""Deterministic relationship label placement in diagram coordinates."""
def overlaps(first, second, gap=3):
    return (first[0] < second[2]+gap and second[0] < first[2]+gap
            and first[1] < second[3]+gap and second[1] < first[3]+gap)


def crosses_box(first, last, box, gap=5):
    """Whether a segment touches the padded text box (including its interior)."""
    left, top, right, bottom = box
    low, high = 0.0, 1.0
    for start, end, minimum, maximum in (
            (first[0], last[0], left-gap, right+gap),
            (first[1], last[1], top-gap, bottom+gap)):
        delta = end-start
        if not delta:
            if not minimum <= start <= maximum:
                return False
            continue
        enter, leave = sorted(((minimum-start)/delta, (maximum-start)/delta))
        low, high = max(low, enter), min(high, leave)
        if low > high:
            return False
    return True


def place_label(center, size, occupied, segments=()):
    """Choose the nearest free label rectangle, avoiding cards, labels and actual line segments."""
    width, height = size
    x, y = center
    step = max(8, height+5)
    for ring in range(101):
        offsets = [(0,0)] if not ring else [(dx,dy) for dx in range(-ring,ring+1)
            for dy in range(-ring,ring+1) if max(abs(dx),abs(dy)) == ring]
        offsets.sort(key=lambda offset: offset[0]**2+offset[1]**2)
        for dx, dy in offsets:
            cx, cy = max(width/2+4,x+dx*step), max(height/2+4,y+dy*step)
            box = (cx-width/2,cy-height/2,cx+width/2,cy+height/2)
            if (not any(overlaps(box, other) for other in occupied)
                    and not any(crosses_box(first, last, box) for first, last in segments)):
                return (cx,cy), box
    # Extremely dense diagrams still get a free, deterministic position below.
    cy = max([y, *(box[3] for box in occupied),
              *(max(first[1], last[1]) for first, last in segments)])+height/2+8
    cx = max(width/2+4,x)
    return (cx,cy), (cx-width/2,cy-height/2,cx+width/2,cy+height/2)
