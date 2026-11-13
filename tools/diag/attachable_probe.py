# -*- coding: utf-8 -*-
"""诊断：设置 ApplicationFrameWindow 的 IsAttachable 各判据逐项核对（自拉自收）。"""
import ctypes
import os
import sys
import time
from ctypes import wintypes
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import wm

os.startfile("ms-settings:about")
time.sleep(3.5)
u = ctypes.windll.user32
EP = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
found = []


@EP
def cb(h, _lp):
    if wm.is_window_visible(h) and not wm.is_cloaked(h) and wm.get_class_name(h) == "ApplicationFrameWindow":
        found.append(h)
    return True


u.EnumWindows(cb, 0)
for x in found:
    print(f"hwnd=0x{x:X} iconic={wm.is_iconic(x)} tool={wm.is_toolwindow(x)} "
          f"owner={wm.get_window(x, 4):#x} cloaked={wm.is_cloaked(x)} title={wm.get_text(x)[:24]!r}")
os.system("taskkill /IM SystemSettings.exe /F >nul 2>&1")
