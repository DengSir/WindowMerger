# -*- coding: utf-8 -*-
"""WindowMerger 工具公共库：ctypes Win32 封装 + 截图 + 进程/配置辅助。

脚本导入方式（脚本位于 tools/<分类>/xxx.py，本文件在 tools/lib/）：
    import sys, pathlib
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "lib"))
    import wm

约定：
- 导入即 SetProcessDPIAware（原 PS 脚本每个 Add-Type 后第一件事）；
  管道/重定向输出下 stdout/stderr 重配 UTF-8（中文 Windows 默认 GBK 会编码报错）。
- 诊断输出标记与原 PS 脚本逐字一致（NO_HOST / LEFT_HIT=Notepad / ...）。
"""
from __future__ import annotations

import ctypes
import json
import os
import subprocess
import sys
import time
from ctypes import POINTER, Structure, byref, c_int, c_uint, c_void_p, sizeof
from ctypes import wintypes
from pathlib import Path

# 管道输出下中文 Windows 默认 GBK，重配 UTF-8 防编码错误（真控制台不受影响）
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
_dwmapi = ctypes.WinDLL("dwmapi", use_last_error=True)
_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_shell32 = ctypes.WinDLL("shell32", use_last_error=True)

# ---------- 常量 ----------

GWL_STYLE = -16
GWL_EXSTYLE = -20
WS_EX_TOPMOST = 0x8
WS_EX_TOOLWINDOW = 0x80
WS_EX_TRANSPARENT = 0x20

GW_HWNDNEXT = 2
GW_OWNER = 4

SW_MINIMIZE = 6
SW_SHOWNA = 8
SW_RESTORE = 9
SW_SHOWNOACTIVATE = 4

WM_CLOSE = 0x0010

HWND_TOPMOST = ctypes.c_void_p(-1)
HWND_NOTOPMOST = ctypes.c_void_p(-2)

SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010

DWMWA_EXTENDED_FRAME_BOUNDS = 9
DWMWA_CLOAKED = 14


def set_dpi_aware_pm2() -> None:
    """SetProcessDpiAwarenessContext(PER_MONITOR_AWARE_V2)：跨 DPI 测试脚本用。"""
    _user32.SetProcessDpiAwarenessContext(c_void_p(-4))


def get_dpi_for_window(h: int) -> int:
    return _user32.GetDpiForWindow(wintypes.HWND(h))


def keybd_event(vk: int, scan: int, flags: int) -> None:
    _user32.keybd_event(vk, scan, flags, c_void_p(0))


def cloaked_raw(h: int) -> int:
    """DWMWA_CLOAKED 原值（0=未 cloaked）。查询失败返回 0。"""
    v = c_int(0)
    if _dwmapi.DwmGetWindowAttribute(wintypes.HWND(h), DWMWA_CLOAKED,
                                     byref(v), sizeof(v)) == 0:
        return v.value
    return 0

SRCCOPY = 0x00CC0020
CAPTUREBLT = 0x40000000
PW_RENDERFULLCONTENT = 0x2  # WPF/分层窗口需要 DWM 渲染内容

MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


# ---------- 结构 ----------

class RECT(Structure):
    _fields_ = [("Left", wintypes.LONG), ("Top", wintypes.LONG),
                ("Right", wintypes.LONG), ("Bottom", wintypes.LONG)]

    @property
    def width(self) -> int:
        return self.Right - self.Left

    @property
    def height(self) -> int:
        return self.Bottom - self.Top

    def as_tuple(self) -> tuple[int, int, int, int]:
        return (self.Left, self.Top, self.Right, self.Bottom)


class POINT(Structure):
    _fields_ = [("X", wintypes.LONG), ("Y", wintypes.LONG)]


class BITMAPINFOHEADER(Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", c_int), ("biHeight", c_int),
                ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD),
                ("biCompression", wintypes.DWORD), ("biSizeImage", wintypes.DWORD),
                ("biXPelsPerMeter", c_int), ("biYPelsPerMeter", c_int),
                ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD)]


# 导入即 DPI aware（原 PS 脚本语义）
_user32.SetProcessDPIAware()


