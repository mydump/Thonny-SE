# SPDX-FileCopyrightText: 2026 Sebastian Ladhoff
# SPDX-License-Identifier: GPL-3.0-only
# See LICENSE in the project root for the full license text.

"""Shared styling for the plugin's drawn controls and diagram surfaces."""

EDGE = "#77828d"
INK = "#20252a"
MUTED = "#596574"
DISABLED = "#a7afb8"
SELECT = "#1765cc"
SELECTION_WIDTH = 3
SELECTION_FILL = "#edf3fc"
# Live objects are distinct from white diagram documents, using a quiet surface.
OBJECT_FILL = "#edf7f3"
OBJECT_EDGE = "#80aaa0"
OBJECT_SHADOW = "#dce7e2"
FIELD_BORDER = "#a8b2ba"
ERROR = "#b42318"
HINT_FILL = "#fff5da"
HINT_BORDER = "#e4d4a7"
HINT_INK = "#725a2a"
HINT_BADGE = "#f3e4b7"
HINT_TEXT = "#4d432e"


def draw_chevron(canvas, x, y, direction, color, tags=()):
    return canvas.create_line(x-10, y-4*direction, x, y+4*direction, x+10, y-4*direction,
                              fill=color, width=3, capstyle="round", joinstyle="round", tags=tags)


# Semantic UML areas, separate from selection/error/deletion/hint colors.
UML_SECTION_FILLS = {'name':'#eae3f4', 'attributes':'#faf3f7', 'methods':'#f3f7fd'}
UML_SECTION_INKS = {'name':'#72549a', 'attributes':'#946781', 'methods':'#426fa9'}
UML_SECTION_BADGES = {'name':'#e0d5ee', 'attributes':'#f1e3ec', 'methods':'#e5eefb'}

# Canonical NSD area colors; shared by the diagram and the palette.
NSD_SECTION_FILLS = {"statement":"#ffffff", "call":"#fff4df",
                     "if_single":"#e9f0ff", "switch":"#e9f0ff", "if":"#e9f0ff", "try":"#e9f0ff",
                     **{kind:"#e7f4ed" for kind in ("while","repeat","for","foreach")}}

# Disabled NSD blocks remain editable; their export copy omits them entirely.
NSD_DISABLED_FILL = "#f1f2f3"
NSD_DISABLED_INK = "#858b92"
NSD_DISABLED_EDGE = "#9ba1a8"
