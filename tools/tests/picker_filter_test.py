# -*- coding: utf-8 -*-
"""选择器过滤与确认回归（PickerWindow / WindowLocator 黑盒）：
  K1 负向过滤：WS_EX_TOOLWINDOW 窗、有 owner 的窗不进候选；排除类名
     （Shell_TrayWnd/Progman 等）不出现；正向：notepad/mspaint 在列表里
  K2 过滤框大小写不敏感 + 按进程名/标题过滤：输入 "MSPAINT" 只剩画图行；
     输入不存在串 → 空列表
  K3 未选中点"吸附" → 无操作（picker 不关闭、不吸附）
  K4 双击行 = 确认吸附（MouseDoubleClick → Confirm）
用法: uv run tools\\tests\\picker_filter_test.py [--exe 路径]
警告: 强杀所有 WindowMerger/Notepad/mspaint；探针窗口用完即毁。
"""
import argparse
import ctypes
import subprocess
import sys
import tempfile
import time
from ctypes import wintypes
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import wm
import wm_uia
import uiautomation as auto

GWL_STYLE, GWL_EXSTYLE = -16, -20
WS_VISIBLE = 0x10000000
WS_OVERLAPPEDWINDOW = 0x00CF0000
WS_EX_TOOLWINDOW = 0x80


def make_probe_windows() -> tuple[int, int, object, object]:
    """创建 (toolwindow, owned) 两个可见探针窗 + class 实例（销毁用）。"""
    WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, wintypes.HWND, wintypes.UINT,
                                 wintypes.WPARAM, wintypes.LPARAM)

    class WNDCLASSW(ctypes.Structure):
        _fields_ = [("style", ctypes.c_uint), ("lpfnWndProc", WNDPROC),
                    ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int),
                    ("hInstance", wintypes.HINSTANCE), ("hIcon", wintypes.HICON),
                    ("hCursor", ctypes.c_void_p), ("hbrBackground", wintypes.HBRUSH),
                    ("lpszMenuName", wintypes.LPCWSTR), ("lpszClassName", wintypes.LPCWSTR)]

    user32 = ctypes.windll.user32
    user32.DefWindowProcW.restype = ctypes.c_ssize_t
    user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM,
                                      wintypes.LPARAM]
    user32.CreateWindowExW.restype = wintypes.HWND
    user32.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR,
                                       wintypes.DWORD, ctypes.c_int, ctypes.c_int,
                                       ctypes.c_int, ctypes.c_int, wintypes.HWND,
                                       wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID]
    user32.DestroyWindow.argtypes = [wintypes.HWND]
    user32.UnregisterClassW.argtypes = [wintypes.LPCWSTR, wintypes.HINSTANCE]
    ctypes.windll.kernel32.GetModuleHandleW.restype = wintypes.HMODULE
    ctypes.windll.kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
    proc = WNDPROC(user32.DefWindowProcW)
    wc = WNDCLASSW()
    wc.lpfnWndProc = proc
    wc.hInstance = ctypes.windll.kernel32.GetModuleHandleW(None)
    wc.lpszClassName = "WM_PickerProbe"
    if not user32.RegisterClassW(ctypes.byref(wc)):
        raise OSError("RegisterClassW failed")
    # 工具窗：可见 + 有标题 + WS_EX_TOOLWINDOW（候选过滤必须排除）
    tool = user32.CreateWindowExW(
        WS_EX_TOOLWINDOW, "WM_PickerProbe", "WM_PROBE_TOOLWINDOW",
        WS_OVERLAPPEDWINDOW | WS_VISIBLE, 60, 60, 300, 200, None, None, wc.hInstance, None)
    # owned：可见 + 有标题 + owner=工具窗（候选过滤必须排除）
    owned = user32.CreateWindowExW(
        0, "WM_PickerProbe", "WM_PROBE_OWNED",
        WS_OVERLAPPEDWINDOW | WS_VISIBLE, 380, 60, 300, 200, tool, None, wc.hInstance, None)
    if not tool or not owned:
        raise OSError("CreateWindowExW failed")
    return tool, owned, wc, user32


def find_picker(host: int) -> int:
    for h in wm.all_windows_of_pid(wm.pid_of(host)):
        if h != host and "选择吸附到" in wm.get_text(h):
            return h
    return 0


def picker_texts(picker: int) -> list[str]:
    pe = wm_uia.element_from_handle(picker)
    out = []
    for c, _ in auto.WalkControl(pe, includeTop=False, maxDepth=8):
        if c.ControlTypeName in ("ListItemControl", "DataItemControl", "TextControl") \
                and (c.Name or "").strip():
            out.append(c.Name)
    return out