# ---------- 基础窗口查询 ----------

def is_window(h: int) -> bool:
    return bool(_user32.IsWindow(wintypes.HWND(h)))


def is_window_visible(h: int) -> bool:
    return bool(_user32.IsWindowVisible(wintypes.HWND(h)))


def is_iconic(h: int) -> bool:
    return bool(_user32.IsIconic(wintypes.HWND(h)))


def is_zoomed(h: int) -> bool:
    return bool(_user32.IsZoomed(wintypes.HWND(h)))


def is_cloaked(h: int) -> bool:
    """DWM cloaked（UWP 挂起等不可见态）。查询失败按未 cloaked。"""
    v = c_int(0)
    if _dwmapi.DwmGetWindowAttribute(wintypes.HWND(h), DWMWA_CLOAKED,
                                     byref(v), sizeof(v)) == 0:
        return v.value != 0
    return False


def get_window_rect(h: int) -> RECT | None:
    r = RECT()
    if _user32.GetWindowRect(wintypes.HWND(h), byref(r)):
        return r
    return None


def ext_frame_bounds(h: int) -> RECT | None:
    """DWMWA_EXTENDED_FRAME_BOUNDS：可见窗口矩形（不含隐形边）。"""
    r = RECT()
    if _dwmapi.DwmGetWindowAttribute(wintypes.HWND(h), DWMWA_EXTENDED_FRAME_BOUNDS,
                                     byref(r), sizeof(r)) == 0:
        return r
    return None


def get_window_long(h: int, index: int) -> int:
    return _user32.GetWindowLongW(wintypes.HWND(h), index)


def set_window_long(h: int, index: int, value: int) -> int:
    return _user32.SetWindowLongW(wintypes.HWND(h), index, value)


def get_ex_style(h: int) -> int:
    return get_window_long(h, GWL_EXSTYLE)


def is_toolwindow(h: int) -> bool:
    return (get_ex_style(h) & WS_EX_TOOLWINDOW) != 0


def is_topmost(h: int) -> bool:
    return (get_ex_style(h) & WS_EX_TOPMOST) != 0


def set_toolwindow(h: int, tool: bool) -> None:
    ex = get_ex_style(h)
    set_window_long(h, GWL_EXSTYLE, (ex | WS_EX_TOOLWINDOW) if tool else (ex & ~WS_EX_TOOLWINDOW))


def get_text(h: int, max_chars: int = 256) -> str:
    buf = ctypes.create_unicode_buffer(max_chars)
    _user32.GetWindowTextW(wintypes.HWND(h), buf, max_chars)
    return buf.value


def get_class_name(h: int, max_chars: int = 256) -> str:
    buf = ctypes.create_unicode_buffer(max_chars)
    _user32.GetClassNameW(wintypes.HWND(h), buf, max_chars)
    return buf.value


def pid_of(h: int) -> int:
    pid = wintypes.DWORD(0)
    _user32.GetWindowThreadProcessId(wintypes.HWND(h), byref(pid))
    return pid.value


def get_top_window() -> int:
    return _user32.GetTopWindow(None) or 0


def get_window(h: int, cmd: int) -> int:
    return _user32.GetWindow(wintypes.HWND(h), cmd) or 0


def z_walk(start: int | None = None):
    """z 序自顶向下产出 hwnd（可选从指定窗口起）。"""
    h = get_top_window() if start is None else start
    for _ in range(2048):
        if not h:
            return
        yield h
        h = get_window(h, GW_HWNDNEXT)


def window_from_point(x: int, y: int) -> int:
    return _user32.WindowFromPoint(POINT(x, y)) or 0


def get_cursor_pos() -> tuple[int, int] | None:
    p = POINT()
    if _user32.GetCursorPos(byref(p)):
        return (p.X, p.Y)
    return None


def get_foreground_window() -> int:
    return _user32.GetForegroundWindow() or 0


def set_foreground_window(h: int) -> None:
    _user32.SetForegroundWindow(wintypes.HWND(h))


