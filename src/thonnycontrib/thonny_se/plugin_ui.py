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
from .diagram_preferences import APPEARANCE, STRUCTOGRAM_CAT_BLOCKS, STRUCTOGRAM_HINTS, UML_EARS, UML_HINTS, OBJECT_METHODS, UML_CONSTRUCTOR_NAME, UML_CHECK_TYPES, UML_METHOD_STYLE, UML_AUTO_DEFAULTS, UML_USE_MULTIPLICITY, UML_CHECK_VALUES, OBJECT_CHECK_ARGUMENTS


PROJECT_URL = "https://github.com/mydump/Thonny-SE"

LIGHT_UI_THEME = "thonny_se.light_ui_theme"
LIGHT_SYNTAX_THEME = "thonny_se.light_syntax_theme"
DARK_UI_THEME = "thonny_se.dark_ui_theme"
DARK_SYNTAX_THEME = "thonny_se.dark_syntax_theme"
APPEARANCE_DEFAULTS = {
    APPEARANCE: "light",
    LIGHT_UI_THEME: "",
    LIGHT_SYNTAX_THEME: "Default Light",
    DARK_UI_THEME: "Clean Dark",
    DARK_SYNTAX_THEME: "Default Dark",
}


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
        self._add_appearance_options(workbench)
        def group(title):
            frame = ttk.LabelFrame(self, text=title, padding=(10, 8))
            frame.grid(sticky="ew", pady=(0, 8))
            return frame

        def check(parent, key, label):
            variable = BooleanVar(self, value=workbench.get_option(key))
            self.options[key] = variable
            ttk.Checkbutton(parent, text=tr(label), variable=variable).pack(anchor="w", pady=1)

        uml = group(tr('UML editor'))
        check(uml, UML_HINTS, 'Hide introductory hints in this editor')
        check(uml, UML_CONSTRUCTOR_NAME, 'Display __init__ as the class name in diagrams')
        check(uml, UML_USE_MULTIPLICITY, 'Call relationship counts multiplicity instead of cardinality')
        row = ttk.Frame(uml)
        row.pack(fill="x", pady=(6, 5))
        ttk.Label(row, text=tr('Names of automatically generated methods')).pack(side="left", padx=(0, 12))
        variable = StringVar(self, value=workbench.get_option(UML_METHOD_STYLE))
        self.options[UML_METHOD_STYLE] = variable
        ttk.Combobox(row, textvariable=variable, state="readonly",
                     values=('snake_case', 'camelCase'), width=14).pack(side="left")
        ttk.Separator(uml).pack(fill="x", pady=(4, 6))
        check(uml, UML_AUTO_DEFAULTS, 'Fill in initial values automatically when selecting an attribute type')
        check(uml, UML_CHECK_TYPES, 'Reject unknown type names in attributes, parameters and return values')
        check(uml, UML_CHECK_VALUES, 'Check that initial values match their declared types')

        structogram = group(tr('Structogram editor'))
        check(structogram, STRUCTOGRAM_HINTS, 'Hide introductory hints in this editor')
        objects = group(tr('Object inspector SE'))
        check(objects, OBJECT_METHODS, 'Show all object methods instead of the Methods dropdown')
        check(objects, OBJECT_CHECK_ARGUMENTS, 'Check argument types in the object inspector')
        ttk.Label(objects, text=tr('Checks literals and known variables against parameter types. Entered function and method calls are not evaluated or checked for their return type.'), wraplength=540, justify='left').pack(anchor='w', padx=(20, 0), pady=(0, 4))

        extras = group(tr('Extras'))
        cats = BooleanVar(self, value=any(workbench.get_option(key)
                                       for key in (STRUCTOGRAM_CAT_BLOCKS, UML_EARS)))
        self.options[STRUCTOGRAM_CAT_BLOCKS] = self.options[UML_EARS] = cats
        ttk.Checkbutton(extras, text=tr('Cats'), variable=cats).pack(anchor="w", pady=1)

    def _add_appearance_options(self, workbench):
        group = ttk.LabelFrame(self, text=tr("Appearance"), padding=8)
        group.grid(sticky="ew", pady=(0, 8))
        group.columnconfigure((1, 2), weight=1)

        mode = StringVar(self, value=workbench.get_option(APPEARANCE))
        self.options[APPEARANCE] = mode
        ttk.Label(group, text=tr("UI theme")).grid(row=1, column=0, sticky="w", padx=(0, 8))
        ttk.Label(group, text=tr("Syntax theme")).grid(row=2, column=0, sticky="w", padx=(0, 8))

        ui_themes = tuple(workbench.get_usable_ui_theme_names())
        syntax_themes = tuple(workbench.get_syntax_theme_names())
        self._default_ui_label = tr("Thonny default ({theme})").format(
            theme=workbench.get_default_ui_theme()
        )
        for column, (value, label, ui_key, syntax_key) in enumerate(
            (
                ("light", tr("Light"), LIGHT_UI_THEME, LIGHT_SYNTAX_THEME),
                ("dark", tr("Dark"), DARK_UI_THEME, DARK_SYNTAX_THEME),
            ),
            start=1,
        ):
            ttk.Radiobutton(group, text=label, variable=mode, value=value).grid(
                row=0, column=column, sticky="w", pady=(0, 4)
            )
            for row, key, themes in ((1, ui_key, ui_themes), (2, syntax_key, syntax_themes)):
                default = APPEARANCE_DEFAULTS[key]
                selected = workbench.get_option(key)
                if selected not in themes:
                    selected = default
                if key == LIGHT_UI_THEME:
                    themes = (self._default_ui_label, *themes)
                    selected = selected or self._default_ui_label
                variable = StringVar(self, value=selected)
                self.options[key] = variable
                ttk.Combobox(group, textvariable=variable, values=themes, state="readonly", width=20).grid(
                    row=row, column=column, sticky="ew", padx=(0, 6), pady=2
                )

    def apply(self):
        from .editor import StructogramEditor
        from .uml_editor import UmlEditor

        workbench = get_workbench()
        changed = set()
        for key, variable in self.options.items():
            value = variable.get()
            if key == LIGHT_UI_THEME and value == self._default_ui_label:
                value = ""
            if value != workbench.get_option(key):
                workbench.set_option(key, value)
                changed.add(key)
        for editor in workbench.get_editor_notebook().get_all_editors():
            if isinstance(editor, StructogramEditor) and changed & {APPEARANCE, STRUCTOGRAM_CAT_BLOCKS, STRUCTOGRAM_HINTS}:
                editor.diagram.draw()
                if APPEARANCE in changed:
                    editor.palette.refresh_appearance()
            elif isinstance(editor, UmlEditor) and changed & {APPEARANCE, UML_HINTS, UML_EARS, UML_CONSTRUCTOR_NAME, UML_CHECK_TYPES, UML_METHOD_STYLE, UML_AUTO_DEFAULTS, UML_USE_MULTIPLICITY, UML_CHECK_VALUES}:
                editor.diagram.draw()
                member = editor.diagram.member_editor
                if member is not None and hasattr(member, "_refresh_type_feedback"):
                    member._refresh_type_feedback()
        if OBJECT_METHODS in changed:
            view = workbench._thonny_se_objects.existing_view()
            if view is not None:
                view.draw()
        self._apply_appearance(workbench, changed)

    def _apply_appearance(self, workbench, changed):
        if workbench.get_option(APPEARANCE) == "dark":
            ui_key, syntax_key = DARK_UI_THEME, DARK_SYNTAX_THEME
        else:
            ui_key, syntax_key = LIGHT_UI_THEME, LIGHT_SYNTAX_THEME

        if not changed.intersection((APPEARANCE, ui_key, syntax_key)):
            return

        updated = False
        for key, theme in (
            ("view.ui_theme", workbench.get_option(ui_key) or workbench.get_default_ui_theme()),
            ("view.syntax_theme", workbench.get_option(syntax_key)),
        ):
            if theme != workbench.get_option(key):
                workbench.set_option(key, theme)
                updated = True

        if updated:
            workbench.reload_themes()


