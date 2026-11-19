# SPDX-FileCopyrightText: 2026 Sebastian Ladhoff
# SPDX-License-Identifier: GPL-3.0-only
# See LICENSE in the project root for the full license text.

"""Remember export appearance independently of the editor's display."""
from dataclasses import dataclass, fields
from thonny import get_workbench


@dataclass(frozen=True)
class ExportOptions:
    transparent_background: bool = True
    transparent_models: bool = True
    monochrome: bool = True


EXPORT_KEYS = {field.name: 'thonny_se.export_'+field.name for field in fields(ExportOptions)}


def load_options():
    workbench = get_workbench()
    return ExportOptions(**{name: bool(workbench.get_option(key, True)) if workbench else True
                            for name, key in EXPORT_KEYS.items()})


def save_options(options):
    workbench = get_workbench()
    if workbench:
        for name, key in EXPORT_KEYS.items():
            workbench.set_option(key, getattr(options, name))