def set_cursor_pos(x: int, y: int) -> None:
    _user32.SetCursorPos(x, y)


def mouse_event(flags: int) -> None:
    _user32.mouse_event(flags, 0, 0, 0, c_void_p(0))


def show_window(h: int, cmd: int) -> None:
    _user32.ShowWindow(wintypes.HWND(h), cmd)


def set_window_pos(h: int, insert_after: int | None, x: int, y: int, w: int, hh: int,
                   flags: int) -> bool:
    """insert_after=None → 不改 z 序（SWP_NOZORDER 由调用方 flags 控制）。"""
    after = wintypes.HWND(insert_after) if insert_after is not None else None
    return bool(_user32.SetWindowPos(wintypes.HWND(h), after, x, y, w, hh, flags))


def set_topmost(h: int, top: bool) -> None:
    after = HWND_TOPMOST if top else HWND_NOTOPMOST
    _user32.SetWindowPos(wintypes.HWND(h), after, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE)


def post_close(h: int) -> None:
    """PostMessage WM_CLOSE：走正常退出流程（保存配置/释放子窗口）。"""
    _user32.PostMessageW(wintypes.HWND(h), WM_CLOSE, c_void_p(0), c_void_p(0))


def find_window_by_title(title: str) -> int:
    return _user32.FindWindowW(None, title) or 0


# ---------- 进程 ----------

TH32CS_SNAPPROCESS = 0x2


class _PROCESSENTRY32W(Structure):
    _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
                ("th32ProcessID", wintypes.DWORD),
                ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", wintypes.DWORD),
                ("cntThreads", wintypes.DWORD), ("th32ParentProcessID", wintypes.DWORD),
                ("pcPriClassBase", ctypes.c_long), ("dwFlags", wintypes.DWORD),
                ("szExeFile", wintypes.WCHAR * 260)]


def _process_snapshot() -> list[tuple[int, str]]:
    """[(pid, exe名小写去.exe)]，一次快照（免句柄，提权进程也拿得到，与 PS Get-Process 同语义）。"""
    snap = _kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    out: list[tuple[int, str]] = []
    if snap in (0, -1):  # INVALID_HANDLE_VALUE
        return out
    try:
        e = _PROCESSENTRY32W()
        e.dwSize = sizeof(e)
        ok = _kernel32.Process32FirstW(snap, byref(e))
        while ok:
            out.append((e.th32ProcessID, e.szExeFile.lower().removesuffix(".exe")))
            ok = _kernel32.Process32NextW(snap, byref(e))
    finally:
        _kernel32.CloseHandle(wintypes.HANDLE(snap))
    return out


def _proc_name_of_pid(pid: int) -> str:
    """进程名（不带 .exe）。进程不存在返回 '?'（原 PS try/catch 语义）。"""
    for p, exe in _process_snapshot():
        if p == pid:
            return exe
    return "?"


def proc_name_of(h: int) -> str:
    return _proc_name_of_pid(pid_of(h))


def pids_by_name(name: str) -> list[int]:
    """按进程名（不区分大小写、可带 .exe）列出存活的 PID（Toolhelp 快照）。"""
    name = name.lower().removesuffix(".exe")
    return [p for p, exe in _process_snapshot() if exe == name]


def main_windows_of_pid(pid: int) -> list[int]:
    """该 PID 的可见顶层窗口（近似 .NET MainWindowHandle；吸附场景每进程就一个主窗）。"""
    out: list[int] = []
    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    @WNDENUMPROC
    def _cb(h, _lp):
        if pid_of(h) == pid and is_window_visible(h) and get_text(h):
            out.append(h)
        return True

    _user32.EnumWindows(_cb, 0)
    return out


def top_windows_of_pids(pids: list[int]) -> list[int]:
    """该组 PID 的可见无主顶层窗口（原 PS Find-TopWindowsOf：不要求有标题）。"""
    wanted = set(pids)
    out: list[int] = []
    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    @WNDENUMPROC
    def _cb(h, _lp):
        if pid_of(h) in wanted and is_window_visible(h) and get_window(h, GW_OWNER) == 0:
            out.append(h)
        return True

    _user32.EnumWindows(_cb, 0)
    return out


