# -*- coding: utf-8 -*-
"""snap 接管实例还原路径探针（非常驻回归）：4K@150 屏摆两个 EFB 贴合靶窗 →
接管（最大化）→ 还原按钮(_maxButton UIA Invoke) 观察宿主还原矩形是否 = 派生
并集矩形（吸附布局），定位"snap 实例改变宿主大小"。
用法: uv run tools/diag/snap_restore_probe.py
警告: 强杀所有 WindowMerger。
标记（英文）：ALIGN / DETECT / MAXIMIZED / RESTORE_BTN / DONE / FAIL_*
"""
import ctypes
import ctypes.wintypes as wt
import json
import os
import subprocess
import sys
import time
from ctypes import byref
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import wm  # noqa: E402
import wm_uia  # noqa: E402

SWP_FLAGS = wm.SWP_NOZORDER | wm.SWP_NOACTIVATE
_u = ctypes.windll.user32
_u.CreateWindowExW.restype = wt.HWND
_u.CreateWindowExW.argtypes = [wt.DWORD, wt.LPCWSTR, wt.LPCWSTR, wt.DWORD,
                               ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                               wt.HWND, wt.HMENU, wt.HINSTANCE, wt.LPVOID]
_u.DefWindowProcW.restype = ctypes.c_ssize_t
_u.DefWindowProcW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM)


class WNDCLASSW(ctypes.Structure):
    _fields_ = [("style", ctypes.c_uint), ("lpfnWndProc", WNDPROC),
                ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int),
                ("hInstance", wt.HINSTANCE), ("hIcon", wt.HICON),
                ("hCursor", ctypes.c_void_p), ("hbrBackground", wt.HBRUSH),
                ("lpszMenuName", wt.LPCWSTR), ("lpszClassName", wt.LPCWSTR)]


_WNDPROC_OBJ = WNDPROC(_u.DefWindowProcW)
_CLASSES: list[tuple[str, WNDCLASSW]] = []


def register_class(class_name: str, hinst) -> None:
    wc = WNDCLASSW()
    wc.lpfnWndProc = _WNDPROC_OBJ
    wc.hInstance = hinst
    wc.lpszClassName = class_name
    if not _u.RegisterClassW(ctypes.byref(wc)):
        raise OSError("RegisterClassW failed")
    _CLASSES.append((class_name, wc))


def make_win(title: str, class_name: str, hinst) -> int:
    WS_OVERLAPPEDWINDOW = 0x00CF0000
    WS_VISIBLE = 0x10000000
    h = _u.CreateWindowExW(0, class_name, title, WS_OVERLAPPEDWINDOW | WS_VISIBLE,
                           100, 100, 600, 400, None, None, hinst, None)
    if not h:
        raise OSError("CreateWindowExW failed")
    return h


def pump(seconds: float) -> None:
    msg = wt.MSG()
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        while _u.PeekMessageW(byref(msg), None, 0, 0, 1):
            _u.TranslateMessage(byref(msg))
            _u.DispatchMessageW(byref(msg))
        time.sleep(0.05)


def efb_align(h: int, target: tuple[int, int, int, int]) -> bool:
    for _ in range(8):
        e = wm.ext_frame_bounds(h)
        if e is None:
            return False
        dx, dy = target[0] - e.Left, target[1] - e.Top
        dw, dh = target[2] - e.Right, target[3] - e.Bottom
        if max(abs(dx), abs(dy), abs(dw), abs(dh)) <= 1:
            return True
        r = wm.get_window_rect(h)
        wm.set_window_pos(h, None, r.Left + dx, r.Top + dy,
                          r.width + dw, r.height + dh, SWP_FLAGS)
        pump(0.08)
    return False


def detect_once() -> dict:
    p = subprocess.run([wm.exe_path(), "--detect-snap"], capture_output=True,
                       text=True, encoding="utf-8")
    try:
        return json.loads(p.stdout)
    except Exception:
        return {"ok": False, "reason": "BAD_JSON"}


