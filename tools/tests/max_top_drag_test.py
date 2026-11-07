# -*- coding: utf-8 -*-
"""最大化顶条拖动还原回归（自动化——注入拖动）：
宿主停左侧屏（无则主屏）→ PostMessage SC_MAXIMIZE 最大化 → 两组断言：
  A. 最大化整窗 WM_NCHITTEST 全 HTCLIENT：WindowChrome 的 resize 边命中测试不看
     最大化状态（WPF 源码 _HitTestNca 无该检查），最大化时窗口顶边=屏幕顶边，顶条
     最上 8 DIP 被判 HTTOP 缩放区——鼠标按在屏幕顶上拖不动（实测）。修复 = 宿主
     WndProc 最大化时整窗回 HTCLIENT（最大化本就不可缩放，Windows 标准行为）。
  B. 从屏幕顶边 dy=2（旧版死区）注入下拖 → 必须还原并跟随光标（is_zoomed=False、
     顶边下移≈拖距、宽度不变）。
正常态探针只打印不断言：dy<8DIP 必须仍是 HTTOP（修复不得动正常态缩放边）。
用法: uv run tools/tests/max_top_drag_test.py [--exe 路径]
警告: 强杀所有 WindowMerger + 删 config.json。
"""
import argparse
import subprocess
import sys
import time
from ctypes import windll, byref
from ctypes import wintypes
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import wm

WM_NCHITTEST = 0x0084
HTCLIENT, HTTOP, HTLEFT, HTBOTTOM = 1, 12, 10, 20
SMTO_ABORTIFHUNG = 0x0002
_user32 = windll.user32


def hit_test(h: int, x: int, y: int) -> int | None:
    """直接问窗口本身某屏幕坐标的命中结果（同 wm.title_grab_point 的探测方式）。"""
    lp = ((y & 0xFFFF) << 16) | (x & 0xFFFF)
    result = wintypes.LPARAM()
    if _user32.SendMessageTimeoutW(wintypes.HWND(h), WM_NCHITTEST, None,
                                   wintypes.LPARAM(lp), SMTO_ABORTIFHUNG, 1000,
                                   byref(result)):
        return result.value
    return None


