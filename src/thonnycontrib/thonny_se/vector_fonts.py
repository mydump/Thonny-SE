# SPDX-FileCopyrightText: 2026 Sebastian Ladhoff
# SPDX-License-Identifier: GPL-3.0-only
# See LICENSE in the project root for the full license text.

"""Process-private icon-font registration; no font installation or admin rights."""
import ctypes
from ctypes.util import find_library
from pathlib import Path


def register_private(path, backend):
    path = Path(path).resolve()
    if backend == 'win32':
        from ctypes import wintypes
        gdi = ctypes.WinDLL('gdi32',use_last_error=True)
        gdi.AddFontResourceExW.argtypes = (wintypes.LPCWSTR,wintypes.DWORD,ctypes.c_void_p)
        gdi.AddFontResourceExW.restype = ctypes.c_int
        return bool(gdi.AddFontResourceExW(str(path),0x10,None))  # FR_PRIVATE
    if backend == 'x11':
        name = find_library('fontconfig')
        if not name:return False
        fc = ctypes.CDLL(name)
        fc.FcConfigGetCurrent.argtypes = ()
        fc.FcConfigGetCurrent.restype = ctypes.c_void_p
        fc.FcConfigAppFontAddFile.argtypes = (ctypes.c_void_p,ctypes.c_char_p)
        fc.FcConfigAppFontAddFile.restype = ctypes.c_int
        config = fc.FcConfigGetCurrent()
        return bool(config and fc.FcConfigAppFontAddFile(config,str(path).encode()))
    if backend != 'aqua':return False
    cf=ctypes.CDLL('/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation')
    ct=ctypes.CDLL('/System/Library/Frameworks/CoreText.framework/CoreText')
    cf.CFURLCreateFromFileSystemRepresentation.argtypes=[ctypes.c_void_p,ctypes.c_char_p,ctypes.c_long,ctypes.c_bool]
    cf.CFURLCreateFromFileSystemRepresentation.restype=ctypes.c_void_p
    cf.CFRelease.argtypes=[ctypes.c_void_p]
    ct.CTFontManagerRegisterFontsForURL.argtypes=[ctypes.c_void_p,ctypes.c_uint32,ctypes.POINTER(ctypes.c_void_p)]
    ct.CTFontManagerRegisterFontsForURL.restype=ctypes.c_bool
    encoded=str(path).encode()
    url=cf.CFURLCreateFromFileSystemRepresentation(None,encoded,len(encoded),False)
    if not url:return False
    error=ctypes.c_void_p()
    try:return bool(ct.CTFontManagerRegisterFontsForURL(url,1,ctypes.byref(error)))
    finally:
        cf.CFRelease(url)
        if error.value:cf.CFRelease(error)
