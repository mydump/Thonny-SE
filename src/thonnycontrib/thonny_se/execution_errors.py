# SPDX-FileCopyrightText: 2026 Sebastian Ladhoff
# SPDX-License-Identifier: GPL-3.0-only
# See LICENSE in the project root for the full license text.

"""One console destination for Python errors, including frontend preparation."""
import traceback
from thonny import get_shell, get_workbench


def report_python_error(error):
    workbench = get_workbench()
    if workbench is None:
        return
    workbench.show_view('ShellView', set_focus=False)
    get_shell().print_error(''.join(traceback.format_exception_only(type(error), error)))