def drag(from_x: int, from_y: int, to_x: int, to_y: int, steps: int = 20) -> None:
    wm.set_cursor_pos(from_x, from_y)
    time.sleep(0.15)
    wm.mouse_event(wm.MOUSEEVENTF_LEFTDOWN)
    time.sleep(0.15)
    for i in range(1, steps + 1):
        wm.set_cursor_pos(from_x + (to_x - from_x) * i // steps,
                          from_y + (to_y - from_y) * i // steps)
        time.sleep(0.025)
    time.sleep(0.2)
    wm.mouse_event(wm.MOUSEEVENTF_LEFTUP)
    time.sleep(1.0)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", default=wm.exe_path())
    a = ap.parse_args()

    wm.force_kill_by_name("WindowMerger")
    time.sleep(0.8)
    wm.remove_config()
    subprocess.Popen([a.exe])
    time.sleep(4)
    hm = wm.host_hwnd()
    if not hm:
        print("NO_HOST")
        return 1

    wa = wm.left_monitor_work_area()
    scale = wm.get_dpi_for_window(hm) / 96.0
    border = round(8 * scale)  # WindowChrome ResizeBorderThickness=8 DIP → 物理 px
    park_y = 200 if wa.Left < 0 else 60
    drag_px = 220
    # 还原后窗口必须完整落在屏内（CI 720 高也要装得下拖动全程）
    h = max(340, min(600, (wa.Bottom - wa.Top) - park_y - drag_px - 10))
    drag_px = max(120, min(drag_px, (wa.Bottom - wa.Top) - park_y - h - 10))
    w = 900
    x = wa.Left + 100 if wa.Left < 0 else 60
    # 两步钉位（AGENTS 已知坑：WPF 跨 DPI 保 DIP 不保物理，移动+尺寸一步到位会被
    # WM_DPICHANGED 自缩放改写）——先移动收敛 DPI，再设尺寸
    wm.set_window_pos(hm, None, x, park_y, 0, 0, wm.SWP_NOZORDER | wm.SWP_NOSIZE)
    time.sleep(0.6)
    wm.set_window_pos(hm, None, 0, 0, w, h, wm.SWP_NOZORDER | wm.SWP_NOMOVE)
    time.sleep(1.0)
    hr = wm.get_window_rect(hm)
    cx = hr.Left + hr.width // 2
    print(f"HOST normal ({hr.Left},{hr.Top})-({hr.Right},{hr.Bottom}) "
          f"scale={scale} border~{border}px")

    # 正常态探针（信息性）：顶边缩放区必须原样保留
    dys = list(range(0, border + 8, 2))
    normal = {dy: hit_test(hm, cx, hr.Top + dy) for dy in dys}
    print(f"NORMAL probe dy:{dys} -> {[normal[d] for d in dys]} "
          f"(dy<{border} 应为 HTTOP={HTTOP}，修复不得动正常态)")

    # 最大化（同 maximize_drag_test 的已验证路径）
    wm.show_window(hm, 3)  # SW_MAXIMIZE
    time.sleep(1.0)
    if not wm.is_zoomed(hm):
        print("NO_MAXIMIZE")
        wm.graceful_close_by_name("WindowMerger")
        return 1
    time.sleep(0.8)  # 最大化布局收敛
    mr = wm.get_window_rect(hm)
    print(f"HOST maximized ({mr.Left},{mr.Top})-({mr.Right},{mr.Bottom})")

    # A. 最大化整窗探针：顶边逐行（屏幕顶边）+ 左/右/底边，修复后必须全 HTCLIENT
    maxp = {dy: hit_test(hm, cx, mr.Top + dy) for dy in dys}
    edge_l = hit_test(hm, mr.Left + 2, mr.Top + mr.height // 2)
    edge_r = hit_test(hm, mr.Right - 3, mr.Top + mr.height // 2)
    edge_b = hit_test(hm, cx, mr.Bottom - 3)
    print(f"MAX probe dy:{dys} -> {[maxp[d] for d in dys]}  "
          f"edges L/R/B = {edge_l}/{edge_r}/{edge_b}  (修复后应全 HTCLIENT={HTCLIENT})")
    probe_ok = (all(maxp[d] == HTCLIENT for d in dys)
                and edge_l == HTCLIENT and edge_r == HTCLIENT and edge_b == HTCLIENT)

    # B. 屏幕顶边死区注入下拖 → 必须还原并跟随（还原锚点≈光标占比 → 顶边下移≈拖距）
    drag(cx, mr.Top + 2, cx, mr.Top + 2 + drag_px)
    r2 = wm.get_window_rect(hm)
    moved = r2.Top - mr.Top
    size_ok = abs(r2.width - w) <= 8
    drag_ok = (not wm.is_zoomed(hm)) and (drag_px - 60 <= moved <= drag_px + 60) and size_ok
    print(f"DRAG top+2 down {drag_px}px: zoomed={wm.is_zoomed(hm)} topMoved={moved} "
          f"rect=({r2.Left},{r2.Top})-({r2.Right},{r2.Bottom}) "
          f"width={r2.width}(期望≈{w})")

    # 还原后正常态探针（信息性）：缩放边必须恢复
    r2d = {dy: hit_test(hm, cx, r2.Top + dy) for dy in dys[:4]}
    print(f"RESTORED probe dy:{dys[:4]} -> {[r2d[d] for d in dys[:4]]} "
          f"(应回到 HTTOP={HTTOP} 缩放区)")

    wm.graceful_close_by_name("WindowMerger")
    time.sleep(1.5)
    wm.remove_config()
    print("MAX_TOP_DRAG_TEST_DONE")
    ok = probe_ok and drag_ok
    print(f"RESULT {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
