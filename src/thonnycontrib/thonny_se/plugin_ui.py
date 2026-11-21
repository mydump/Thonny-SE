# SPDX-FileCopyrightText: 2026 Sebastian Ladhoff
# SPDX-License-Identifier: GPL-3.0-only
# See LICENSE in the project root for the full license text.

"""Info-Dialog und Optionsseite für Thonny SE."""
from .scrolling import ScrollArea
from .i18n import tr
import json
from importlib.resources import as_file, files
from tkinter import BooleanVar, StringVar, PhotoImage, ttk

from thonny import get_workbench
from thonny.config_ui import ConfigurationPage
from thonny.ui_utils import (
    CommonDialog,
    VerticallyScrollableFrame,
    create_url_label,
    ems_to_pixels,
    show_dialog,
)

from ._version import __version__
from .diagram_preferences import STRUCTOGRAM_CAT_BLOCKS, STRUCTOGRAM_HINTS, UML_EARS, UML_HINTS, OBJECT_METHODS, UML_CONSTRUCTOR_NAME, UML_CHECK_TYPES, UML_METHOD_STYLE, UML_AUTO_DEFAULTS, UML_USE_MULTIPLICITY, UML_CHECK_VALUES


PROJECT_URL = "https://github.com/mydump/Thonny-SE"


class AboutDialog(CommonDialog):
    def __init__(self, master):
        super().__init__(master)
        self.title(tr('About Thonny SE'))
        self.resizable(False, False)

        padding = self.get_large_padding()
        gap = self.get_small_padding()
        content = ttk.Frame(self, padding=padding)
        content.pack(fill="both", expand=True)

        logo_resource = files(__package__).joinpath("icons", "Thonny-SE-128.png")
        with as_file(logo_resource) as logo_path:
            self._logo_image = PhotoImage(master=self, file=str(logo_path))
        logo = ttk.Label(content, image=self._logo_image)
        logo.pack(anchor="w", pady=(0, gap))
        ttk.Label(content, text="Thonny SE", font="TkHeadingFont").pack(anchor="w")
        ttk.Label(content, text=tr('The educational software development plugin')).pack(anchor="w")
        ttk.Label(content, text=tr("Version: {version}").format(version=__version__)).pack(anchor="w", pady=(gap, 0))
        create_url_label(content, PROJECT_URL, text=PROJECT_URL).pack(anchor="w")
        ttk.Label(content, text=tr('Concept and development: Sebastian Ladhoff')).pack(
            anchor="w", pady=(gap, 0)
        )
        ttk.Label(content, text=tr('AI tools were used during development.')).pack(
            anchor="w"
        )
        ttk.Label(content, text="Copyright © 2026 Sebastian Ladhoff").pack(anchor="w")
        create_url_label(
            content, "https://www.gnu.org/licenses/gpl-3.0.html",
            text=tr('Project license: GNU GPL v3 only'),
        ).pack(anchor="w")

        ttk.Separator(content, orient="horizontal").pack(fill="x", pady=padding)
        ttk.Label(content, text=tr('Third-party software and licenses'), font="TkHeadingFont").pack(anchor="w")
        sources = VerticallyScrollableFrame(content)
        sources.canvas.configure(
            width=ems_to_pixels(35),
            height=ems_to_pixels(7),
            background=ttk.Style(self).lookup("TFrame", "background"),
        )
        sources.pack(fill="x")
        notices = files(__package__).joinpath("notices", "components.json")
        inventory = json.loads(notices.read_text(encoding="utf-8"))
        for source in (*inventory["components"], *inventory["resources"]):
            license_label = (tr("ISC and MIT (Feather-derived icons)")
                             if source["id"] == "lucide" else source["license"])
            ttk.Label(
                sources.interior,
                text=f'{source["name"]} · {license_label}',
                wraplength=ems_to_pixels(34),
            ).pack(
                anchor="w", pady=(gap, 0)
            )
            create_url_label(sources.interior, source["url"]).pack(anchor="w")
            if source['id'] == 'lucide':
                ttk.Label(sources.interior,
                    text=tr('Icons and derived icon font: Lucide contributors and Cole Bemis (Feather).'),
                    wraplength=ems_to_pixels(34),justify='left').pack(anchor='w')

        self.source_scrolling = ScrollArea(sources.canvas, sources, axes='y')

        ttk.Button(content, text=tr('Close'), command=self.destroy).pack(anchor="e", pady=(gap, 0))
        self.bind("<Escape>", lambda event: self.destroy())
        self.bind("<Return>", lambda event: self.destroy())
        self.bind("<KP_Enter>", lambda event: self.destroy())


