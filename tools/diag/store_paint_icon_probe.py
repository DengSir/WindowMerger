# -*- coding: utf-8 -*-
"""诊断：商店版 mspaint（ApplicationFrameWindow）的图标四连查询。
UWP 框架窗的图标来自 app tile（shell 走 AUMID），窗口本身可能四连全 miss——
那类窗口被 snap 接管时 UpdateHostIcon 拼不到素材 → 回退/占位（用户报告的图标不对）。

用法: uv run tools/diag/store_paint_icon_probe.py   （自拉自收，不动已开的用户实例）
"""
import ctypes
import subprocess
import sys
import time
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


def hits(hwnd: int) -> str:
    out = []
    if _user32.SendMessageW(wintypes.HWND(hwnd), WM_GETICON, wintypes.WPARAM(ICON_BIG), wintypes.LPARAM(0)):
        out.append("BIG")
    if _user32.GetClassLongPtrW(wintypes.HWND(hwnd), GCLP_HICON):
        out.append("CLS")
    if _user32.SendMessageW(wintypes.HWND(hwnd), WM_GETICON, wintypes.WPARAM(ICON_SMALL2), wintypes.LPARAM(0)):
        out.append("SM2")
    if _user32.GetClassLongPtrW(wintypes.HWND(hwnd), GCLP_HICONSM):
        out.append("CLSM")
    return "+".join(out) or "NONE"


def scan_tag(tag: str) -> None:
    """扫当前可见窗里类名含 ApplicationFrame / CabinetW / Paint 的。"""
    EnumProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def cb(h, _lp):
        if wm.is_window_visible(h) and not wm.is_cloaked(h) and not wm.is_iconic(h):
            c = wm.get_class_name(h)
            t = wm.get_text(h)
            if t and ("ApplicationFrame" in c or "CabinetWClass" in c or "WinUI" in c):
                print(f"  {tag} {c:30s} {hits(h):10s} {t[:36]} pid={wm.pid_of(h)}")
        return True

    _user32.EnumWindows(EnumProc(cb), 0)


def main() -> int:
    print("== 拉起前 ==")
    scan_tag("before")
    subprocess.Popen(["mspaint.exe"], env=wm.host_env())
    wins: list[tuple[str, int]] = []
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        wins = wm.main_windows_by_name("mspaint", "PaintApp", "Paint")
        if wins:
            break
        time.sleep(0.3)
    time.sleep(2.0)  # store Paint 首帧就绪
    print(f"== 拉起后 main_windows_by_name={wins} ==")
    scan_tag("after ")
    for _, h in wins:
        print(f"  direct hwnd=0x{h:X} class={wm.get_class_name(h)!r} hits={hits(h)} "
              f"title={wm.get_text(h)[:36]!r}")
    wm.graceful_close_by_name("mspaint")
    wm.graceful_close_by_name("PaintApp")
    time.sleep(1.0)
    wm.force_kill_by_name("mspaint", "PaintApp")
    return 0


if __name__ == "__main__":
    sys.exit(main())
