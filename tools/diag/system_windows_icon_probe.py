# -*- coding: utf-8 -*-
"""诊断：资源管理器（CabinetWClass）与 UWP 框架窗（ms-settings）的图标四连查询。
用户报告 snap 接管"系统应用"后宿主任务栏图标回退成应用图标（两子窗素材全 miss），
本探针验证最常见系统窗的两类候选是否真的拿不到图标。

用法: uv run tools/diag/system_windows_icon_probe.py   （自拉自收）
"""
import ctypes
import os
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


def scan(tag: str) -> None:
    EnumProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def cb(h, _lp):
        if wm.is_window_visible(h) and not wm.is_cloaked(h) and not wm.is_iconic(h):
            c = wm.get_class_name(h)
            t = wm.get_text(h)
            if t and ("CabinetWClass" in c or "ApplicationFrame" in c or "CoreWindow" in c
                      or "Shell_TrayWnd" not in c and ("Sett" in t or "设置" in t)):
                print(f"  {tag} {c:30s} {hits(h):10s} {t[:36]} pid={wm.pid_of(h)}")
        return True

    _user32.EnumWindows(EnumProc(cb), 0)


def main() -> int:
    print("== 拉起前 ==")
    scan("before")

    subprocess.Popen(["explorer.exe"], env=wm.host_env())  # 打开一个文件夹窗口
    os.startfile("ms-settings:about")  # UWP 设置（ApplicationFrameWindow 候选）
    time.sleep(4.0)
    print("== 拉起后 ==")
    scan("after ")

    wm.graceful_close_by_name("explorer")  # 只关我们开的文件夹窗（explorer 进程不会退）
    os.system("taskkill /IM SystemSettings.exe /F >nul 2>&1")
    time.sleep(0.8)
    print("DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
