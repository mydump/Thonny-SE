# SPDX-FileCopyrightText: 2026 Sebastian Ladhoff
# SPDX-License-Identifier: GPL-3.0-only
# See LICENSE in the project root for the full license text.

"""Einstiegspunkt für Thonnys Plugin-Lader."""
from .i18n import tr


def load_plugin():
    from .i18n import initialize
    initialize()

    import logging
    from thonny import get_version

    # Die Dokumentintegration hängt von den Interna der 5.0-Reihe ab.
    if get_version().split(".")[:2] != ["5", "0"]:
        logging.getLogger(__name__).warning(
            tr('Thonny SE currently supports only Thonny 5.0.x; plugin not loaded.')
        )
        return
    from .integration import install
    install()

    from .object_inspector import install as install_object_inspector
    install_object_inspector()

    from .plugin_ui import install as install_plugin_ui
    install_plugin_ui()