def install():
    workbench = get_workbench()
    for key, value in APPEARANCE_DEFAULTS.items():
        workbench.set_default(key, value)
    for option in (STRUCTOGRAM_CAT_BLOCKS, STRUCTOGRAM_HINTS, UML_HINTS, UML_EARS, UML_USE_MULTIPLICITY):
        workbench.set_default(option, False)
    for option in (OBJECT_CHECK_ARGUMENTS, OBJECT_METHODS, UML_CONSTRUCTOR_NAME, UML_CHECK_TYPES, UML_AUTO_DEFAULTS, UML_CHECK_VALUES):
        workbench.set_default(option, True)
    workbench.set_default(UML_METHOD_STYLE, "snake_case")
    from .diagram_preferences import UML_GRID
    workbench.set_default(UML_GRID, "none")
    from .export_preferences import EXPORT_DEFAULTS, EXPORT_KEYS
    for name, key in EXPORT_KEYS.items():
        workbench.set_default(key, EXPORT_DEFAULTS[name])
    # Thonny lädt seinen eigenen Info-Eintrag zuerst in derselben Menügruppe.
    workbench.add_command(
        "thonny_se_about", "help", tr('About Thonny SE'),
        lambda: show_dialog(AboutDialog(workbench)), group=61,
    )
    workbench.add_configuration_page("thonny_se", "Thonny SE", ThonnySEOptionsPage, 100)
