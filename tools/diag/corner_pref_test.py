# -*- coding: utf-8 -*-
"""DWMWA_WINDOW_CORNER_PREFERENCE(33) 直角化验证：吸附窗口方形靠 DWM 属性而非窗口样式。

Phase 1 隔离实验：ctypes 造普通 WS_OVERLAPPEDWINDOW 品红窗（不碰任何样式），
默认 Win11 圆角为基线截图 → 只设属性 33 = DONOTROUND → 再截，角部区域前后差分
断言弧形缺口消失 + 属性读回 0→1。
Phase 2 产品实跑（DeleteTab 方案）：mspaint CLI 吸附（先靶窗后宿主），断言吸附子窗
属性 33=1、EXSTYLE 无 toolwindow 位（方案不再改样式）、任务栏画图按钮隐藏、外部
最小化被维护定时器拉回，截子窗 EFB 四角放大图 + Alt+Tab 切换器截图佐证；优雅关
宿主后断言还原（属性回 DEFAULT、任务栏按钮回来）。config.json 先备份后还原。

输出：%TEMP%\\wm_corner\\*.png（角部放大图 / Alt+Tab 切换器）
标记（英文，诊断输出约定）：P1_CORNER_DIFF / P2_BASELINE_BUTTON / P2_ATTR / P2_MIN_HEAL /
ALTTAB_SHOT / P2_RESTORED / PASS / FAIL
"""
import argparse
import ctypes
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import wm  # noqa: E402  导入即 PMv2 + WM_UPDATE_OFF 注入
import wm_uia  # noqa: E402

from PIL import Image  # noqa: E402

OUT_DIR = Path(tempfile.gettempdir()) / "wm_corner"
MAGENTA = 0x00FF00FF          # COLORREF 0x00BBGGRR
CROP = 36                     # 角部截图边长（物理像素）
ZOOM = 8
ATTR = 33                     # DWMWA_WINDOW_CORNER_PREFERENCE
DONOTROUND, DEFAULT = 1, 0

_dwm = ctypes.WinDLL("dwmapi")
_user32 = ctypes.windll.user32
_gdi32 = ctypes.windll.gdi32
_k32 = ctypes.windll.kernel32


def corner_pref(h: int) -> int:
    v = ctypes.c_int(-1)
    _dwm.DwmGetWindowAttribute(ctypes.wintypes.HWND(h), ATTR, ctypes.byref(v), 4)
    return v.value


def set_corner_pref(h: int, val: int) -> int:
    return _dwm.DwmSetWindowAttribute(ctypes.wintypes.HWND(h), ATTR,
                                      ctypes.byref(ctypes.c_int(val)), 4)


def crop_zoom_save(img: Image.Image, box: tuple[int, int, int, int], name: str) -> Image.Image:
    OUT_DIR.mkdir(exist_ok=True)
    crop = img.crop(box)
    zoom = crop.resize(((box[2] - box[0]) * ZOOM, (box[3] - box[1]) * ZOOM), Image.NEAREST)
    p = OUT_DIR / name
    zoom.save(p)
    print(f"  saved {p}")
    return crop


def sample_tl(crop: Image.Image) -> tuple[int, int, int]:
    return crop.getpixel((3, 3))[:3]


def sample_br(crop: Image.Image) -> tuple[int, int, int]:
    return crop.getpixel((crop.width - 4, crop.height - 4))[:3]


# ---------- Phase 1：隔离实验（普通窗，只设属性 33） ----------

