# -*- coding: utf-8 -*-
"""诊断：exe 图标兜底可行性——ApplicationFrameWindow 四连全 miss 时，
SHGetFileInfo(进程 exe) 能否拿到正确的应用图标（设置=SystemSettings.exe；
真 UWP 外框是 ApplicationFrameHost，需走子 CoreWindow 找真实应用进程）。

用法: uv run tools/diag/exe_icon_fallback_probe.py
"""
import ctypes
import os
import subprocess
import sys
import time
from ctypes import wintypes
from pathlib import Path
from tempfile import gettempdir

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import wm

_user32 = ctypes.windll.user32
_kernel32 = ctypes.windll.kernel32
_shell32 = ctypes.windll.shell32
_gdi32 = ctypes.windll.gdi32

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
SHGFI_ICON, SHGFI_LARGEICON = 0x100, 0x0
FILE_ATTRIBUTE_NORMAL = 0x80


class SHFILEINFOW(ctypes.Structure):
    _fields_ = [("hIcon", wintypes.HICON), ("iIcon", ctypes.c_int),
                ("dwAttributes", wintypes.DWORD), ("szDisplayName", ctypes.c_wchar * 260),
                ("szTypeName", ctypes.c_wchar * 80)]


_kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
_kernel32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD,
                                                 wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
_shell32.SHGetFileInfoW.restype = wintypes.BOOL
_shell32.SHGetFileInfoW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD,
                                    ctypes.POINTER(SHFILEINFOW), wintypes.UINT, wintypes.UINT]
_user32.FindWindowExW.restype = wintypes.HWND
_user32.FindWindowExW.argtypes = [wintypes.HWND, wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR]


def image_path_of_pid(pid: int) -> str:
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    h = _kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not h:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(1024)
        size = wintypes.DWORD(1024)
        if _kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
            return buf.value
        return ""
    finally:
        _kernel32.CloseHandle(h)


def shell_icon(path: str) -> int:
    info = SHFILEINFOW()
    if _shell32.SHGetFileInfoW(path, FILE_ATTRIBUTE_NORMAL, ctypes.byref(info),
                               ctypes.sizeof(SHFILEINFOW), SHGFI_ICON | SHGFI_LARGEICON):
        return info.hIcon or 0
    return 0


def dump_icon(hicon: int, name: str) -> None:
    class ICONINFO(ctypes.Structure):
        _fields_ = [("fIcon", wintypes.BOOL), ("xHotspot", wintypes.DWORD),
                    ("yHotspot", wintypes.DWORD), ("hbmMask", wintypes.HBITMAP),
                    ("hbmColor", wintypes.HBITMAP)]

    class BITMAP(ctypes.Structure):
        _fields_ = [("bmType", wintypes.LONG), ("bmWidth", wintypes.LONG),
                    ("bmHeight", wintypes.LONG), ("bmWidthBytes", wintypes.LONG),
                    ("bmPlanes", wintypes.WORD), ("bmBitsPixel", wintypes.WORD),
                    ("bmBits", ctypes.c_void_p)]

    class BMIH(ctypes.Structure):
        _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG),
                    ("biHeight", wintypes.LONG), ("biPlanes", wintypes.WORD),
                    ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                    ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
                    ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD),
                    ("biClrImportant", wintypes.DWORD)]

    ii = ICONINFO()
    if not _user32.GetIconInfo(hicon, ctypes.byref(ii)):
        print(f"  {name}: GetIconInfo fail")
        return
    bm = BITMAP()
    _gdi32.GetObjectW(ii.hbmColor, ctypes.sizeof(BITMAP), ctypes.byref(bm))
    w, h = bm.bmWidth, bm.bmHeight
    hdc = _user32.GetDC(None)
    bmi = BMIH(ctypes.sizeof(BMIH), w, -h, 1, 32, 0, 0, 0, 0, 0, 0)
    buf = ctypes.create_string_buffer(w * h * 4)
    _gdi32.GetDIBits(hdc, ii.hbmColor, 0, h, buf, ctypes.byref(bmi), 0)
    _user32.ReleaseDC(None, hdc)
    _gdi32.DeleteObject(ii.hbmMask)
    _gdi32.DeleteObject(ii.hbmColor)
    px = bytearray(buf.raw)
    for i in range(0, len(px), 4):
        px[i], px[i + 2] = px[i + 2], px[i]  # BGRA→RGBA
    Image.frombytes("RGBA", (w, h), bytes(px)).save(str(Path(gettempdir(), name)))
    print(f"  {name}: {w}x{h} -> {Path(gettempdir(), name)}")


def main() -> int:
    subprocess.Popen(["ms-settings:about"], shell=True) if False else os.startfile("ms-settings:about")
    time.sleep(4.0)
    EnumProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    frames: list[int] = []

    def cb(h, _lp):
        if wm.is_window_visible(h) and not wm.is_cloaked(h) and wm.get_class_name(h) == "ApplicationFrameWindow":
            frames.append(h)
        return True

    _user32.EnumWindows(EnumProc(cb), 0)
    for f in frames:
        pid = wm.pid_of(f)
        print(f"frame hwnd=0x{f:X} pid={pid} class={wm.get_class_name(hf) if False else wm.get_class_name(f)!r} "
              f"title={wm.get_text(f)[:30]!r}")
        path = image_path_of_pid(pid)
        print(f"  frame exe: {path}")
        hi = shell_icon(path)
        print(f"  SHGetFileInfo(frame exe): {'HIT' if hi else 'miss'}")
        if hi:
            dump_icon(hi, "wm_fallback_framehost.png")
            _user32.DestroyIcon(hi)
        core = _user32.FindWindowExW(wintypes.HWND(f), None, "Windows.UI.Core.CoreWindow", None)
        if core:
            cpid = wm.pid_of(core)
            cpath = image_path_of_pid(cpid)
            print(f"  core hwnd=0x{core:X} pid={cpid} exe: {cpath}")
            hc = shell_icon(cpath)
            print(f"  SHGetFileInfo(core exe): {'HIT' if hc else 'miss'}")
            if hc:
                dump_icon(hc, "wm_fallback_app.png")
                _user32.DestroyIcon(hc)
        else:
            print("  core: no CoreWindow child")
    os.system("taskkill /IM SystemSettings.exe /F >nul 2>&1")
    return 0


if __name__ == "__main__":
    sys.exit(main())
