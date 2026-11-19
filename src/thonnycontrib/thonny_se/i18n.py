# SPDX-FileCopyrightText: 2026 Sebastian Ladhoff
# SPDX-License-Identifier: GPL-3.0-only
# See LICENSE in the project root for the full license text.

"""Plugin translations using Thonny's language and English source messages.

UI labels created at import time follow Thonny's restart-based language changes.
This module also works without Thonny, for model/code-generation consumers.
"""
from functools import lru_cache
from importlib.resources import files
import json
import logging


_language_code = "en_US"


def initialize():
    """Capture Thonny's language before importing modules with UI constants.

    Like Thonny itself, existing widgets keep their language until restart.
    """
    from thonny import get_workbench

    global _language_code
    _language_code = get_workbench().get_option("general.language") or "en_US"


def language_code():
    return _language_code


@lru_cache(maxsize=None)
def _catalog(code):
    # Locale names come from a setting, never use them as arbitrary paths.
    if not code or not all(c.isascii() and (c.isalnum() or c == "_") for c in code):
        return {}
    resource = files(__package__).joinpath("locales", code + ".json")
    try:
        result = json.loads(resource.read_text(encoding="utf-8"))
        if not isinstance(result, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in result.items()):
            raise ValueError("Translation catalog must map strings to strings")
        return result
    except FileNotFoundError:
        return {}
    except (OSError, ValueError):
        logging.getLogger(__name__).exception("Could not load Thonny SE translations for %s", code)
        return {}


def tr(message):
    """Translate an English message; missing/empty entries fall back to English."""
    code = str(language_code()).replace("-", "_")
    language = code.split("_", 1)[0].lower()
    # English source messages are the authoritative fallback for every language.
    if language == "en":
        return message
    return _catalog(code).get(message) or _catalog(language).get(message) or message