def all_windows_of_pid(pid: int) -> list[int]:
    """该 PID 的全部可见顶层窗口（**含 owned 对话框**——UIA root children 会漏掉
    ShowDialog 的 owned 窗口，实测；按标题找模态对话框必须走这里）。"""
    out: list[int] = []
    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    @WNDENUMPROC
    def _cb(h, _lp):
        if pid_of(h) == pid and is_window_visible(h):
            out.append(h)
        return True

    _user32.EnumWindows(_cb, 0)
    return out


def main_windows_by_name(*names: str) -> list[tuple[str, int]]:
    """Get-Process A,B | Where MainWindowHandle≠0 等价：[(进程名, hwnd)]。"""
    out: list[tuple[str, int]] = []
    for n in names:
        for pid in pids_by_name(n):
            for h in main_windows_of_pid(pid):
                out.append((n.lower().removesuffix(".exe"), h))
    return out


def host_hwnd() -> int:
    """WindowMerger 宿主主窗句柄；没有则 0（原 `Get-Process WindowMerger ...MainWindowHandle`）。"""
    for pid in pids_by_name("WindowMerger"):
        for h in main_windows_of_pid(pid):
            return h
    return 0


def host_hwnds() -> list[int]:
    out = []
    for pid in pids_by_name("WindowMerger"):
        out.extend(main_windows_of_pid(pid))
    return out


def graceful_close_by_name(name: str) -> None:
    """CloseMainWindow 等价：向该进程全部可见顶层窗口投递 WM_CLOSE。"""
    for pid in pids_by_name(name):
        for h in main_windows_of_pid(pid):
            post_close(h)


def force_kill_by_name(*names: str) -> None:
    """Stop-Process -Force 等价（taskkill /F）。"""
    for n in names:
        for pid in pids_by_name(n):
            subprocess.run(["taskkill", "/F", "/PID", str(pid)],
                           capture_output=True, check=False)


def force_kill_pid(pid: int) -> None:
    subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True, check=False)


def image_path_of_pid(pid: int) -> str | None:
    """QueryFullProcessImageNameW（Unicode，经典语义）；失败 None。"""
    h = _kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not h:
        return None
    try:
        buf = ctypes.create_unicode_buffer(1024)
        n = wintypes.DWORD(1024)
        if _kernel32.QueryFullProcessImageNameW(wintypes.HANDLE(h), 0, buf, byref(n)):
            return buf.value
        return None
    finally:
        _kernel32.CloseHandle(wintypes.HANDLE(h))


def parent_pid_of(pid: int) -> int:
    """父进程 PID；查不到返回 0（NtQueryInformationProcess(ProcessBasicInformation)）。"""
    class PBI(Structure):
        _fields_ = [("ExitStatus", ctypes.c_size_t), ("PebBaseAddress", ctypes.c_void_p),
                    ("AffinityMask", ctypes.c_size_t), ("BasePriority", ctypes.c_void_p),
                    ("UniqueProcessId", ctypes.c_size_t),
                    ("InheritedFromUniqueProcessId", ctypes.c_size_t)]

    h = _kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not h:
        return 0
    try:
        pbi = PBI()
        n = c_int(0)
        status = ctypes.WinDLL("ntdll").NtQueryInformationProcess(
            wintypes.HANDLE(h), 0, byref(pbi), sizeof(PBI), byref(n))
        return pbi.InheritedFromUniqueProcessId if status == 0 else 0
    finally:
        _kernel32.CloseHandle(wintypes.HANDLE(h))


def launched_by(pid: int, ancestor: int, depth: int = 3) -> bool:
    """pid 的祖先链（向上 depth 层）里是否含 ancestor——打包应用 stub→后代
    需要两层；StartTime 判据对 WindowsApps 预创建/挂起唤醒的进程不可靠（实测）。"""
    cur = pid
    for _ in range(depth):
        cur = parent_pid_of(cur)
        if cur == 0:
            return False
        if cur == ancestor:
            return True
    return False


