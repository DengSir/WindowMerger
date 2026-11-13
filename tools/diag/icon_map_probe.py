# -*- coding: utf-8 -*-
"""诊断：全系统可见顶层窗的图标四连查询命中地图（TryGetIconSource 同款口径，只读）。
找出"四连全 miss"的窗口类——snap 接管这类窗口时宿主任务栏图标会回退成应用图标
（UpdateHostIcon 拼不到素材），即用户报告的"图标不对"候选根因。

用法: uv run tools/diag/icon_map_probe.py
"""
import ctypes
import sys
from ctypes import wintypes
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import wm

WM_GETICON = 0x7F
ICON_BIG, ICON_SMALL2 = 1, 2
GCLP_HICON, GCLP_HICONSM = -14, -34

_user32 = ctypes.windll.user32
_user32.SendMessageW.restype = ctypes.c_ssize_t
_user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
_user32.GetClassLongPtrW.restype = ctypes.c_ssize_t
_user32.GetClassLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]


def hits(hwnd: int) -> list[str]:
    out = []
    if _user32.SendMessageW(wintypes.HWND(hwnd), WM_GETICON, wintypes.WPARAM(ICON_BIG), wintypes.LPARAM(0)):
        out.append("BIG")
    if _user32.GetClassLongPtrW(wintypes.HWND(hwnd), GCLP_HICON):
        out.append("CLS")
    if _user32.SendMessageW(wintypes.HWND(hwnd), WM_GETICON, wintypes.WPARAM(ICON_SMALL2), wintypes.LPARAM(0)):
        out.append("SM2")
    if _user32.GetClassLongPtrW(wintypes.HWND(hwnd), GCLP_HICONSM):
        out.append("CLSM")
    return out


def main() -> int:
    rows: list[tuple[str, str, str, int]] = []
    EnumProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def cb(h, _lp):
        if wm.is_window_visible(h) and not wm.is_cloaked(h) and not wm.is_iconic(h):
            title = wm.get_text(h)
            if title:
                rows.append((title[:38], wm.get_class_name(h), "+".join(hits(h)) or "NONE",
                             wm.pid_of(h)))
        return True

    _user32.EnumWindows(EnumProc(cb), 0)
    print("== 有图标 ==")
    for t, c, hit, pid in rows:
        if hit != "NONE":
            print(f"  {hit:12s} {c:28s} {t}")
    print("== 四连全 miss（拼图无素材→回退应用图标）==")
    for t, c, hit, pid in rows:
        if hit == "NONE":
            name = "?"
            try:
                import psutil  # noqa
            except ImportError:
                pass
            print(f"  {c:28s} {t}   pid={pid}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
