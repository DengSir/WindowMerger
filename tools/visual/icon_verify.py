# -*- coding: utf-8 -*-
"""应用图标验证：(1) exe 内嵌图标 (2) 运行中任务栏按钮图标（UIA 定位 + 全屏截裁剪）。
原 IconVerify.ps1。
用法: py tools\\visual\\icon_verify.py
截图: %TEMP%\\wm_exeicon.png / wm_taskbaricon.png
"""
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import wm
import wm_uia


def main() -> int:
    # 1. exe 内嵌图标（ApplicationIcon）
    exe = wm.exe_path()
    # .NET ExtractAssociatedIcon 等价：shell 图标按本征尺寸取（GetSystemMetrics 随 DPI）
    import ctypes
    import ctypes.wintypes as wt

    class SHFILEINFOW(ctypes.Structure):
        _fields_ = [("hIcon", wt.HICON), ("iIcon", ctypes.c_int),
                    ("dwAttributes", wt.DWORD), ("szDisplayName", ctypes.c_wchar * 260),
                    ("szTypeName", ctypes.c_wchar * 80)]

    shgfi_icon = 0x100
    shell32 = ctypes.WinDLL("shell32")
    info = SHFILEINFOW()
    shell32.SHGetFileInfoW(exe, 0, ctypes.byref(info), ctypes.sizeof(SHFILEINFOW), shgfi_icon)
    if not info.hIcon:
        print("NO_EMBEDDED_ICON")
        return 1
    # HICON → PIL（GetDIBits 方式）
    user32, gdi32 = ctypes.WinDLL("user32"), ctypes.WinDLL("gdi32")
    ico_w = wm.get_system_metrics(wm.SM_CXICON)
    ico_h = wm.get_system_metrics(wm.SM_CYICON)
    hdc_screen = user32.GetDC(0)
    hdc_mem = gdi32.CreateCompatibleDC(hdc_screen)
    bmp = gdi32.CreateCompatibleBitmap(hdc_screen, ico_w, ico_h)
    gdi32.SelectObject(hdc_mem, bmp)
    user32.DrawIconEx(hdc_mem, 0, 0, info.hIcon, ico_w, ico_h, 0, None, 0x3)
    class BIH(ctypes.Structure):
        _fields_ = [("biSize", wt.DWORD), ("biWidth", ctypes.c_long), ("biHeight", ctypes.c_long),
                    ("biPlanes", wt.WORD), ("biBitCount", wt.WORD), ("biCompression", wt.DWORD),
                    ("biSizeImage", wt.DWORD), ("biXPelsPerMeter", ctypes.c_long),
                    ("biYPelsPerMeter", ctypes.c_long), ("biClrUsed", wt.DWORD),
                    ("biClrImportant", wt.DWORD)]
    bi = BIH()
    bi.biSize, bi.biWidth, bi.biHeight = ctypes.sizeof(BIH), ico_w, -ico_h
    bi.biPlanes, bi.biBitCount = 1, 32
    buf = ctypes.create_string_buffer(ico_w * ico_h * 4)
    gdi32.GetDIBits(hdc_mem, bmp, 0, ico_h, buf, ctypes.byref(bi), 0)
    Image.frombuffer("RGB", (ico_w, ico_h), buf.raw, "raw", "BGRX", 0, 1
                     ).save(str(Path(tempfile.gettempdir(), "wm_exeicon.png")))
    gdi32.DeleteObject(bmp)
    gdi32.DeleteDC(hdc_mem)
    user32.ReleaseDC(0, hdc_screen)
    user32.DestroyIcon(info.hIcon)
    print("EXE_ICON_SAVED")

    # 2. 启动无吸附实例 → 回退图标路径
    subprocess.Popen([exe])
    time.sleep(3)
    hm = wm.host_hwnd()
    if not hm:
        print("NO_HOST")
        return 1

    # 任务栏按钮定位（名字含 WindowMerger），裁图标区 4x 放大
    root = wm_uia.root_element()
    cond = wm_uia.property_condition(wm_uia.UIA_CLASSNAME_PROPERTY_ID, "Shell_TrayWnd")
    taskbar = wm_uia.find_first(root, cond, wm_uia.UIA_TREE_SCOPE_CHILDREN)
    btn = None
    if taskbar is not None:
        btn = wm_uia.find_by_name(taskbar, "WindowMerger")
    if btn is None:
        print("NO_TASKBAR_BUTTON")
        return 1
    x, y, bw, bh = wm_uia.bounding_rect_of(btn)
    print(f"TASKBAR_BTN {bw:.0f}x{bh:.0f} at ({x:.0f},{y:.0f})")
    big = wm.capture_screen(0, 0, 2560, 1440)
    crop = big.crop((int(x), int(y), int(x) + int(bw), int(y) + int(bh)))
    crop.resize((160, 160), Image.NEAREST).save(
        str(Path(tempfile.gettempdir(), "wm_taskbaricon.png")))
    print("TASKBAR_ICON_SAVED")

    wm.graceful_close_by_name("WindowMerger")
    time.sleep(1.2)
    print("ICON_VERIFY_DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
