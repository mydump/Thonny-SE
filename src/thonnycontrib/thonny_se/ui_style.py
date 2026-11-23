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
OBJECT_FOCUS = "#4c8976"
OBJECT_ACTIVE_FILL = "#d8eee4"
DOC_FILL = "#f4f6f5"
FIELD_BORDER = "#a8b2ba"
ERROR = "#b42318"
ARGUMENT_MISSING = "#b48a24"
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

# Light drawing colors remain the defaults for export.
DARK_CANVAS = "#20242a"
DARK_MONOCHROME_CANVAS = "#222222"
DARK_MONOCHROME_SURFACE = "#303030"
DARK_MONOCHROME_INK = "#eeeeee"
DARK_DIAGRAM_COLORS = {
    "white": "#2b3139",
    "#ffffff": "#2b3139",
    INK: "#e2e6eb",
    MUTED: "#b0bac7",
    EDGE: "#8794a4",
    SELECT: "#83b8ff",
    ERROR: "#ffa59e",
    ARGUMENT_MISSING: "#e4c36e",
    HINT_FILL: "#403626",
    HINT_BORDER: "#8b7754",
    HINT_BADGE: "#51422a",
    HINT_INK: "#eed195",
    HINT_TEXT: "#f0ddba",
    NSD_DISABLED_FILL: "#34383e",
    NSD_DISABLED_INK: "#a7aeb8",
    NSD_DISABLED_EDGE: "#717985",
    NSD_SECTION_FILLS["call"]: "#413629",
    NSD_SECTION_FILLS["if"]: "#2c3d53",
    NSD_SECTION_FILLS["while"]: "#2a4038",
    UML_SECTION_FILLS["name"]: "#40354e",
    UML_SECTION_FILLS["attributes"]: "#3c303c",
    UML_SECTION_FILLS["methods"]: "#2b3a4d",
    UML_SECTION_INKS["name"]: "#c5afe2",
    UML_SECTION_INKS["attributes"]: "#dab1c8",
    UML_SECTION_INKS["methods"]: "#a9c6ee",
    UML_SECTION_BADGES["name"]: "#4b3d5b",
    UML_SECTION_BADGES["attributes"]: "#503b4c",
    UML_SECTION_BADGES["methods"]: "#364963",
    FIELD_BORDER: "#8794a4",
    DISABLED: "#738090",
    SELECTION_FILL: "#304358",
    OBJECT_FILL: "#2b3b36",
    OBJECT_EDGE: "#759b91",
    OBJECT_SHADOW: "#1b221f",
    OBJECT_FOCUS: "#8dc6af",
    OBJECT_ACTIVE_FILL: "#3d5d4f",
    DOC_FILL: "#282e2b",
    "#b9cfe8": "#647c99",
    "#dceaff": "#384d68",
    "#28794e": "#9bd5b2",
    "#a6b4c3": "#67798d",
    "#47586b": "#b9c8d9",
    "#faddd9": "#633a3e",
    "#fff8f7": "#543437",
    "#edf0f3": "#2d343d",  # Grid
    "#d6d6d6": "#1b1e23",  # UML focus surroundings
    "#fff0ee": "#4b3033",  # UML deletion surface
    "#000000": "#c5ced8",  # Cat details
    "#8f2019": "#ffc0ba",
    "#124e9e": "#bad7ff",
}

DARK_MONOCHROME_CONTROLS = {
    SELECT: DARK_DIAGRAM_COLORS[SELECT],
    "#edf0f3": "#383838",
}


def uses_dark_ui(workbench=None):
    from tkinter import TclError
    from thonny import get_workbench

    if workbench is None:
        workbench = get_workbench()
    if workbench is None:
        return False
    try:
        return workbench.uses_dark_ui_theme()
    except TclError:
        # Tk can temporarily lack the active theme during native callbacks.
        return "dark" in str(workbench.get_option("view.ui_theme", "")).lower()


def ui_color(light):
    return DARK_DIAGRAM_COLORS.get(light, light) if uses_dark_ui() else light