class ThonnySEOptionsPage(ConfigurationPage):
    def __init__(self, master):
        super().__init__(master)
        self.options = {}
        self.columnconfigure(0, weight=1)
        workbench = get_workbench()
        for title, options in (
            (tr('Structogram editor'), (
                (STRUCTOGRAM_HINTS, tr('Hide introductory hints in this editor')),
                (STRUCTOGRAM_CAT_BLOCKS, tr('Cats')),
            )),
            (tr('UML editor'), (
                (UML_HINTS, tr('Hide introductory hints in this editor')),
                (UML_CONSTRUCTOR_NAME, tr('Display __init__ as the class name in diagrams')),
                (UML_CHECK_TYPES, tr('Reject unknown type names in attributes, parameters and return values')),
                (UML_CHECK_VALUES, tr('Check that initial values match their declared types')),
                (UML_AUTO_DEFAULTS, tr('Fill in initial values automatically when selecting an attribute type')),
                (UML_USE_MULTIPLICITY, tr('Call relationship counts multiplicity instead of cardinality')),
                (UML_METHOD_STYLE, tr('Names of automatically generated methods')),
                (UML_EARS, tr('Cats')),
            )),
            (tr('Object inspector SE'), ((OBJECT_METHODS, tr('Show all object methods instead of the Methods dropdown')),)),
        ):
            group = ttk.LabelFrame(self, text=title, padding=8)
            group.grid(sticky="ew", pady=(0, 8))
            for key, label in options:
                if key == UML_METHOD_STYLE:
                    row = ttk.Frame(group)
                    row.grid(sticky="w", pady=(5, 5))
                    ttk.Label(row, text=label).pack(side="left", padx=(0, 8))
                    variable = StringVar(self, value=workbench.get_option(key))
                    ttk.Combobox(row, textvariable=variable, state="readonly",
                                 values=('snake_case', 'camelCase'), width=14).pack(side="left")
                    self.options[key] = variable
                    continue
                variable = BooleanVar(self, value=workbench.get_option(key))
                self.options[key] = variable
                ttk.Checkbutton(group, text=label, variable=variable).grid(sticky="w")

    def apply(self):
        from .editor import StructogramEditor
        from .uml_editor import UmlEditor

        workbench = get_workbench()
        changed = set()
        for key, variable in self.options.items():
            value = variable.get()
            if value != workbench.get_option(key):
                workbench.set_option(key, value)
                changed.add(key)
        for editor in workbench.get_editor_notebook().get_all_editors():
            if isinstance(editor, StructogramEditor) and changed & {STRUCTOGRAM_CAT_BLOCKS, STRUCTOGRAM_HINTS}:
                editor.diagram.draw()
            elif isinstance(editor, UmlEditor) and changed & {UML_HINTS, UML_EARS, UML_CONSTRUCTOR_NAME, UML_CHECK_TYPES, UML_METHOD_STYLE, UML_AUTO_DEFAULTS, UML_USE_MULTIPLICITY, UML_CHECK_VALUES}:
                editor.diagram.draw()
                member = editor.diagram.member_editor
                if member is not None and hasattr(member, "_refresh_type_feedback"):
                    member._refresh_type_feedback()
        if OBJECT_METHODS in changed:
            view = workbench._thonny_se_objects.existing_view()
            if view is not None:
                view.draw()


def install():
    workbench = get_workbench()
    for option in (STRUCTOGRAM_CAT_BLOCKS, STRUCTOGRAM_HINTS, UML_HINTS, UML_EARS, OBJECT_METHODS, UML_USE_MULTIPLICITY):
        workbench.set_default(option, False)
    for option in (UML_CONSTRUCTOR_NAME, UML_CHECK_TYPES, UML_AUTO_DEFAULTS, UML_CHECK_VALUES):
        workbench.set_default(option, True)
    workbench.set_default(UML_METHOD_STYLE, "snake_case")
    from .diagram_preferences import UML_GRID
    workbench.set_default(UML_GRID, "none")
    from .export_preferences import EXPORT_KEYS
    for key in EXPORT_KEYS.values():
        workbench.set_default(key, True)
    # Thonny lädt seinen eigenen Info-Eintrag zuerst in derselben Menügruppe.
    workbench.add_command(
        "thonny_se_about", "help", tr('About Thonny SE'),
        lambda: show_dialog(AboutDialog(workbench)), group=61,
    )
    workbench.add_configuration_page("thonny_se", "Thonny SE", ThonnySEOptionsPage, 100)