def proc_start_time(pid: int):
    """进程启动时刻（本地时间）；打不开/失败 None。"""
    import datetime

    class FILETIME(Structure):
        _fields_ = [("dwLowDateTime", wintypes.DWORD), ("dwHighDateTime", wintypes.DWORD)]

    h = _kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not h:
        return None
    try:
        ft_create, ft_exit, ft_kernel, ft_user = FILETIME(), FILETIME(), FILETIME(), FILETIME()
        if not _kernel32.GetProcessTimes(wintypes.HANDLE(h), byref(ft_create), byref(ft_exit),
                                         byref(ft_kernel), byref(ft_user)):
            return None
        ts = (ft_create.dwHighDateTime << 32) | ft_create.dwLowDateTime
        utc = datetime.datetime(1601, 1, 1) + datetime.timedelta(microseconds=ts / 10)
        return utc.astimezone()
    finally:
        _kernel32.CloseHandle(wintypes.HANDLE(h))


SM_CXSCREEN = 0
SM_CYSCREEN = 1
SM_XVIRTUALSCREEN = 76
SM_YVIRTUALSCREEN = 77
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79
SM_CXICON = 49
SM_CYICON = 50


def virtual_screen_bounds() -> tuple[int, int, int, int]:
    """虚拟屏 (x, y, w, h)：全部显示器包围盒（物理像素）。"""
    return (_user32.GetSystemMetrics(SM_XVIRTUALSCREEN), _user32.GetSystemMetrics(SM_YVIRTUALSCREEN),
            _user32.GetSystemMetrics(SM_CXVIRTUALSCREEN), _user32.GetSystemMetrics(SM_CYVIRTUALSCREEN))


def get_system_metrics(index: int) -> int:
    return _user32.GetSystemMetrics(index)


class MONITORINFO(Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", RECT), ("rcWork", RECT),
                ("dwFlags", wintypes.DWORD)]


MONITOR_DEFAULTTOPRIMARY = 1


def primary_work_area() -> RECT:
    """主屏工作区（不含任务栏，物理像素）——MonitorFromPoint + GetMonitorInfo。
    （SystemParametersInfoW(SPI_GETWORKAREA) 在本机 Win11 实测失败，勿用）"""
    h = _user32.MonitorFromPoint(POINT(0, 0), MONITOR_DEFAULTTOPRIMARY)
    mi = MONITORINFO()
    mi.cbSize = sizeof(MONITORINFO)
    if not _user32.GetMonitorInfoW(h, byref(mi)):
        raise OSError("GetMonitorInfo failed")
    return mi.rcWork


def monitors() -> list[MONITORINFO]:
    """全部可见显示器信息（EnumDisplayMonitors，物理像素）。"""
    out: list[MONITORINFO] = []
    MONITORENUMPROC = ctypes.WINFUNCTYPE(
        wintypes.BOOL, wintypes.HMONITOR, wintypes.HDC, POINTER(RECT), wintypes.LPARAM)

    @MONITORENUMPROC
    def _cb(hmon, _hdc, _rc, _lp):
        mi = MONITORINFO()
        mi.cbSize = sizeof(MONITORINFO)
        if _user32.GetMonitorInfoW(hmon, byref(mi)):
            out.append(mi)
        return True

    _user32.EnumDisplayMonitors(None, None, _cb, 0)
    return out


def left_monitor_work_area() -> RECT:
    """最左（原点 x 最小）显示器的工作区——测试钉位基准（AGENTS：测试宿主一律停左侧
    100% 屏）。单屏即主屏工作区。"""
    ms = monitors()
    if not ms:
        raise OSError("no monitor")
    return min(ms, key=lambda mi: mi.rcMonitor.Left).rcWork