def phase1() -> bool:
    from ctypes import wintypes

    WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, wintypes.HWND,
                                 ctypes.c_uint, wintypes.WPARAM, wintypes.LPARAM)

    class PAINTSTRUCT(ctypes.Structure):
        _fields_ = [("hdc", wintypes.HDC), ("fErase", wintypes.BOOL),
                    ("rcPaint", wintypes.RECT), ("fRestore", wintypes.BOOL),
                    ("fIncUpdate", wintypes.BOOL), ("rgbReserved", ctypes.c_byte * 32)]

    class WNDCLASSEXW(ctypes.Structure):
        _fields_ = [("cbSize", ctypes.c_uint), ("style", ctypes.c_uint),
                    ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int),
                    ("cbWndExtra", ctypes.c_int), ("hInstance", wintypes.HINSTANCE),
                    ("hIcon", wintypes.HICON), ("hCursor", ctypes.c_void_p),
                    ("hbrBackground", wintypes.HBRUSH), ("lpszMenuName", wintypes.LPCWSTR),
                    ("lpszClassName", wintypes.LPCWSTR), ("hIconSm", wintypes.HICON)]

    _user32.DefWindowProcW.restype = ctypes.c_ssize_t
    _user32.DefWindowProcW.argtypes = [wintypes.HWND, ctypes.c_uint,
                                       wintypes.WPARAM, wintypes.LPARAM]
    brush = _gdi32.CreateSolidBrush(MAGENTA)

    def proc(h, msg, wp, lp):  # WM_PAINT 手涂品红，其余全默认（标准非客户区框架 = Win11 圆角）
        if msg == 0x000F:
            ps = PAINTSTRUCT()
            hdc = _user32.BeginPaint(h, ctypes.byref(ps))
            _user32.FillRect(hdc, ctypes.byref(ps.rcPaint), wintypes.HBRUSH(brush))
            _user32.EndPaint(h, ctypes.byref(ps))
            return 0
        return _user32.DefWindowProcW(h, msg, wp, lp)

    hinst = _k32.GetModuleHandleW(None)
    wc = WNDCLASSEXW(ctypes.sizeof(WNDCLASSEXW), 0, WNDPROC(proc), 0, 0, hinst,
                     None, None, wintypes.HBRUSH(brush), None, "wm_corner_probe", None)
    if not _user32.RegisterClassExW(ctypes.byref(wc)):
        raise OSError("RegisterClassExW failed")
    WS_OVERLAPPEDWINDOW, WS_VISIBLE = 0x00CF0000, 0x10000000
    x, y = wm.park_on_left_or_primary(420, 340)
    hwnd = _user32.CreateWindowExW(0, "wm_corner_probe", "CORNER_PROBE",
                                   WS_OVERLAPPEDWINDOW | WS_VISIBLE,
                                   x, y, 420, 340, None, None, hinst, None)
    if not hwnd:
        raise OSError("CreateWindowExW failed")
    pump(0.5)  # 等首帧合成 + 消息泵

    def shoot(tag: str):
        wm.set_topmost(hwnd, True)
        time.sleep(0.15)
        img = wm.capture_screen(x, y, 420, 340)
        wm.set_topmost(hwnd, False)  # 截图后必须还原层级（AGENTS 约定）
        tl = crop_zoom_save(img, (0, 0, CROP, CROP), f"p1_tl_{tag}.png")
        br = crop_zoom_save(img, (420 - CROP, 340 - CROP, 420, 340), f"p1_br_{tag}.png")
        return tl, br

    def diff_count(a: Image.Image, b: Image.Image) -> int:
        """角部区域前后差分像素数：圆角→直角只在弧形缺口区不同（约几十像素）。"""
        return sum(1 for px in range(a.width) for py in range(a.height)
                   if a.getpixel((px, py)) != b.getpixel((px, py)))

    print(f"PHASE1 hwnd={hwnd:#x} attr33_before={corner_pref(hwnd)}")
    tl0, br0 = shoot("before")
    hr = set_corner_pref(hwnd, DONOTROUND)
    pump(0.4)
    print(f"PHASE1 set(DONOTROUND) hr={hr:#x} attr33_after={corner_pref(hwnd)}")
    tl1, br1 = shoot("after")
    # 采样点避开 ~7px 隐形边（弧缺口最深处 = 45° 对角附近）：圆角时透壁纸、直角时是窗口
    diag0 = tl0.getpixel((8, 5))[:3]
    diag1 = tl1.getpixel((8, 5))[:3]
    tl_d, br_d = diff_count(tl0, tl1), diff_count(br0, br1)
    ok = corner_pref(hwnd) == DONOTROUND and tl_d > 30 and br_d > 30 and diag0 != diag1
    print(f"P1_CORNER_DIFF tl={tl_d} br={br_d} diag0={diag0} diag1={diag1} "
          f"{'PASS' if ok else 'FAIL'}")
    _user32.DestroyWindow(hwnd)
    return ok


