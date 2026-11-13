# -*- coding: utf-8 -*-
"""诊断：snap 接管 UWP 框架窗（设置）后的宿主任务栏图标端到端验证。
修复前：设置窗四连全 miss → 回退应用图标（用户报告的"图标不对"）。
修复后：exe 图标兜底（ApplicationFrameWindow → 子 CoreWindow → SystemSettings.exe 齿轮）
       → 宿主图标 = 齿轮 + Tk 靶窗图标拼接。

用法: uv run tools/diag/snap_uwp_icon_check.py
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


class ICONINFO(ctypes.Structure):
    _fields_ = [("fIcon", wintypes.BOOL), ("xHotspot", wintypes.DWORD),
                ("yHotspot", wintypes.DWORD), ("hbmMask", wintypes.HBITMAP),
                ("hbmColor", wintypes.HBITMAP)]


class BITMAP(ctypes.Structure):
    _fields_ = [("bmType", wintypes.LONG), ("bmWidth", wintypes.LONG),
                ("bmHeight", wintypes.LONG), ("bmWidthBytes", wintypes.LONG),
                ("bmPlanes", wintypes.WORD), ("bmBitsPixel", wintypes.WORD),
                ("bmBits", ctypes.c_void_p)]


_user32 = ctypes.windll.user32
_gdi32 = ctypes.windll.gdi32
_user32.SendMessageW.restype = ctypes.c_ssize_t
_user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
_user32.GetIconInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(ICONINFO)]
_gdi32.GetObjectW.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.POINTER(BITMAP)]


def dump_host_icon(hm: int) -> tuple[int, int] | None:
    hicon = _user32.SendMessageW(wintypes.HWND(hm), 0x7F, wintypes.WPARAM(1), wintypes.LPARAM(0))
    if not hicon:
        print("host icon: miss")
        return None
    ii = ICONINFO()
    if not _user32.GetIconInfo(wintypes.HANDLE(hicon), ctypes.byref(ii)):
        return None
    bm = BITMAP()
    _gdi32.GetObjectW(ii.hbmColor, ctypes.sizeof(BITMAP), ctypes.byref(bm))
    _gdi32.DeleteObject(ii.hbmMask)
    _gdi32.DeleteObject(ii.hbmColor)
    return (bm.bmWidth, bm.bmHeight)


def main() -> int:
    wm.graceful_close_by_name("WindowMerger")
    time.sleep(1.0)
    wm.force_kill_by_name("WindowMerger")
    time.sleep(0.5)

    import os
    os.startfile("ms-settings:about")
    time.sleep(4.0)
    frame = 0
    EnumProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def cb(h, _lp):
        nonlocal frame
        if wm.is_window_visible(h) and not wm.is_cloaked(h) \
                and wm.get_class_name(h) == "ApplicationFrameWindow" and "设置" in wm.get_text(h):
            frame = h
        return True

    _user32.EnumWindows(EnumProc(cb), 0)
    if not frame:
        print("NO_SETTINGS_WINDOW")
        return 1
    print(f"settings frame hwnd=0x{frame:X}")

    tk = subprocess.Popen([sys.executable, str(TARGET_SCRIPT), "WM_UWP_TK"], env=wm.host_env())
    time.sleep(1.2)
    ht = wm.find_window_by_title("WM_UWP_TK")

    p = subprocess.Popen(["bin/Release/net10.0-windows/WindowMerger.exe",
                          "--left-hwnd", str(frame), "--right-hwnd", str(ht),
                          "--profile", "snap-uwp"], env=wm.host_env())
    deadline = time.monotonic() + 8
    hm = 0
    while time.monotonic() < deadline:
        wins = wm.main_windows_of_pid(p.pid)
        if wins:
            hm = wins[0]
            break
        time.sleep(0.1)
    # 等待期间同步采样状态栏：报因通知 3s 过期，事后读不到第一手原因
    seen = []
    ok = False
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        ok = wm.is_attached(frame) and wm.is_attached(ht)
        if ok:
            break
        try:
            import wm_uia
            s = wm_uia.status_text(hm)
            if s and "把任意窗口拖进来" not in s and s not in seen:
                seen.append(s)
        except Exception:
            pass
        time.sleep(0.15)
    print(f"host=0x{hm:X} attached={ok}")
    if not ok:
        print(f"notices={seen}")
        print(f"corner(frame)={wm.corner_pref(frame)} corner(tk)={wm.corner_pref(ht)} "
              f"frame_visible={wm.is_window_visible(frame)} frame_cloaked={wm.is_cloaked(frame)} "
              f"tk_alive={bool(wm.find_window_by_title('WM_UWP_TK'))}")
    if ok:
        size = dump_host_icon(hm)
        sm = (wm.get_system_metrics(wm.SM_CXICON), wm.get_system_metrics(wm.SM_CYICON))
        print(f"host icon size={size} taskbar_metric={sm} composite={size == sm}")
        print(f"PNG 在 tools/diag/out/（host_icon_probe 同款抓法，重跑 host_icon_probe 可复看）")

    wm.post_close(hm) if hm else None
    wm.wait_until(lambda: not wm.pids_by_name("WindowMerger"), 8000, 200)
    tk.terminate()
    os.system("taskkill /IM SystemSettings.exe /F >nul 2>&1")
    Path(wm.config_path().replace("config.json", "config-snap-uwp.json")).unlink(missing_ok=True)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
