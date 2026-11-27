# SPDX-FileCopyrightText: 2026 Sebastian Ladhoff
# SPDX-License-Identifier: GPL-3.0-only
# See LICENSE in the project root for the full license text.

"""Katzenköpfe aus Canvas-Formen, die auch der Grafikexport unterstützt."""
from random import Random


def draw_cat_head(canvas, left, top, right, seed, *, scale, fill="#ffffff", bottom=None, tags=(),
                  ink="#000000", detail="#ffffff", stroke=1, zoom=1):
    variant = Random(seed)
    scale *= variant.uniform(0.93, 1.07)
    on_left = variant.choice((True, False))
    x = left if on_left else right - 98 * scale
    left_ear = variant.randint(-2, 2)
    right_ear = variant.randint(-2, 2)
    expression = variant.choice(("smile", "wink", "surprised", "sleeping", "annoyed", "waving", "hunting", "flowerpot", "paws", "tail"))
    ear_style = variant.choice(("pointed", "wide", "folded", "tufted"))
    tags = (*tags, "cat-head", "cat-" + expression, "ears-" + ear_style)
    height_scale = 0.72 if expression == "hunting" else 1
    contour = max(1, int(stroke * zoom + .5))
    # Outer contours follow the diagram. Facial details grow more gently so
    # small UML heads retain separate eyes, mouth and inner ears.
    detail_weight = max(.8, (stroke / 2) ** .25)
    detail_contour = max(1, int(min(2, stroke) * zoom + .5))

    def detail_width(width):
        return max(1, int(width * scale * detail_weight * zoom + .5))

    def points(*offsets):
        return [
            (x + (dx if on_left else 98 - dx) * scale, top + dy * scale * height_scale)
            for dx, dy in offsets
        ]

    def line(offsets, width=2):
        canvas.create_line(points(*offsets), fill=ink, width=detail_width(width),
                           capstyle="round", joinstyle="round", tags=tags)

    def polygon(offsets, color=fill):
        canvas.create_polygon(points(*offsets), fill=color, outline=ink,
                              width=contour if color == fill else detail_contour, tags=tags)

    if expression == "paws":
        for paw_x in (25, 65):
            polygon(((paw_x - 7, 0), (paw_x - 7, -8), (paw_x - 4, -13),
                     (paw_x + 4, -13), (paw_x + 7, -8), (paw_x + 7, 0)))
            for toe in (-3, 1):
                line(((paw_x + toe, -9), (paw_x + toe, -5)), width=1)
        return
    if expression == "tail":
        tail_top = bottom if bottom is not None else top
        tail = ((43, 3), (43, 15), (48, 24), (59, 28), (70, 25), (75, 18),
                (74, 12), (70, 10), (67, 13), (68, 18), (63, 21), (56, 20),
                (51, 15), (51, 3))
        canvas.create_polygon(
            [(px, tail_top + py - top - 3 * scale) for px, py in points(*tail)],
            fill=fill, outline=ink, width=contour, tags=tags,
        )
        return

    ear_shapes = {
        "pointed": ((9, -9), (10, -18), (13, -27), (17, -33), (20, -34), (25, -31), (34, -21)),
        "wide": ((9, -9), (7, -19), (6, -30), (11, -31), (22, -27), (34, -21)),
        "folded": ((9, -9), (10, -22), (17, -30), (28, -26), (32, -18), (24, -21), (34, -21)),
        "tufted": ((9, -9), (10, -22), (13, -29), (12, -34), (17, -31), (19, -35), (22, -30), (34, -21)),
    }
    ear = ear_shapes[ear_style]
    outline = (
        ((0, 0), (4, -6))
        + tuple((dx, dy + left_ear) for dx, dy in ear)
        + ((44, -23), (54, -23))
        + tuple((98 - dx, dy + right_ear) for dx, dy in reversed(ear))
        + ((94, -6), (98, 0))
    )
    # Fill the head without closing its outline across the diagram's edge.
    canvas.create_polygon(points(*outline), fill=fill, outline='', tags=tags)
    inset = min(8, stroke / (2 * scale))
    canvas.create_line(points((inset, 0), (98-inset, 0)), fill=fill,
                       width=contour+2, capstyle='butt', tags=(*tags, 'cat-seam'))
    canvas.create_line(points(*outline), fill=ink, width=contour,
                       capstyle='butt', joinstyle='round', tags=(*tags, 'cat-contour'))
    for mirrored, shift in ((False, left_ear), (True, right_ear)):
        inner = ((14, -15), (16, -24), (20, -28), (25, -23), (29, -20))
        if ear_style == "folded":
            inner = ((15, -16), (16, -23), (23, -23), (26, -20))
        polygon(tuple((98 - dx if mirrored else dx, dy + shift) for dx, dy in inner), detail)

    for eye in (33, 65):
        if expression == "sleeping":
            line(((eye - 5, -11), (eye - 2, -8), (eye + 2, -8), (eye + 5, -11)))
        elif expression in ("annoyed", "hunting"):
            line(((eye - 5, -12), (eye + 5, -12)))
            pupil = eye + 3 if expression == "hunting" else eye
            line(((pupil, -11), (pupil, -9)), width=3)
            if expression == "annoyed":
                slope = 2 if eye == 33 else -2
                line(((eye - 5, -17 - slope), (eye + 5, -17 + slope)))
        elif expression == "wink" and eye == 65:
            line(((61, -9), (65, -12), (69, -9)))
        else:
            line(((eye, -12), (eye, -9)), width=5)

    if expression == "surprised":
        polygon(((49, -12), (53, -9), (52, -5), (46, -5), (45, -9)))
    elif expression in ("annoyed", "hunting"):
        line(((44, -5), (49, -7), (54, -5)))
    else:
        line(((43, -10), (45, -7), (47, -7), (49, -10), (51, -7), (53, -7), (55, -10)))

    if expression == "sleeping":
        line(((72, -19), (80, -19), (72, -13), (80, -13)), width=1)
        line(((85, -27), (93, -27), (85, -21), (93, -21)), width=1)
    elif expression == "waving":
        polygon(((87, 0), (91, -7), (96, -12), (96, -23), (99, -26),
                 (102, -26), (105, -23), (105, -10), (102, -4), (99, 0)))
        line(((99, -21), (102, -21)), width=1)
        line(((99, -17), (102, -17)), width=1)
        line(((109, -25), (112, -28)), width=1)
        line(((110, -19), (114, -19)), width=1)
    elif expression == "flowerpot":
        # Die ausgestreckte Pfote schiebt den geneigten Topf über die Kante.
        polygon(((87, -5), (91, -11), (112, -11), (116, -8), (114, -4), (94, -3)))
        line(((109, -9), (113, -8)), width=1)
        polygon(((117, -13), (133, -8), (125, 5), (115, 1)), detail)
        polygon(((116, -16), (136, -10), (134, -6), (115, -12)), detail)
        line(((125, -13), (129, -24), (126, -30)), width=1)
        polygon(((128, -21), (120, -24), (121, -28), (129, -25)), detail)
        polygon(((129, -24), (136, -28), (138, -24), (130, -20)), detail)
        line(((134, -3), (138, 0)), width=1)
        line(((131, 3), (134, 6)), width=1)
    elif expression == "hunting":
        # Die Maus sitzt am anderen Ende und schaut zur lauernden Katze.
        mouse_x = right - 26 * scale if on_left else left + 26 * scale
        direction = 1 if on_left else -1

        def mouse_points(*offsets):
            return [(mouse_x + dx * scale * direction, top + dy * scale) for dx, dy in offsets]

        mouse_tags = (*tags, "cat-mouse")
        canvas.create_line(
            mouse_points((16, -5), (22, -8), (25, -5), (22, -2)),
            fill=ink, width=detail_width(1), tags=mouse_tags,
        )
        canvas.create_polygon(
            mouse_points((0, -2), (4, -7), (9, -10), (15, -9), (18, -5), (17, 0), (4, 0)),
            fill=fill, outline=ink, width=contour, tags=mouse_tags,
        )
        canvas.create_polygon(
            mouse_points((7, -8), (6, -13), (9, -16), (12, -14), (12, -9)),
            fill=detail, outline=ink, width=detail_contour, tags=mouse_tags,
        )
        canvas.create_line(mouse_points((4, -4), (5, -4)), fill=ink, width=detail_width(2), tags=mouse_tags)
