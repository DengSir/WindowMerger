# -*- coding: utf-8 -*-
"""诊断：snap 接管实例的宿主任务栏图标本体探针。
WM_GETICON(ICON_BIG) → GetIconInfo → GetDIBits 解码像素存 PNG，直接看画了什么；
顺带打印子窗口四种图标查询（TryGetIconSource 的同款口径）的命中与尺寸。
预期：吸附后宿主大图标 = 两子窗图标对角拼接（32px@100%）；fallback = 应用 256px 大帧。

用法: uv run tools/diag/host_icon_probe.py
输出: tools/diag/out/*.png + 控制台命中表。会拉起 Tk 靶窗与新 notepad（结束清理）。
"""
import ctypes
import struct
import subprocess
import sys
import time
import zlib
from ctypes import wintypes
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import wm

OUT = Path(__file__).resolve().parent / "out"
OUT.mkdir(exist_ok=True)
TARGET_SCRIPT = Path(__file__).resolve().parents[1] / "targets" / "snap_target.py"

WM_GETICON = 0x7F
ICON_BIG, ICON_SMALL2 = 1, 2
GCLP_HICON, GCLP_HICONSM = -14, -34


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


_user32 = ctypes.windll.user32
_gdi32 = ctypes.windll.gdi32
_user32.GetClassLongPtrW.restype = ctypes.c_ssize_t
_user32.GetClassLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
_user32.SendMessageW.restype = ctypes.c_ssize_t  # LRESULT 是 64 位，默认 c_int 会截断/负数化句柄
_user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
_user32.GetIconInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(ICONINFO)]
_user32.GetDC.argtypes = [wintypes.HWND]
_user32.GetDC.restype = wintypes.HDC
_user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
_gdi32.GetObjectW.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.POINTER(BITMAP)]
_gdi32.GetDIBits.argtypes = [wintypes.HDC, wintypes.HANDLE, wintypes.UINT, wintypes.UINT,
                             ctypes.c_void_p, ctypes.POINTER(BMIH), wintypes.UINT]
_gdi32.DeleteObject.argtypes = [wintypes.HANDLE]


def write_png(path: Path, w: int, h: int, bgra: bytes) -> None:
    """GDI 的 32bpp 自上而下 BGRA → PNG（手写，无 PIL 依赖）。"""
    px = bytearray(w * h * 4)
    for i in range(0, len(bgra), 4):
        px[i], px[i + 1], px[i + 2], px[i + 3] = bgra[i + 2], bgra[i + 1], bgra[i], bgra[i + 3]
    raw = b"".join(b"\x00" + bytes(px[y * w * 4:(y + 1) * w * 4]) for y in range(h))

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    png = (b"\x89PNG\r\n\x1a\n"
           + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))
    path.write_bytes(png)


def hicon_pixels(hicon: int) -> tuple[int, int] | None:
    """HICON → (宽, 高)，并落 PNG（out/icon_<n>.png）；失败返回 None。"""
    ii = ICONINFO()
    if not _user32.GetIconInfo(wintypes.HANDLE(hicon), ctypes.byref(ii)):
        return None
    bm = BITMAP()
    if not _gdi32.GetObjectW(ii.hbmColor, ctypes.sizeof(BITMAP), ctypes.byref(bm)):
        _gdi32.DeleteObject(ii.hbmMask)
        _gdi32.DeleteObject(ii.hbmColor)
        return None
    w, h = bm.bmWidth, bm.bmHeight
    hdc = _user32.GetDC(None)
    bmi = BMIH(ctypes.sizeof(BMIH), w, -h, 1, 32, 0, 0, 0, 0, 0, 0)
    buf = ctypes.create_string_buffer(w * h * 4)
    ok = _gdi32.GetDIBits(hdc, wintypes.HANDLE(ii.hbmColor), 0, h, buf, ctypes.byref(bmi), 0)
    _user32.ReleaseDC(None, hdc)
    _gdi32.DeleteObject(ii.hbmMask)
    _gdi32.DeleteObject(ii.hbmColor)
    if not ok:
        return None
    write_png(OUT / f"icon_{hicon}.png", w, h, buf.raw)
    return (w, h)