def test_layout() -> dict:
    """测试固定布局（按主屏工作区自适应，物理像素）：
    - 主屏宽 ≥2560（4K 开发机）：host (400,150,2200,900)，靶窗宿主正下方 (400,1090,1100,620)
    - 窄屏（CI RDP 实测只有 1024x720！）：host (20,380,960,320)，靶窗宿主上方 (20,40,500,300)
      （上方放靶窗才能满足"松手光标在宿主上方且在屏内"的构造；经典版 mspaint 最小宽
      远小于商店版，472px 格子装得下——CI 实测 514px 格 deviation=0）
    返回 {host, target, drop_center, covered_drop_center, cover_fx, cover_fw,
    divider_delta}；其余坐标由各测试按钉位后回读矩形推导，保证一套代码两种屏都能跑。"""
    wa = primary_work_area()
    if wa.Right - wa.Left >= 2560:
        return {"host": (400, 150, 2200, 900), "target": (400, 1090, 1100, 620),
                "drop_center": (1000, 560), "covered_drop_center": (2050, 830),
                "cover_fx": 0.55, "cover_fw": 0.40, "divider_delta": 200}
    # CI 拖 -120（分隔条左移→右格变宽）：472px 右格再压 200 会到 272px，可能触发
    # 经典 mspaint 最小宽钳制；向左压的是 notepad 格（经典版最小宽更小）且比例 0.37 仍 ≥0.2
    return {"host": (20, 380, 960, 320), "target": (20, 40, 500, 300),
            "drop_center": (256, 440), "covered_drop_center": (788, 620),
            "cover_fx": 0.65, "cover_fw": 0.30, "divider_delta": -120}


def park_on_left_or_primary(w: int, h: int) -> tuple[int, int]:
    """测试窗停放原点：有左侧副屏（开发机）停左侧 100% 屏，否则（CI 单屏）停主屏
    左上角——经典 notepad/mspaint 在单屏上停负坐标会整个出屏。"""
    wa = left_monitor_work_area()
    if wa.Left < 0:
        return (wa.Left + 100, wa.Top + 200)
    return (60, 60)


def wait_until(fn, timeout_ms: int, interval_ms: int = 100) -> bool:
    """轮询 fn() 直到真或超时（原 PS Start-Sleep 循环）。"""
    deadline = time.monotonic() + timeout_ms / 1000
    while time.monotonic() < deadline:
        if fn():
            return True
        time.sleep(interval_ms / 1000)
    return fn()


# ---------- 截图（Pillow） ----------

def capture_screen(x: int, y: int, w: int, h: int):
    """CopyFromScreen 等价：屏幕区域 → PIL Image（含分层窗口，Tooltip 弹层必须走这里）。"""
    from PIL import Image

    hdc_screen = _user32.GetDC(0)
    hdc_mem = _gdi32.CreateCompatibleDC(hdc_screen)
    bmp = _gdi32.CreateCompatibleBitmap(hdc_screen, w, h)
    _gdi32.SelectObject(hdc_mem, wintypes.HBITMAP(bmp))
    _gdi32.BitBlt(hdc_mem, 0, 0, w, h, hdc_screen, x, y, SRCCOPY | CAPTUREBLT)
    bi = BITMAPINFOHEADER()
    bi.biSize = sizeof(BITMAPINFOHEADER)
    bi.biWidth = w
    bi.biHeight = -h
    bi.biPlanes = 1
    bi.biBitCount = 32
    buf = ctypes.create_string_buffer(w * h * 4)
    ok = _gdi32.GetDIBits(hdc_mem, wintypes.HBITMAP(bmp), 0, h, buf, byref(bi), 0)
    img = Image.frombuffer("RGB", (w, h), buf.raw, "raw", "BGRX", 0, 1) if ok else None
    _gdi32.DeleteObject(wintypes.HBITMAP(bmp))
    _gdi32.DeleteDC(hdc_mem)
    _user32.ReleaseDC(0, hdc_screen)
    if img is None:
        raise OSError("屏幕截图失败（锁屏会话会报句柄无效，见 AGENTS.md）")
    return img