def show(tag: str, h: int, expect: tuple[int, int, int, int] | None) -> None:
    r = wm.get_window_rect(h)
    z = wm.is_zoomed(h)
    ok = (r is not None and expect is not None
          and all(abs(x - y) <= 4 for x, y in zip(r.as_tuple(), expect)))
    print(f"{tag} zoomed={z} rect={r.as_tuple() if r else None} expect={expect} "
          f"{'OK' if ok else 'MISMATCH'}")


def main() -> int:
    screen = "main" if "--screen" not in sys.argv else sys.argv[sys.argv.index("--screen") + 1]
    wm.force_kill_by_name("WindowMerger")
    pcfg = Path(os.environ["APPDATA"]) / "WindowMerger" / "config-snap-repro.json"
    if pcfg.exists():
        pcfg.unlink()  # 清掉上次尺寸记忆，验证默认正常态几何
    pump(0.8)
    mons = wm.monitors()
    m = (next(mi for mi in mons if mi.rcMonitor.Left == 0 and mi.rcMonitor.Top == 0
              and mi.rcMonitor.Right > 2000)  # 4K 主屏（150%）
         if screen == "main" else
         min(mons, key=lambda mi: mi.rcMonitor.Left))  # 最左（96 DPI）屏
    wa = m.rcWork
    print(f"REPRO on wa=({wa.Left},{wa.Top})-({wa.Right},{wa.Bottom}) "
          f"dpi={wm.monitor_dpi(m)}")

    hinst = ctypes.windll.kernel32.GetModuleHandleW(None)
    register_class("WM_SnapReproA", hinst)
    register_class("WM_SnapReproB", hinst)
    ha = make_win("WM_SNAP_A", "WM_SnapReproA", hinst)
    hb = make_win("WM_SNAP_B", "WM_SnapReproB", hinst)
    pump(0.5)
    mid_x = (wa.Left + wa.Right) // 2
    ok = (efb_align(ha, (wa.Left, wa.Top, mid_x, wa.Bottom))
          and efb_align(hb, (mid_x, wa.Top, wa.Right, wa.Bottom)))
    print(f"ALIGN a={ok}")
    pump(0.5)
    d = detect_once()
    print(f"DETECT {json.dumps(d, ensure_ascii=False)}")
    if not d.get("ok"):
        print("FAIL_DETECT")
        return 1

    subprocess.Popen([wm.exe_path(), "--left-hwnd", str(ha), "--right-hwnd", str(hb),
                      "--profile", "snap-repro"])
    host = 0
    for _ in range(150):
        host = wm.find_window_by_title("窗口合并 WindowMerger")
        if host:
            break
        pump(0.2)
    if not host:
        print("FAIL_NO_HOST")
        return 1
    attached = wm.wait_until(lambda: wm.is_attached(ha) and wm.is_attached(hb), 10000, 200)
    pump(1.0)
    union = (wa.Left, wa.Top, wa.Right, wa.Bottom)
    print(f"ATTACHED={attached}")
    show("MAXIMIZED", host, union)

    # 正常态几何 = 960×600 DIP × 屏 DPI 居中于布局屏（不再取并集——并集≈工作区会让
    # 取消最大化落回同样大的矩形）；还原按钮应落到该矩形，两窗缩进格子
    scale = wm.get_dpi_for_window(host) / 96.0
    dw, dh = round(960 * scale), round(600 * scale)
    expect = (wa.Left + (wa.Right - wa.Left - dw) // 2,
              wa.Top + (wa.Bottom - wa.Top - dh) // 2,
              wa.Left + (wa.Right - wa.Left - dw) // 2 + dw,
              wa.Top + (wa.Bottom - wa.Top - dh) // 2 + dh)
    wm_uia.invoke(wm_uia.find_by_automation_id(wm_uia.element_from_handle(host),
                                               "_maxButton"))
    pump(1.5)
    show("RESTORE_BTN", host, expect)

    wm.post_close(host)
    for _ in range(50):
        if not wm.pids_by_name("WindowMerger"):
            break
        pump(0.2)
    pcfg = Path(os.environ["APPDATA"]) / "WindowMerger" / "config-snap-repro.json"
    if pcfg.exists():
        pcfg.unlink()
    print("DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