def queries(hwnd: int, tag: str) -> None:
    """TryGetIconSource 同款四连查询：打印命中与图标本征尺寸。"""
    names = ["WM_GETICON_BIG", "GCLP_HICON", "WM_GETICON_SMALL2", "GCLP_HICONSM"]
    handles = [
        _user32.SendMessageW(wintypes.HWND(hwnd), WM_GETICON, wintypes.WPARAM(ICON_BIG), wintypes.LPARAM(0)),
        _user32.GetClassLongPtrW(wintypes.HWND(hwnd), GCLP_HICON),
        _user32.SendMessageW(wintypes.HWND(hwnd), WM_GETICON, wintypes.WPARAM(ICON_SMALL2), wintypes.LPARAM(0)),
        _user32.GetClassLongPtrW(wintypes.HWND(hwnd), GCLP_HICONSM),
    ]
    for name, h in zip(names, handles):
        if h:
            size = hicon_pixels(h)
            print(f"  {tag:12s} {name:18s} HIT hicon=0x{h:X} size={size}")
        else:
            print(f"  {tag:12s} {name:18s} miss")


def wait_attached(*hwnds: int, timeout_s: float = 10.0) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if all(wm.is_attached(h) for h in hwnds):
            return True
        time.sleep(0.2)
    return False


def wait_host(pid: int, timeout_s: float = 8.0) -> int:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        wins = wm.main_windows_of_pid(pid)
        if wins:
            return wins[0]
        time.sleep(0.1)
    return 0


def close_host(hm: int) -> None:
    wm.post_close(hm)
    wm.wait_until(lambda: not wm.pids_by_name("WindowMerger"), 8000, 200)
    time.sleep(0.4)


def main() -> int:
    wm.graceful_close_by_name("WindowMerger")
    time.sleep(1.0)
    wm.force_kill_by_name("WindowMerger")
    time.sleep(0.5)

    # 靶窗：两个 Tk 窗（自有进程，安全）+ 新拉起的 notepad（真实应用图标参照）
    procs = [subprocess.Popen([sys.executable, str(TARGET_SCRIPT), "WM_ICON_A"], env=wm.host_env()),
             subprocess.Popen([sys.executable, str(TARGET_SCRIPT), "WM_ICON_B"], env=wm.host_env())]
    np = subprocess.Popen(["notepad.exe"], env=wm.host_env())
    time.sleep(1.5)
    ha = wm.find_window_by_title("WM_ICON_A")
    hb = wm.find_window_by_title("WM_ICON_B")
    hn = wm.find_window_by_title("Notepad") or (
        wm.main_windows_by_name("Notepad") or [(None, 0)])[0][1] if wm.main_windows_by_name("Notepad") else 0
    print(f"targets: A=0x{ha:X} B=0x{hb:X} notepad=0x{hn:X}")

    print("== 子窗口图标四连查询（TryGetIconSource 口径）==")
    queries(ha, "TkA")
    queries(hb, "TkB")
    if hn:
        queries(hn, "notepad")

    def run_flow(tag: str, args: list[str]) -> None:
        p = subprocess.Popen(["bin/Release/net10.0-windows/WindowMerger.exe"] + args, env=wm.host_env())
        hm = wait_host(p.pid)
        if not hm:
            print(f"== {tag}: NO HOST ==")
            return
        attached = wait_attached(ha, hb)
        print(f"== {tag}: host=0x{hm:X} attached={attached} ==")
        if attached:
            queries(hm, "host")
        close_host(hm)

    run_flow("FLOW_B hwnd直连(TkA+TkB)",
             ["--left-hwnd", str(ha), "--right-hwnd", str(hb), "--profile", "snap-probe"])
    if hn:
        run_flow("FLOW_C hwnd直连(notepad+TkB)",
                 ["--left-hwnd", str(hn), "--right-hwnd", str(hb), "--profile", "snap-probe"])

    # 清理
    for p in procs:
        p.terminate()
    wm.post_close(hn) if hn else None
    time.sleep(0.8)
    wm.force_kill_by_name("Notepad")
    Path(wm.config_path().replace("config.json", "config-snap-probe.json")).unlink(missing_ok=True)
    print("PNG 输出在 tools/diag/out/（文件名含 HICON 句柄值）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
