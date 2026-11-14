# -*- coding: utf-8 -*-
"""高 DPI 屏 snap 捕捉复现探针（非常驻回归）：在 4K@150 主屏上摆两个 EFB 贴合的
**ctypes 直建 Win32 窗口**（本进程 PMv2，几何 1:1 自洽——Tk 靶是 SystemAware，
混合 DPI 下自我缩放几何不可控），依次验证 --detect-snap 检测 → 接管 → 双窗吸附 →
释放还原。桌面原有的漂浮大窗（盖住布局）正是回归目标：贪心去重叠会抓不到、
贴合子集搜索应命中。等待期间持续泵本进程消息——靶窗线程不泵消息时宿主跨进程
SendMessage/SetWindowPos 会挂死宿主 UI 线程（窗口永不显示）。
用法: uv run tools/diag/snap_hdpi_repro.py
警告: 强杀所有 WindowMerger + 删 config-snap-repro.json。
标记（英文）：ALIGN / DETECT / TAKEOVER / ATTACHED / HOST_RECT / RELEASE / DONE / FAIL_*
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
# 缺 argtypes 时 LPARAM 大值（CREATESTRUCT 指针等）按 c_int 转换会 OverflowError
_u.DefWindowProcW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM)


class WNDCLASSW(ctypes.Structure):
    _fields_ = [("style", ctypes.c_uint), ("lpfnWndProc", WNDPROC),
                ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int),
                ("hInstance", wt.HINSTANCE), ("hIcon", wt.HICON),
                ("hCursor", ctypes.c_void_p), ("hbrBackground", wt.HBRUSH),
                ("lpszMenuName", wt.LPCWSTR), ("lpszClassName", wt.LPCWSTR)]


# 回调/类对象必须模块级保活：RegisterClassW 只存指针，局部对象被 GC 后窗口一收
# 消息就崩
_WNDPROC_OBJ = WNDPROC(_u.DefWindowProcW)
_CLASSES: list[tuple[str, WNDCLASSW]] = []


def register_class(class_name: str, hinst) -> WNDCLASSW:
    wc = WNDCLASSW()
    wc.lpfnWndProc = _WNDPROC_OBJ
    wc.hInstance = hinst
    wc.lpszClassName = class_name
    if not _u.RegisterClassW(ctypes.byref(wc)):
        raise OSError("RegisterClassW failed")
    _CLASSES.append((class_name, wc))  # 保活至窗口销毁
    return wc


def make_win(title: str, class_name: str, hinst) -> int:
    WS_OVERLAPPEDWINDOW = 0x00CF0000
    WS_VISIBLE = 0x10000000
    h = _u.CreateWindowExW(0, class_name, title, WS_OVERLAPPEDWINDOW | WS_VISIBLE,
                           100, 100, 600, 400, None, None, hinst, None)
    if not h:
        raise OSError("CreateWindowExW failed")
    return h


def destroy_win(h: int, class_name: str, hinst) -> None:
    _u.DestroyWindow(wt.HWND(h))
    _u.UnregisterClassW(class_name, hinst)


def pump(seconds: float) -> None:
    """泵本进程窗口消息（见文件头）：等待期间必须持续泵，否则宿主挂死。"""
    msg = wt.MSG()
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        while _u.PeekMessageW(byref(msg), None, 0, 0, 1):  # PM_REMOVE
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
    e = wm.ext_frame_bounds(h)
    print(f"  align final efb={e.as_tuple() if e else None}")
    return False


def detect_once() -> dict:
    p = subprocess.run([wm.exe_path(), "--detect-snap"], capture_output=True,
                       text=True, encoding="utf-8")
    try:
        return json.loads(p.stdout)
    except Exception:
        return {"ok": False, "reason": "BAD_JSON", "detail": p.stdout + p.stderr}


def main() -> int:
    wm.force_kill_by_name("WindowMerger")
    pump(0.8)

    mons = wm.monitors()
    m = next(mi for mi in mons if mi.rcMonitor.Left == 0 and mi.rcMonitor.Top == 0
             and mi.rcMonitor.Right > 2000)  # 4K 主屏（150%）
    wa = m.rcWork
    dpi = wm.monitor_dpi(m)
    print(f"REPRO on wa=({wa.Left},{wa.Top})-({wa.Right},{wa.Bottom}) dpi={dpi}")

    hinst = ctypes.windll.kernel32.GetModuleHandleW(None)
    register_class("WM_SnapReproA", hinst)
    register_class("WM_SnapReproB", hinst)
    ha = make_win("WM_SNAP_A", "WM_SnapReproA", hinst)
    hb = make_win("WM_SNAP_B", "WM_SnapReproB", hinst)
    print(f"TARGETS a={ha} b={hb}")
    pump(0.5)

    mid_x = (wa.Left + wa.Right) // 2
    ok_a = efb_align(ha, (wa.Left, wa.Top, mid_x, wa.Bottom))
    ok_b = efb_align(hb, (mid_x, wa.Top, wa.Right, wa.Bottom))
    ea, eb = wm.ext_frame_bounds(ha), wm.ext_frame_bounds(hb)
    print(f"ALIGN a={ok_a} b={ok_b} "
          f"efb_a={ea.as_tuple() if ea else None} efb_b={eb.as_tuple() if eb else None}")
    pre_a, pre_b = wm.get_window_rect(ha), wm.get_window_rect(hb)

    pump(0.5)
    d = detect_once()
    print(f"DETECT {json.dumps(d, ensure_ascii=False)}")

    if not d.get("ok"):
        print("FAIL_DETECT")
        destroy_win(ha, "WM_SnapReproA", hinst)
        destroy_win(hb, "WM_SnapReproB", hinst)
        return 1
    if d.get("left") not in (ha, hb):
        print(f"FAIL_HWNDS detect left={d.get('left')} a={ha} b={hb}")
        destroy_win(ha, "WM_SnapReproA", hinst)
        destroy_win(hb, "WM_SnapReproB", hinst)
        return 1

    subprocess.Popen([wm.exe_path(), "--left-hwnd", str(ha), "--right-hwnd", str(hb),
                      "--profile", "snap-repro"])
    host = 0
    for _ in range(150):  # 30s：WPF 冷启动在繁忙桌面可能较慢
        host = wm.find_window_by_title("窗口合并 WindowMerger")
        if host:
            break
        pump(0.2)
    print(f"TAKEOVER host={host}")
    if not host:
        print("FAIL_NO_HOST")
        destroy_win(ha, "WM_SnapReproA", hinst)
        destroy_win(hb, "WM_SnapReproB", hinst)
        return 1

    attached = wm.wait_until(lambda: wm.is_attached(ha) and wm.is_attached(hb), 10000, 200)
    notices = []
    for _ in range(6):  # 报因单槽会被 250ms 空闲文案覆盖，连抓 6 次留痕
        st = wm_uia.status_text(host)
        if st:
            notices.append(st)
        pump(0.15)
    print(f"ATTACHED attached={attached} corner_a={wm.corner_pref(ha)} "
          f"corner_b={wm.corner_pref(hb)}")
    print(f"NOTICES {notices}")

    r = wm.get_window_rect(host)
    print(f"HOST_RECT ({r.Left},{r.Top})-({r.Right},{r.Bottom}) "
          f"zoomed={wm.is_zoomed(host)} wa=({wa.Left},{wa.Top})-({wa.Right},{wa.Bottom})")

    wm.post_close(host)
    for _ in range(50):
        if not wm.pids_by_name("WindowMerger"):
            break
        pump(0.2)
    ra, rb = wm.get_window_rect(ha), wm.get_window_rect(hb)
    back = (bool(ra) and all(abs(x - y) <= 3 for x, y in zip(ra.as_tuple(), pre_a.as_tuple()))
            and bool(rb) and all(abs(x - y) <= 3 for x, y in zip(rb.as_tuple(), pre_b.as_tuple())))
    print(f"RELEASE back={back} a={ra.as_tuple() if ra else None} "
          f"b={rb.as_tuple() if rb else None}")

    # ---------- S4 报因路径抽查（本机无干净屏，CI 才覆盖；子集搜索新分类器自证）----------
    register_class("WM_SnapReproC", hinst)
    hc = make_win("WM_SNAP_C", "WM_SnapReproC", hinst)
    w3 = (wa.Right - wa.Left) // 3
    ok3 = (efb_align(ha, (wa.Left, wa.Top, wa.Left + w3, wa.Bottom))
           and efb_align(hb, (wa.Left + w3, wa.Top, wa.Left + w3 * 2, wa.Bottom))
           and efb_align(hc, (wa.Left + w3 * 2, wa.Top, wa.Right, wa.Bottom)))
    pump(0.5)
    d3 = detect_once()
    print(f"S4_THIRDS aligned={ok3} -> {d3.get('reason')} (期望 TOO_MANY:3)")
    sh_ok = (efb_align(ha, (wa.Left, wa.Top, wa.Right, wa.Top + (wa.Bottom - wa.Top) // 2))
             and efb_align(hb, (wa.Left, wa.Top + (wa.Bottom - wa.Top) // 2,
                                wa.Right, wa.Bottom)))
    pump(0.5)
    ds = detect_once()
    print(f"S4_STACKED aligned={sh_ok} -> {ds.get('reason')} (期望 STACKED)")
    gap_ok = (efb_align(ha, (wa.Left, wa.Top, mid_x - 10, wa.Bottom))
              and efb_align(hb, (mid_x + 10, wa.Top, wa.Right, wa.Bottom)))
    pump(0.5)
    dg = detect_once()
    print(f"S4_GAP aligned={gap_ok} -> {dg.get('reason')} (期望 NO_LAYOUT)")

    destroy_win(hc, "WM_SnapReproC", hinst)
    destroy_win(ha, "WM_SnapReproA", hinst)
    destroy_win(hb, "WM_SnapReproB", hinst)
    pcfg = os.path.join(os.environ["APPDATA"], "WindowMerger", "config-snap-repro.json")
    if os.path.exists(pcfg):
        os.remove(pcfg)
    print("DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
