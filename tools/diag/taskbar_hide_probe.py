# -*- coding: utf-8 -*-
"""ITaskbarList::DeleteTab 替代 WS_EX_TOOLWINDOW 隐藏任务栏的可行性实测。

探针 = ctypes 造的普通洋红窗 WM_TAB_PROBE（不改任何样式），依次验证：
  1. 基线：任务栏按钮存在（Appid: 按钮，全多屏 Shell_TrayWnd 扫描）
  2. DeleteTab 后按钮消失？静置 2s 是否稳定？
  3. 激活（前台切换）后按钮是否复活？
  4. SW_HIDE→SW_SHOWNA 显隐切换后是否复活？（模拟现 SetToolWindowStyle 的重绘舞步）
  5. 最小化→还原后是否复活？
  6. Alt+Tab 切换器里还显不显示（截图目视，洋红缩略图辨识）——存 %TEMP%\\wm_corner\\alt_tab_probe.png
  7. AddTab 能否加回（反向操作可用性）

COM = 裸 vtable 调用（ITaskbarList：3=HrInit 4=AddTab 5=DeleteTab），不引依赖。
标记（英文）：BASELINE_BUTTON / DELETE_HR / GONE_AFTER_DELETE / STAYS_AFTER_IDLE /
BACK_AFTER_ACTIVATE / BACK_AFTER_SHOWTOGGLE / BACK_AFTER_MINRESTORE / ADDTAB_RESTORED / ALTTAB_SHOT
"""
import ctypes
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import wm  # noqa: E402
import wm_uia  # noqa: E402

OUT_DIR = Path(tempfile.gettempdir()) / "wm_corner"
PROBE_TITLE = "WM_TAB_PROBE"

_user32 = ctypes.windll.user32
_ole32 = ctypes.windll.ole32

CLSCTX_ALL = 23
CLSID_TASKBARLIST = "{56FDF344-FD6D-11d0-958A-006097C9A090}"
IID_ITASKBARLIST = "{56FDF342-FD6D-11d0-958A-006097C9A090}"


class GUID(ctypes.Structure):
    _fields_ = [("Data1", ctypes.c_ulong), ("Data2", ctypes.c_ushort),
                ("Data3", ctypes.c_ushort), ("Data4", ctypes.c_ubyte * 8)]


def guid(s: str) -> GUID:
    h = s.strip("{}").replace("-", "")
    g = GUID()
    g.Data1, g.Data2, g.Data3 = int(h[:8], 16), int(h[8:12], 16), int(h[12:16], 16)
    for i in range(8):
        g.Data4[i] = int(h[16 + i * 2:18 + i * 2], 16)
    return g


def itbl_call(punk, index: int, hwnd: int = 0) -> int:
    """ITaskbarList 裸 vtable：3=HrInit 4=AddTab 5=DeleteTab 6=ActivateTab 7=SetActiveAlt。"""
    vtbl = ctypes.cast(punk, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p)))[0]
    proto = ctypes.WINFUNCTYPE(ctypes.HRESULT, ctypes.c_void_p, ctypes.c_void_p)
    fn = ctypes.cast(vtbl[index], proto)
    return fn(punk, ctypes.c_void_p(hwnd))


def taskbar_hwnds() -> list[int]:
    """全部可见任务栏（Win11 主屏 Shell_TrayWnd + 副屏 Shell_SecondaryTrayWnd）。"""
    out = []
    for cls in ("Shell_TrayWnd", "Shell_SecondaryTrayWnd"):
        h = 0
        while True:
            h = _user32.FindWindowExW(None, h, cls, None)
            if not h:
                break
            if wm.is_window_visible(h):
                out.append(h)
    return out


def probe_button_names() -> list[str]:
    """按显式 AUMID 精确匹配探针按钮（Appid:WM.TabProbe）。

    教训：裸窗口的按钮名 = 进程 exe 的文件描述（如 "Python"），窗口标题不参与——
    按标题找按钮必然落空；与宿主 OnStartup 同款 SetCurrentProcessExplicitAppUserModelID
    让按钮 AutomationId = Appid:WM.TabProbe，唯一可判。"""
    names = []
    for h in taskbar_hwnds():
        el = wm_uia.element_from_handle(h)
        for b in wm_uia.find_all_buttons(el):
            aid = wm_uia.automation_id_of(b)
            if aid.startswith("Appid:") and "WM.TabProbe" in aid:  # 实测 "Appid: " 冒号后带空格
                names.append(wm_uia.name_of(b))
    return names


def activate(h: int) -> None:
    wm.keybd_event(0x12, 0x38, 0)  # ALT 一下解锁 SetForegroundWindow 的前台锁
    wm.keybd_event(0x12, 0x38, 2)
    wm.set_foreground_window(h)