def pump(seconds: float) -> None:
    """消息泵：探针窗必须有人泵消息，否则显示为"未响应"幽灵。"""
    from ctypes import wintypes

    class MSG(ctypes.Structure):
        _fields_ = [("hwnd", wintypes.HWND), ("message", ctypes.c_uint),
                    ("wParam", wintypes.WPARAM), ("lParam", wintypes.LPARAM),
                    ("time", wintypes.DWORD), ("pt", wintypes.POINT)]

    pm_remove = 0x0001
    msg = MSG()
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        while _user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, pm_remove):
            _user32.TranslateMessage(ctypes.byref(msg))
            _user32.DispatchMessageW(ctypes.byref(msg))
        time.sleep(0.02)


# ---------- Phase 2：产品实跑（mspaint CLI 吸附，DeleteTab 隐藏任务栏） ----------

def paint_button_seen() -> bool:
    """任务栏有没有画图按钮（DeleteTab 生效判据；按钮名 = shell 识别名 画图/Paint）。"""
    return any("画图" in n or "paint" in n.lower() for n in wm_uia.dump_taskbar_buttons())


def phase2() -> bool:
    cp = wm.config_path()
    backup = Path(cp).read_text(encoding="utf-8") if os.path.exists(cp) else None

    exe = wm.exe_path()
    if not os.path.exists(exe):
        print("NO_EXE 先 dotnet build -c Release")
        return False
    if wm.main_windows_by_name("mspaint") or wm.host_hwnds():
        print("BUSY 已有 mspaint/WindowMerger 在跑，避免误杀用户实例，跳过")
        return False

    subprocess.Popen(["mspaint"])
    if not wm.wait_until(lambda: wm.main_windows_by_name("mspaint"), 20000):
        print("NO_MSPAINT")
        return False
    target = wm.main_windows_by_name("mspaint")[0][1]
    time.sleep(0.8)  # shell 异步建任务栏按钮
    print(f"P2_BASELINE_BUTTON={paint_button_seen()}")

    subprocess.Popen([exe, "--left", "mspaint"], env=wm.host_env())
    if not wm.wait_until(lambda: wm.host_hwnd() != 0, 15000):
        print("NO_HOST")
        return False
    host = wm.host_hwnd()
    if not wm.wait_until(lambda: wm.is_attached(target), 15000):  # 吸附探针 = 圆角直角化
        print("NO_ATTACH")
        wm.post_close(host)
        return False
    time.sleep(1.0)  # 等维护定时器收敛

    # 宿主钉到测试屏（跨 DPI 两步走：先移动收敛 DPI，再设尺寸）
    if wm.is_zoomed(host) or wm.is_iconic(host):
        wm.show_window(host, wm.SW_RESTORE)
    wa = wm.pick_test_monitor().rcWork
    hw = min(1500, wa.Right - wa.Left - 40)
    hh = min(620, wa.Bottom - wa.Top - 120)
    wm.set_window_pos(host, None, wa.Left + 20, wa.Top + 20, 0, 0,
                      wm.SWP_NOSIZE | wm.SWP_NOZORDER | wm.SWP_NOACTIVATE)
    wm.set_window_pos(host, None, 0, 0, hw, hh,
                      wm.SWP_NOMOVE | wm.SWP_NOZORDER | wm.SWP_NOACTIVATE)
    time.sleep(1.5)  # 子窗跨屏 WM_DPICHANGED 自收敛 + 维护周期

    attr = corner_pref(target)
    tool = wm.is_toolwindow(target)
    btn_hidden = not paint_button_seen()
    print(f"PHASE2 child={target:#x} attr33={attr} toolwindow={tool} taskbar_hidden={btn_hidden}")

    # 自愈冒烟：外部最小化子窗 → 维护定时器拉回（250ms tick，轮询观测不可靠，睡过 6 tick 再断言）
    wm.show_window(target, wm.SW_MINIMIZE)
    time.sleep(1.5)
    healed = not wm.is_iconic(target) and wm.is_attached(target)
    print(f"P2_MIN_HEAL={healed} attr33={corner_pref(target)}")

    # Alt+Tab 注入截图（目视确认切换器没有独立画图缩略图）
    fg_saved = wm.get_foreground_window()
    wm.set_foreground_window(host)
    time.sleep(0.3)
    wm.keybd_event(0x12, 0x38, 0)  # ALT down
    wm.keybd_event(0x09, 0x0F, 0)  # TAB down
    wm.keybd_event(0x09, 0x0F, 2)  # TAB up
    time.sleep(1.0)  # 切换器动画
    OUT_DIR.mkdir(exist_ok=True)
    wm.capture_test_screen().save(OUT_DIR / "alt_tab_attached.png")
    wm.keybd_event(0x1B, 0x01, 0)  # ESC 取消切换
    wm.keybd_event(0x1B, 0x01, 2)
    wm.keybd_event(0x12, 0x38, 2)  # ALT up
    if fg_saved:
        wm.set_foreground_window(fg_saved)
    print(f"ALTTAB_SHOT={OUT_DIR / 'alt_tab_attached.png'}")

    # 子窗四角放大（最小化自愈后重新实测 EFB）
    corners_ok = False
    wm.set_topmost(host, True)  # 只提宿主：子窗 z 序保持"宿主正下方"，勿动
    time.sleep(0.2)
    img = wm.capture_test_screen()
    wm.set_topmost(host, False)
    efb = wm.ext_frame_bounds(target)
    if efb:
        ox = wm.pick_test_monitor().rcMonitor.Left
        oy = wm.pick_test_monitor().rcMonitor.Top
        corners_ok = True
        pts = {"tl": (efb.Left, efb.Top), "tr": (efb.Right - CROP, efb.Top),
               "bl": (efb.Left, efb.Bottom - CROP), "br": (efb.Right - CROP, efb.Bottom - CROP)}
        for tag, (cx, cy) in pts.items():
            crop = crop_zoom_save(img, (cx - ox, cy - oy, cx - ox + CROP, cy - oy + CROP),
                                  f"p2_{tag}.png")
            inner = crop.getpixel((24, 24))[:3]
            edge = sample_tl(crop) if tag == "tl" else sample_br(crop)
            same = wm.color_close(edge, inner, tol=20)
            corners_ok = corners_ok and same
            print(f"  {tag}: edge={edge} inner={inner} {'square-looking' if same else 'arc-ish'}")
    ok = attr == DONOTROUND and not tool and btn_hidden and healed and corners_ok
    print(f"P2_ATTR={attr} P2_NOTOOL={not tool} P2_BTN_HIDDEN={btn_hidden} "
          f"corners={'OK' if corners_ok else 'CHECK'} {'PASS' if ok else 'FAIL'}")

    # 收尾：优雅关宿主（还原 mspaint）→ 断言还原（圆角回默认 + 任务栏按钮回来）→ 清靶窗 → 还原配置
    wm.post_close(host)
    wm.wait_until(lambda: wm.host_hwnds() == [], 8000)
    time.sleep(0.8)
    restored_attr = corner_pref(target)
    restored_tool = wm.is_toolwindow(target)
    restored_btn = paint_button_seen()
    ok2 = restored_attr in (0, DEFAULT) and not restored_tool and restored_btn
    print(f"P2_RESTORED attr33={restored_attr} tool={restored_tool} button={restored_btn} "
          f"{'PASS' if ok2 else 'FAIL'}")
    wm.force_kill_by_name("mspaint")
    if backup is not None:
        Path(cp).write_text(backup, encoding="utf-8")
    elif os.path.exists(cp):
        os.remove(cp)
    return ok and ok2


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", choices=["1", "2", "all"], default="all")
    a = ap.parse_args()
    p1 = phase1() if a.phase in ("1", "all") else True
    p2 = phase2() if a.phase in ("2", "all") else True
    all_ok = p1 and p2
    print(f"{'PASS' if all_ok else 'FAIL'}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
