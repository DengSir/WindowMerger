# -*- coding: utf-8 -*-
"""子窗口激活联动 + z 序自愈收敛回归（2026-11 中线闪烁修复系列）。

覆盖三个行为点：
  A. 子窗口成为前台 → 宿主 topmost-toggle 升顶越过遮挡窗（焦点保持在子窗口）
  B. 自愈收敛：激活后 z 序在 ≤0.6s 内稳定，之后零写入（永动互搏回归探针）
  C. FixZOrder 跳过隐藏窗口：隐藏杂窗插进宿主正下方槽位不触发纠正（不可见
     插队者被移除），可见后立即纠正
用法: uv run tools/tests/child_fg_raise_test.py [--exe 路径]
警告: 会先优雅关闭再强杀所有 WindowMerger/Notepad/mspaint（含用户开着的实例，
      优雅关闭保证已吸附子窗口正常回原位摘样式）。
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

VK_MENU = 0x12
TARGET_TITLE = "WM_DRAG_TARGET"


def z_index_above(target: int, cap: int = 400) -> int | None:
    """target 在 z 序（自顶向下）中的序号；不在前 cap 个则 None。
    顶栏隐窗带（IME/Cicero 等）实测就有几十层，cap 太小会误判 None。"""
    for i, h in enumerate(wm.z_walk()):
        if i >= cap:
            return None
        if h == target:
            return i
    return None


def visible_slots_below(host: int, n: int = 2) -> list[int]:
    """宿主正下方前 n 个可见（非 cloaked）窗口——与 FixZOrder 同一判定口径。"""
    out, h, hops = [], host, 0
    while len(out) < n and hops < 32:
        h = wm.get_window(h, 2)  # GW_HWNDNEXT
        if not h:
            break
        hops += 1
        if wm.is_window_visible(h) and not wm.is_cloaked(h):
            out.append(h)
    return out


def full_below(host: int, count: int = 5) -> list[int]:
    """宿主正下方前 count 个原始槽位（含隐藏）。"""
    out, h = [], host
    for _ in range(count):
        h = wm.get_window(h, 2)
        if not h:
            break
        out.append(h)
    return out


def make_hidden_window() -> tuple[int, object, object]:
    """创建一个隐藏顶层窗口（无 WS_VISIBLE，占 z 序、不可见不可命中）。
    返回 (hwnd, WNDCLASSW 实例, user32)——卸载时 DestroyWindow + UnregisterClassW 用。"""
    WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, wintypes.HWND, wintypes.UINT,
                                 wintypes.WPARAM, wintypes.LPARAM)

    class WNDCLASSW(ctypes.Structure):
        _fields_ = [("style", ctypes.c_uint), ("lpfnWndProc", WNDPROC),
                    ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int),
                    ("hInstance", wintypes.HINSTANCE), ("hIcon", wintypes.HICON),
                    ("hCursor", ctypes.c_void_p), ("hbrBackground", wintypes.HBRUSH),
                    ("lpszMenuName", wintypes.LPCWSTR), ("lpszClassName", wintypes.LPCWSTR)]

    user32 = ctypes.windll.user32
    # DefWindowProcW / CreateWindowExW / UnregisterClassW 必须声明全参数类型——默认 int
    # 转换遇 64 位 WPARAM/LPARAM 高位会 OverflowError，wndproc 回调每次消息都炸（实测窗口
    # 行为异常、探针测试全歪）；hInstance 是模块基址，Win11 高熵 ASLR 下可 >2^31，不声明
    # 类型在 CreateWindowExW/UnregisterClassW 两处直接溢出（CI 实测 argument 11，看脸翻车）
    user32.DefWindowProcW.restype = ctypes.c_ssize_t
    user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT,
                                      wintypes.WPARAM, wintypes.LPARAM]
    user32.CreateWindowExW.restype = wintypes.HWND
    user32.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR,
                                       wintypes.DWORD, ctypes.c_int, ctypes.c_int,
                                       ctypes.c_int, ctypes.c_int, wintypes.HWND,
                                       wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID]
    user32.DestroyWindow.restype = wintypes.BOOL
    user32.DestroyWindow.argtypes = [wintypes.HWND]
    user32.UnregisterClassW.restype = wintypes.BOOL
    user32.UnregisterClassW.argtypes = [wintypes.LPCWSTR, wintypes.HINSTANCE]
    # GetModuleHandleW 不声明 restype 默认按 c_int 截断成 32 位——高位置 1 时变负数、
    # 存进 HINSTANCE 再读回是巨型正数，正是 CreateWindowExW 溢出的总根源
    ctypes.windll.kernel32.GetModuleHandleW.restype = wintypes.HMODULE
    ctypes.windll.kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
    proc = WNDPROC(user32.DefWindowProcW)
    wc = WNDCLASSW()
    wc.lpfnWndProc = proc
    wc.hInstance = ctypes.windll.kernel32.GetModuleHandleW(None)
    wc.lpszClassName = "WMZ_HiddenProbe"
    if not user32.RegisterClassW(ctypes.byref(wc)):
        raise OSError("RegisterClassW failed")
    # 0x0000 = WS_OVERLAPPED，无 WS_VISIBLE → 隐藏；放屏外避免可见化前闪现
    h = user32.CreateWindowExW(0, "WMZ_HiddenProbe", "WMZ_HiddenProbe", 0x00000000,
                               -500, -500, 10, 10, None, None, wc.hInstance, None)
    if not h:
        raise OSError("CreateWindowExW failed")
    return h, wc, user32


def activate_by_click(h: int) -> None:
    """穿透点击子窗口可见区中心激活（真实用户路径；ALT+SetForegroundWindow
    属强制接管，实测不产生 EVENT_SYSTEM_FOREGROUND，联动钩子收不到）。"""
    r = wm.get_window_rect(h)
    cx, cy = (r.Left + r.Right) // 2, (r.Top + r.Bottom) // 2
    wm.set_cursor_pos(cx, cy)
    time.sleep(0.15)
    wm.mouse_event(2)   # LEFTDOWN
    time.sleep(0.05)
    wm.mouse_event(4)   # LEFTUP
    time.sleep(0.15)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", default=wm.exe_path())
    a = ap.parse_args()
    failures: list[str] = []

    # 1. 清理：先优雅关宿主（吸附子窗口正常回原位摘样式），再强杀残留测试窗
    wm.graceful_close_by_name("WindowMerger")
    time.sleep(1.0)
    wm.force_kill_by_name("WindowMerger", "Notepad", "mspaint")
    t = wm.find_window_by_title(TARGET_TITLE)
    if t:
        wm.post_close(t)
        time.sleep(0.5)
    time.sleep(0.8)

    # 2. 测试窗口（目标必须先于宿主存在）
    t1 = Path(tempfile.gettempdir(), "wmfgr1.txt")
    t1.write_text("child-fg-raise-1", encoding="ascii")
    subprocess.Popen(["notepad", str(t1)])
    subprocess.Popen(["mspaint"])
    if not wm.wait_main_windows("Notepad", "mspaint"):
        print("FAIL_TARGETS_NOT_RUNNING")
        return 1

    # 3. 宿主 CLI 吸附（左=notepad 右=mspaint），等吸附落盘
    subprocess.Popen([a.exe, "--left", "notepad", "--right", "mspaint"])
    host = 0
    for _ in range(40):
        time.sleep(0.25)
        host = wm.host_hwnd()
        cfg = wm.load_config()
        if host and len(cfg.get("AttachedHwnds", [])) == 2:
            break
    if not host or len(wm.load_config().get("AttachedHwnds", [])) != 2:
        print("FAIL attach-timeout")
        return 1
    left, right = wm.load_config()["AttachedHwnds"]  # 吸附顺序 = 左、右

    # 3.5 圈地：test_layout 固定布局（1024x768 预算内，锚定 96 DPI 优先显示器）。
    # 跨 DPI 挪动必须两步走：先移动收敛 DPI 再设尺寸，一步到位会被 WPF 改写
    # （实测 2200x900 落成 3300x1350）
    hx, hy, hw, hh = wm.test_layout()["host"]
    wm.set_window_pos(host, None, hx, hy, 0, 0, wm.SWP_NOSIZE | wm.SWP_NOZORDER)
    time.sleep(0.4)
    wm.set_window_pos(host, None, 0, 0, hw, hh, wm.SWP_NOMOVE | wm.SWP_NOZORDER)
    time.sleep(1.0)
    hr = wm.get_window_rect(host)
    print(f"HOST {host:X} L={left:X} R={right:X} rect=({hr.Left},{hr.Top},{hr.Right},{hr.Bottom})")

    def click_zone_clear(child: int) -> bool:
        """穿透点击必须直达子窗口：中心点 WindowFromPoint 的 GA_ROOT 顶层窗口应等于
        子窗口 hwnd。不能直接比对——Win11 notepad/mspaint 是多 HWND 应用，命中
        的往往是内部编辑区子控件（实测 RichEditD2DPT）。"""
        r = wm.get_window_rect(child)
        hit = wm.window_from_point((r.Left + r.Right) // 2,
                                   (r.Top + r.Bottom) // 2)
        root = ctypes.windll.user32.GetAncestor(hit, 2)  # GA_ROOT
        return root == child

    def prepare_unit() -> bool:
        """预升单元到桌面杂物之上 + 确认点击区净空；不净空则重升重验（最多 3 轮）。"""
        for i in range(3):
            wm.keybd_event(VK_MENU, 0, 0)
            wm.set_foreground_window(host)
            time.sleep(0.15)
            wm.keybd_event(VK_MENU, 0, 2)
            time.sleep(0.7)
            if click_zone_clear(left) and click_zone_clear(right):
                return True
            print(f"PREPARE{i} click zone covered, retrying")
        return False

    if not prepare_unit():
        print("SKIP_CLICK_ZONE_COVERED")
        wm.graceful_close_by_name("WindowMerger")
        return 0

    # 4. 遮挡窗：拖动靶窗压住宿主顶条区域并置前
    subprocess.Popen([sys.executable, str(Path(__file__).resolve().parents[1]
                                          / "targets" / "drag_target.py")])
    target = 0
    for _ in range(20):
        time.sleep(0.25)
        target = wm.find_window_by_title(TARGET_TITLE)
        if target:
            break
    if not target:
        print("FAIL no-drag-target")
        return 1
    # 靶窗只压顶条（上缘探出屏），不遮格子——TEST A/B 的穿透点击必须直达子窗口
    wm.set_window_pos(target, None, hr.Left + 200, hr.Top - 100, 400, 150, 0x0040)  # SWP_SHOWWINDOW
    time.sleep(0.5)
    zi_host, zi_tgt = z_index_above(host), z_index_above(target)
    print(f"STEP0 z_host={zi_host} z_target={zi_tgt} (target 应在宿主上方)")
    if None in (zi_host, zi_tgt) or zi_tgt > zi_host:
        failures.append("A0: 遮挡窗未覆盖宿主")

    # 5. TEST A：子窗口激活 → 宿主升顶越过遮挡窗 + 焦点保持。
    # 本测试依赖 EVENT_SYSTEM_FOREGROUND：ALT+SetForegroundWindow 强制改前台
    # 不产生该事件、注入点击可能被前台抢占类程序瞬间抢回——两类情况都无法
    # 合成验证，按环境限制 SKIP。
    activate_by_click(left)
    fg_early = None
    t0 = time.monotonic()
    while time.monotonic() - t0 < 0.6:
        if wm.get_foreground_window() == left:
            fg_early = time.monotonic() - t0
            break
        time.sleep(0.05)
    if fg_early is None and click_zone_clear(left):
        fg = wm.get_foreground_window()
        print(f"SKIP_FOREGROUND_HIJACK fg={fg:X}({wm.proc_name_of(fg)}) "
              "点击区净空但前台被抢占类程序持有，无法合成验证")
        wm.graceful_close_by_name("WindowMerger")
        t = wm.find_window_by_title(TARGET_TITLE)
        if t:
            wm.post_close(t)
        return 0
    time.sleep(0.6)
    zi_host, zi_tgt = z_index_above(host), z_index_above(target)
    slots = visible_slots_below(host)
    print(f"STEP_A fg_early={fg_early} z_host={zi_host} z_target={zi_tgt} "
          f"slots={[f'{h:X}' for h in slots]}")
    if fg_early is None:
        failures.append("A1: 点击后 0.6s 内焦点未落到子窗口")
    if None in (zi_host, zi_tgt) or zi_host > zi_tgt:
        failures.append("A2: 宿主未越过遮挡窗升顶")
    if set(slots) != {left, right}:
        failures.append(f"A3: 子窗口未粘回宿主正下方 slots={[f'{h:X}' for h in slots]}")

    # 6. TEST B：自愈收敛——再激活一次后采样 2s，0.6s 后可见槽位必须零变动
    # （永动探针；采可见口径，隐藏杂窗自身抖动不参与）
    activate_by_click(right)
    time.sleep(1.0)
    samples, last, churn_after_settle = [], None, 0
    t0 = time.monotonic()
    while time.monotonic() - t0 < 2.0:
        cur = tuple(f"{h:X}" for h in visible_slots_below(host, 3))
        if cur != last:
            if samples and time.monotonic() - t0 > 0.6:
                churn_after_settle += 1
            samples.append((round(time.monotonic() - t0, 2), cur))
            last = cur
        time.sleep(0.05)
    print(f"STEP_B churn_after_0.6s={churn_after_settle} transitions={len(samples)}")
    if churn_after_settle:
        failures.append(f"B1: 0.6s 后仍有 {churn_after_settle} 次 z 变动（永动互搏回归）")

    # 7. TEST C：隐藏杂窗插进宿主正下方 → 不触发纠正；可见化 → 立即纠正
    probe, wc_cls, user32 = make_hidden_window()
    try:
        wm.set_window_pos(probe, host, 0, 0, 0, 0,
                          wm.SWP_NOMOVE | wm.SWP_NOSIZE | wm.SWP_NOACTIVATE)
        time.sleep(1.2)  # ≥4 个维护 tick；旧逻辑会在 250ms 内把它挤走
        # 豁免口径：探针须仍在宿主下方 8 槽内（隐藏杂窗可插在其前），
        # 且子窗口可见槽位纹丝不动（隐藏插队者不触发翻转）
        below_raw = full_below(host, 8)
        dist = below_raw.index(probe) + 1 if probe in below_raw else -1
        print(f"STEP_C1 probe_dist={dist} raw={[f'{h:X}' for h in below_raw]}")
        if not 1 <= dist <= 8:
            failures.append("C1: 隐藏插队者被驱赶（应被豁免，仍在宿主下方 8 槽内）")
        if set(visible_slots_below(host)) != {left, right}:
            failures.append("C2: 隐藏插队引发子窗口翻转")
        # 可见化 → 可见插队者 → 必须纠正（子窗口回到它与宿主之间）
        wm.show_window(probe, wm.SW_SHOWNA)
        time.sleep(1.2)
        # 遍历宿主下方：子窗口必须全部位于 probe 之前（更靠近宿主）
        order, h, hops = [], host, 0
        while h and hops < 60:
            h = wm.get_window(h, 2)
            if not h:
                break
            hops += 1
            order.append(h)
            if h == probe:
                break
        pos_left = order.index(left) if left in order else 99
        pos_right = order.index(right) if right in order else 99
        pos_probe = order.index(probe) if probe in order else -1
        print(f"STEP_C2 probe@{pos_probe} left@{pos_left} right@{pos_right} "
              f"(子窗口应都 < probe)")
        if not (pos_left < pos_probe and pos_right < pos_probe):
            failures.append("C3: 可见插队者未被纠正")
    finally:
        user32.DestroyWindow(probe)
        ctypes.windll.user32.UnregisterClassW("WMZ_HiddenProbe", wc_cls.hInstance)

    # 8. 收尾：优雅关宿主（还原子窗口样式/几何），清测试窗
    wm.graceful_close_by_name("WindowMerger")
    t = wm.find_window_by_title(TARGET_TITLE)
    if t:
        wm.post_close(t)
    time.sleep(1.0)
    wm.force_kill_by_name("Notepad", "mspaint")

    print(f"FAILURES {'; '.join(failures) if failures else 'NONE'}")
    print(f"RESULT {'FAIL' if failures else 'PASS'}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