def picker_list_items(picker: int) -> list:
    pe = wm_uia.element_from_handle(picker)
    return [c for c, _ in auto.WalkControl(pe, includeTop=False, maxDepth=8)
            if c.ControlTypeName in ("ListItemControl", "DataItemControl")]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", default=wm.exe_path())
    a = ap.parse_args()
    auto.SetGlobalSearchTimeout(5)
    failures: list[str] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        print(f"{name} {'OK' if ok else 'MISMATCH'} {detail}")
        if not ok:
            failures.append(name)

    wm.force_kill_by_name("WindowMerger", "Notepad", "mspaint")
    time.sleep(0.8)
    wm.remove_config()
    wm.save_config({"Ratio": 0.5})
    t1 = Path(tempfile.gettempdir(), "wmkf1.txt")
    t1.write_text("picker-filter", encoding="ascii")
    subprocess.Popen(["notepad", str(t1)])
    subprocess.Popen(["mspaint"])
    if not wm.wait_main_windows("Notepad", "mspaint"):
        print("FAIL_TARGETS_NOT_RUNNING")
        return 1

    tool = owned = 0
    wc = user32 = None
    try:
        tool, owned, wc, user32 = make_probe_windows()
        time.sleep(0.3)
        subprocess.Popen([a.exe], env=wm.host_env())
        time.sleep(4)
        hm = wm.host_hwnd()
        if not hm:
            print("NO_HOST")
            return 1
        wm.set_window_pos(hm, None, *wm.test_layout()["host"], wm.SWP_NOZORDER)
        time.sleep(1.0)
        wm.set_topmost(hm, True)
        time.sleep(0.3)

        # ---------- K1 负向/正向过滤 ----------
        wm_uia.invoke(wm_uia.find_by_automation_id(wm_uia.element_from_handle(hm),
                                                   "_pickLeftButton"))
        picker = 0
        if not wm.wait_until(lambda: find_picker(hm), 5000, 200):
            print("FAIL_NO_PICKER")
            return 1
        picker = find_picker(hm)
        texts = picker_texts(picker)
        joined = " | ".join(texts)
        check("K1_TOOLWINDOW_EXCLUDED", "WM_PROBE_TOOLWINDOW" not in joined)
        check("K1_OWNED_EXCLUDED", "WM_PROBE_OWNED" not in joined)
        check("K1_EXCLUDED_CLASSES_ABSENT",
              all(k not in joined for k in ("Shell_TrayWnd", "Progman", "WorkerW")))
        check("K1_POSITIVE_PRESENT", "mspaint" in joined.lower() and "notepad" in joined.lower(),
              f"rows={joined[:160]}...")

        # ---------- K2 过滤框大小写不敏感 ----------
        pe = wm_uia.element_from_handle(picker)
        edit = None
        for c, _ in auto.WalkControl(pe, includeTop=False, maxDepth=6):
            if c.ControlTypeName == "EditControl":
                edit = c
                break
        if edit is None or not wm_uia.set_value(edit, "MSPAINT"):
            check("K2_FILTER", False, "no edit / value set failed")
        else:
            time.sleep(0.5)
            rows = picker_list_items(picker)
            k2a = len(rows) >= 1 and all("画图" in (r.Name or "") or "mspaint" in (r.Name or "").lower()
                                         for r in rows)
            check("K2_CASE_INSENSITIVE", k2a, f"rows={[r.Name for r in rows]}")
            wm_uia.set_value(edit, "zz_no_such_zz")
            time.sleep(0.5)
            check("K2_NO_MATCH_EMPTY", len(picker_list_items(picker)) == 0)
            wm_uia.set_value(edit, "notepad")
            time.sleep(0.5)

        # ---------- K3 未选中点"吸附" → 无操作 ----------
        rows = picker_list_items(picker)
        wm_uia.invoke(wm_uia.find_by_name(pe, "吸附"))
        time.sleep(1.0)
        check("K3_NO_SELECT_NOOP", bool(wm.is_window(picker)) and not wm.is_attached(
            wm.main_windows_by_name("Notepad")[0][1]),
            f"picker_alive={bool(wm.is_window(picker))}")

        # ---------- K4 双击行 = 确认吸附 ----------
        rows = picker_list_items(picker)
        if not rows:
            check("K4_DOUBLE_CLICK", False, "no rows")
        else:
            r = rows[0].BoundingRectangle
            cx, cy = int((r.left + r.right) / 2), int((r.top + r.bottom) / 2)
            wm.set_cursor_pos(cx, cy)
            time.sleep(0.2)
            for _ in range(2):  # 双击
                wm.mouse_event(wm.MOUSEEVENTF_LEFTDOWN)
                time.sleep(0.05)
                wm.mouse_event(wm.MOUSEEVENTF_LEFTUP)
                time.sleep(0.08)
            time.sleep(1.5)
            nh = wm.main_windows_by_name("Notepad")[0][1]
            check("K4_DOUBLE_CLICK_CONFIRM",
                  not wm.is_window(picker) and wm.is_attached(nh),
                  f"picker_alive={bool(wm.is_window(picker))} np_tool={wm.is_attached(nh)}")

        wm.set_topmost(hm, False)
        wm.graceful_close_by_name("WindowMerger")
        time.sleep(1.2)
        wm.force_kill_by_name("Notepad", "mspaint")
    finally:
        if tool:
            user32.DestroyWindow(tool)
        if owned:
            user32.DestroyWindow(owned)
        if wc is not None:
            ctypes.windll.user32.UnregisterClassW("WM_PickerProbe", wc.hInstance)

    print(f"FAILURES {'; '.join(failures) if failures else 'NONE'}")
    print(f"RESULT {'FAIL' if failures else 'PASS'}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