def main() -> int:
    OUT_DIR.mkdir(exist_ok=True)
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
    brush = ctypes.windll.gdi32.CreateSolidBrush(0x00FF00FF)  # 洋红，Alt+Tab 缩略图好认

    def proc(h, msg, wp, lp):
        if msg == 0x000F:  # WM_PAINT
            ps = PAINTSTRUCT()
            hdc = _user32.BeginPaint(h, ctypes.byref(ps))
            _user32.FillRect(hdc, ctypes.byref(ps.rcPaint), wintypes.HBRUSH(brush))
            _user32.EndPaint(h, ctypes.byref(ps))
            return 0
        return _user32.DefWindowProcW(h, msg, wp, lp)

    hinst = ctypes.windll.kernel32.GetModuleHandleW(None)
    # 显式 AUMID 必须在窗口创建前设（宿主 OnStartup 同款）：按钮身份才可精确判
    hr_aumid = ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("WM.TabProbe")
    print(f"AUMID_HR={hr_aumid:#x}")
    wc = WNDCLASSEXW(ctypes.sizeof(WNDCLASSEXW), 0, WNDPROC(proc), 0, 0, hinst,
                     None, None, wintypes.HBRUSH(brush), None, "wm_tab_probe", None)
    if not _user32.RegisterClassExW(ctypes.byref(wc)):
        raise OSError("RegisterClassExW failed")
    x, y = wm.park_on_left_or_primary(300, 200)
    probe = _user32.CreateWindowExW(0, "wm_tab_probe", PROBE_TITLE,
                                    0x00CF0000 | 0x10000000,  # WS_OVERLAPPEDWINDOW | WS_VISIBLE
                                    x, y, 300, 200, None, None, hinst, None)
    if not probe:
        raise OSError("CreateWindowExW failed")
    time.sleep(0.5)  # shell 异步建按钮

    baseline = wm.wait_until(lambda: probe_button_names(), 4000)

    def dump_all_buttons() -> list[tuple[str, str]]:
        rows = []
        for h in taskbar_hwnds():
            el = wm_uia.element_from_handle(h)
            for b in wm_uia.find_all_buttons(el):
                rows.append((wm_uia.name_of(b), wm_uia.automation_id_of(b)))
        return rows

    print(f"BASELINE_BUTTON={baseline or probe_button_names()}")
    print(f"TASKBAR_BUTTONS={dump_all_buttons()}")
    for i, th in enumerate(taskbar_hwnds()):
        r = wm.get_window_rect(th)
        if r:
            strip = wm.capture_screen(r.Left, max(r.Top, r.Bottom - 60),
                                      r.width, min(60, r.height))
            strip.save(OUT_DIR / f"taskbar_{i}.png")
            print(f"  taskbar_{i}.png hwnd={th:#x} rect={r.Left},{r.Top},{r.width},{r.height}")

    hr_ci = _ole32.CoInitializeEx(None, 2)  # STA；uiautomation 已初始化时返回 CHANGED_MODE，无碍
    punk = ctypes.c_void_p()
    hr_cc = _ole32.CoCreateInstance(ctypes.byref(guid(CLSID_TASKBARLIST)), None,
                                    CLSCTX_ALL, ctypes.byref(guid(IID_ITASKBARLIST)),
                                    ctypes.byref(punk))
    if hr_cc != 0 or not punk.value:
        print(f"NO_TASKBARLIST hr_cc={hr_cc:#x}")
        _user32.DestroyWindow(probe)
        return 1
    print(f"COINIT hr={hr_ci:#x} HrInit hr={itbl_call(punk, 3, probe):#x}")

    hr_del = itbl_call(punk, 5, probe)  # DeleteTab
    time.sleep(0.5)
    gone = not probe_button_names()
    time.sleep(2.0)
    stays = not probe_button_names()
    print(f"DELETE_HR={hr_del:#x} GONE_AFTER_DELETE={gone} STAYS_AFTER_IDLE={stays}")

    activate(probe)
    time.sleep(0.5)
    print(f"BACK_AFTER_ACTIVATE={bool(probe_button_names())}")

    wm.show_window(probe, wm.SW_HIDE)
    time.sleep(0.2)
    wm.show_window(probe, wm.SW_SHOWNA)
    time.sleep(0.5)
    print(f"BACK_AFTER_SHOWTOGGLE={bool(probe_button_names())}")

    wm.show_window(probe, wm.SW_MINIMIZE)
    time.sleep(0.3)
    wm.show_window(probe, wm.SW_RESTORE)
    time.sleep(0.5)
    print(f"BACK_AFTER_MINRESTORE={bool(probe_button_names())}")

    # 再删一次测 Alt+Tab 与 AddTab（上面若复活了，此刻按钮在）
    itbl_call(punk, 5, probe)
    time.sleep(0.5)

    fg_saved = wm.get_foreground_window()
    activate(probe)
    time.sleep(0.3)
    wm.keybd_event(0x12, 0x38, 0)  # ALT down
    wm.keybd_event(0x09, 0x0F, 0)  # TAB down
    wm.keybd_event(0x09, 0x0F, 2)  # TAB up
    time.sleep(1.0)  # 切换器动画
    shot = wm.capture_test_screen()
    p = OUT_DIR / "alt_tab_probe.png"
    shot.save(p)
    wm.keybd_event(0x1B, 0x01, 0)  # ESC 取消切换
    wm.keybd_event(0x1B, 0x01, 2)
    wm.keybd_event(0x12, 0x38, 2)  # ALT up
    if fg_saved:
        wm.set_foreground_window(fg_saved)
    print(f"ALTTAB_SHOT={p}")

    hr_add = itbl_call(punk, 4, probe)  # AddTab 加回
    time.sleep(0.5)
    print(f"ADDTAB_RESTORED={bool(probe_button_names())} (hr={hr_add:#x})")

    _user32.DestroyWindow(probe)
    ctypes.windll.ole32.CoUninitialize()
    return 0


if __name__ == "__main__":
    sys.exit(main())
