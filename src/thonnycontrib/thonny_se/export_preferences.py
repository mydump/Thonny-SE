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
    appearance: str = "light"

    @property
    def dark(self):
        return not self.monochrome and self.appearance == "dark"

    @property
    def models_are_transparent(self):
        return self.monochrome and self.transparent_models


EXPORT_KEYS = {field.name: 'thonny_se.export_'+field.name for field in fields(ExportOptions)}
EXPORT_DEFAULTS = {field.name: field.default for field in fields(ExportOptions)}


def load_options():
    workbench = get_workbench()
    if workbench is None:
        return ExportOptions()
    values = {name: workbench.get_option(key, EXPORT_DEFAULTS[name])
              for name, key in EXPORT_KEYS.items()}
    values["appearance"] = "dark" if values["appearance"] == "dark" else "light"
    return ExportOptions(**values)


def save_options(options):
    workbench = get_workbench()
    if workbench:
        for name, key in EXPORT_KEYS.items():
            workbench.set_option(key, getattr(options, name))