def capture_window(h: int):
    """PrintWindow(PW_RENDERFULLCONTENT)：窗口自身渲染，z 序免疫（被遮挡也能截）。"""
    from PIL import Image

    r = get_window_rect(h)
    if r is None:
        raise OSError("GetWindowRect failed")
    w, hh = r.width, r.height
    hdc_window = _user32.GetWindowDC(wintypes.HWND(h))
    hdc_mem = _gdi32.CreateCompatibleDC(hdc_window)
    bmp = _gdi32.CreateCompatibleBitmap(hdc_window, w, hh)
    _gdi32.SelectObject(hdc_mem, wintypes.HBITMAP(bmp))
    _user32.PrintWindow(wintypes.HWND(h), hdc_mem, PW_RENDERFULLCONTENT)
    bi = BITMAPINFOHEADER()
    bi.biSize = sizeof(BITMAPINFOHEADER)
    bi.biWidth = w
    bi.biHeight = -hh
    bi.biPlanes = 1
    bi.biBitCount = 32
    buf = ctypes.create_string_buffer(w * hh * 4)
    ok = _gdi32.GetDIBits(hdc_mem, wintypes.HBITMAP(bmp), 0, hh, buf, byref(bi), 0)
    img = Image.frombuffer("RGB", (w, hh), buf.raw, "raw", "BGRX", 0, 1) if ok else None
    _gdi32.DeleteObject(wintypes.HBITMAP(bmp))
    _gdi32.DeleteDC(hdc_mem)
    _user32.ReleaseDC(wintypes.HWND(h), hdc_window)
    if img is None:
        raise OSError("PrintWindow 失败")
    return img


# ---------- 配置（%APPDATA%\WindowMerger\config.json） ----------

def config_path() -> str:
    return os.path.join(os.environ["APPDATA"], "WindowMerger", "config.json")


# 主题调色板（与 src/Theme.cs 同步；像素断言期望值来源）
PALETTES = {
    "Dark": {"Bar": (32, 32, 32), "Border": (58, 58, 58), "Divider": (60, 60, 60),
             "DividerHover": (43, 91, 143), "Text": (216, 216, 216),
             "ButtonHover": (60, 60, 60), "DangerHover": (196, 43, 28)},
    "Light": {"Bar": (243, 243, 243), "Border": (192, 192, 192), "Divider": (192, 192, 192),
              "DividerHover": (169, 199, 232), "Text": (31, 31, 31),
              "ButtonHover": (220, 220, 220), "DangerHover": (209, 52, 56)},
}


def color_close(actual: tuple[int, int, int], expected: tuple[int, int, int], tol: int = 12) -> bool:
    return all(abs(a - e) <= tol for a, e in zip(actual[:3], expected))


def load_config() -> dict:
    with open(config_path(), encoding="utf-8") as f:
        return json.load(f)


def save_config(cfg: dict) -> None:
    os.makedirs(os.path.dirname(config_path()), exist_ok=True)
    with open(config_path(), "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)


def exe_path() -> str:
    """被测 exe 路径 = 本仓库 bin 产物（tools/lib → 仓库根/bin），避免旧机器硬编码路径。"""
    root = Path(__file__).resolve().parents[2]
    return str(root / "bin" / "Release" / "net10.0-windows" / "WindowMerger.exe")


def desktop_dir() -> str:
    """真实桌面目录（SHGetKnownFolderPath，重定向桌面/OneDrive 也正确）。
    陷阱：第一参数是 KNOWNFOLDERID 结构体指针，传字符串地址会拿到未重定向的默认值
    （实测本机桌面重定向到 D:\\Users 时返回 C:\\Users）。"""
    class GUID(Structure):
        _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD),
                    ("Data3", wintypes.WORD), ("Data4", ctypes.c_ubyte * 8)]

    fid = GUID(0xB4BFCC3A, 0xDB2C, 0x424C,
               (ctypes.c_ubyte * 8)(0xB0, 0x29, 0x7F, 0xE9, 0x9A, 0x87, 0xC6, 0x41))
    buf = ctypes.c_wchar_p()
    if _shell32.SHGetKnownFolderPath(ctypes.byref(fid), 0, None, ctypes.byref(buf)) != 0:
        return os.path.join(os.environ["USERPROFILE"], "Desktop")
    return buf.value


def remove_config() -> None:
    Path(config_path()).unlink(missing_ok=True)
