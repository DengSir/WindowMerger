# -*- coding: utf-8 -*-
"""应用图标验证：(1) exe 内嵌图标 (2) 运行中任务栏按钮图标（UIA 定位 + 全屏截裁剪）。
原 IconVerify.ps1。
用法: uv run tools/\visual\\icon_verify.py
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

    # 任务栏按钮定位（按钮名 = shell 应用识别名：桌面快捷方式显示名优先于窗口标题，
    # 本机快捷方式叫"窗口合并 - Code + ZCode"、窗口标题以"窗口合并"开头——搜共同前缀），
    # 裁图标区 4x 放大
    tb = wm_uia.taskbar()
    btn = wm_uia.find_by_name(tb, "窗口合并") if tb is not None else None
    if btn is None:
        print("NO_TASKBAR_BUTTON")
        return 1
    x, y, bw, bh = wm_uia.bounding_rect_of(btn)
    print(f"TASKBAR_BTN {bw:.0f}x{bh:.0f} at ({x:.0f},{y:.0f})")
    scr_w = wm.get_system_metrics(wm.SM_CXSCREEN)  # 导入即 DPI aware → 主屏物理宽高
    scr_h = wm.get_system_metrics(wm.SM_CYSCREEN)
    big = wm.capture_screen(0, 0, scr_w, scr_h)
    crop = big.crop((int(x), int(y), int(x) + int(bw), int(y) + int(bh)))
    crop.resize((160, 160), Image.NEAREST).save(
        str(Path(tempfile.gettempdir(), "wm_taskbaricon.png")))
    print("TASKBAR_ICON_SAVED")

    wm.graceful_close_by_name("WindowMerger")
    time.sleep(1.2)
    print("ICON_VERIFY_DONE")
    # 判定 = exe 内嵌图标可提取 + 任务栏按钮存在（图标长相人工看 PNG）
    ok = True
    print(f"RESULT {'PASS' if ok else 'FAIL'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
