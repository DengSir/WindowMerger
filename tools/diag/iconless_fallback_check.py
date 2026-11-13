# -*- coding: utf-8 -*-
"""诊断：exe 图标兜底的合成链路端到端验证。
造一个"四连全 miss"的可吸附窗口（剥掉 Tk 靶窗的 WM_SETICON/类图标）→ 接管 →
宿主拼图应含 python.exe 的 shell 图标（GetShellIconForWindow 兜底）而非应用占位。

用法: uv run tools/diag/iconless_fallback_check.py
输出: tools/diag/out/host_fallback.png（宿主大图标像素）
"""
import ctypes
import subprocess
import sys
import time
from ctypes import wintypes
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import wm

TARGET_SCRIPT = Path(__file__).resolve().parents[1] / "targets" / "snap_target.py"
OUT = Path(__file__).resolve().parent / "out"
EXE = wm.exe_path()

_user32 = ctypes.windll.user32
_user32.SendMessageW.restype = ctypes.c_ssize_t
_user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
_user32.SetClassLongPtrW.restype = ctypes.c_ssize_t
_user32.SetClassLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]

WM_SETICON = 0x80
ICON_BIG, ICON_SMALL = 1, 0
GCLP_HICON, GCLP_HICONSM = -14, -34
WM_GETICON = 0x7F
ICON_SMALL2 = 2


def strip_icons(h: int) -> None:
    _user32.SendMessageW(wintypes.HWND(h), WM_SETICON, wintypes.WPARAM(ICON_BIG), wintypes.LPARAM(0))
    _user32.SendMessageW(wintypes.HWND(h), WM_SETICON, wintypes.WPARAM(ICON_SMALL), wintypes.LPARAM(0))
    _user32.SetClassLongPtrW(wintypes.HWND(h), GCLP_HICON, 0)
    _user32.SetClassLongPtrW(wintypes.HWND(h), GCLP_HICONSM, 0)


def icon_hits(h: int) -> int:
    n = 0
    if _user32.SendMessageW(wintypes.HWND(h), WM_GETICON, wintypes.WPARAM(ICON_BIG), wintypes.LPARAM(0)):
        n += 1
    if _user32.GetClassLongPtrW(wintypes.HWND(h), GCLP_HICON):
        n += 1
    if _user32.SendMessageW(wintypes.HWND(h), WM_GETICON, wintypes.WPARAM(ICON_SMALL2), wintypes.LPARAM(0)):
        n += 1
    if _user32.GetClassLongPtrW(wintypes.HWND(h), GCLP_HICONSM):
        n += 1
    return n


def wait_window(title: str, timeout_s: float = 8.0) -> int:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        h = wm.find_window_by_title(title)
        if h:
            return h
        time.sleep(0.1)
    return 0


def wait_host(pid: int, timeout_s: float = 8.0) -> int:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        wins = wm.main_windows_of_pid(pid)
        if wins:
            return wins[0]
        time.sleep(0.1)
    return 0


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


_gdi32 = ctypes.windll.gdi32
_gdi32.GetObjectW.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.POINTER(BITMAP)]
_gdi32.GetDIBits.argtypes = [wintypes.HDC, wintypes.HANDLE, wintypes.UINT, wintypes.UINT,
                             ctypes.c_void_p, ctypes.POINTER(BMIH), wintypes.UINT]
_gdi32.DeleteObject.argtypes = [wintypes.HANDLE]


def dump_host_icon(hm: int, name: str) -> tuple[int, int] | None:
    """宿主大图标解码存 PNG（PIL 在 venv 里，icon_verify 同款依赖）。"""
    from PIL import Image
    hicon = _user32.SendMessageW(wintypes.HWND(hm), WM_GETICON, wintypes.WPARAM(ICON_BIG), wintypes.LPARAM(0))
    if not hicon:
        return None
    ii = ICONINFO()
    if not _user32.GetIconInfo(wintypes.HANDLE(hicon), ctypes.byref(ii)):
        return None
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
        px[i], px[i + 2] = px[i + 2], px[i]
    Image.frombytes("RGBA", (w, h), bytes(px)).save(str(OUT / name))
    return (w, h)


def main() -> int:
    wm.graceful_close_by_name("WindowMerger")
    time.sleep(1.0)
    wm.force_kill_by_name("WindowMerger")
    time.sleep(0.5)

    procs = [subprocess.Popen([sys.executable, str(TARGET_SCRIPT), "WM_ICO_A"], env=wm.host_env()),
             subprocess.Popen([sys.executable, str(TARGET_SCRIPT), "WM_ICO_B"], env=wm.host_env())]
    time.sleep(1.2)
    ha = wait_window("WM_ICO_A")
    hb = wait_window("WM_ICO_B")

    strip_icons(ha)
    print(f"stripped A: icon hits={icon_hits(ha)} (期望 0)")
    print(f"B untouched: icon hits={icon_hits(hb)} (期望 ≥1)")

    p = subprocess.Popen([EXE, "--left-hwnd", str(ha), "--right-hwnd", str(hb),
                          "--profile", "snap-ico"], env=wm.host_env())
    hm = wait_host(p.pid)
    ok = wm.wait_until(lambda: wm.is_attached(ha) and wm.is_attached(hb), 10000, 200)
    print(f"host=0x{hm:X} attached={ok}")
    if ok:
        time.sleep(0.8)  # 等空闲重断言落地
        size = dump_host_icon(hm, "host_fallback.png")
        print(f"host icon size={size} -> tools/diag/out/host_fallback.png")

    wm.post_close(hm) if hm else None
    wm.wait_until(lambda: not wm.pids_by_name("WindowMerger"), 8000, 200)
    for pr in procs:
        pr.terminate()
    time.sleep(0.4)
    Path(wm.config_path().replace("config.json", "config-snap-ico.json")).unlink(missing_ok=True)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
