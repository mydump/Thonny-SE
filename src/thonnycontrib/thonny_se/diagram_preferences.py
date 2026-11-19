# SPDX-FileCopyrightText: 2026 Sebastian Ladhoff
# SPDX-License-Identifier: GPL-3.0-only
# See LICENSE in the project root for the full license text.

"""Darstellungsoptionen für die beiden Diagrammeditoren."""
from thonny import get_workbench

STRUCTOGRAM_CAT_BLOCKS = "thonny_se.structogram_cat_ears"
STRUCTOGRAM_HINTS = "thonny_se.structogram_hide_hints"
UML_HINTS = "thonny_se.uml_hide_hints"
OBJECT_METHODS = "thonny_se.object_show_all_methods"
UML_GRID = "thonny_se.uml_grid"
UML_CONSTRUCTOR_NAME = "thonny_se.uml_constructor_class_name"
UML_CHECK_TYPES = "thonny_se.uml_check_types"
UML_METHOD_STYLE = "thonny_se.uml_method_style"
UML_EARS = "thonny_se.uml_cat_ears"


def enabled(option):
    workbench = get_workbench()
    default = option in (UML_CONSTRUCTOR_NAME, UML_CHECK_TYPES)
    return workbench.get_option(option, default) if workbench is not None else default


def method_style():
    workbench = get_workbench()
    return workbench.get_option(UML_METHOD_STYLE, 'snake_case') if workbench is not None else 'snake_case'
