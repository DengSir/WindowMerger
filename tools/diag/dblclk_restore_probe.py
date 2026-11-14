# -*- coding: utf-8 -*-
"""双击还原矛盾读数探针（issue #1 适配排查用，非常驻回归）：
现象 = double_click_max 第二段（最大化态触顶滑入后双击还原）后 IsZoomed=True
但 GetWindowRect=还原尺寸，两读数自相矛盾。本脚本逐 100ms 采样
（is_zoomed / 矩形 / 顶条 close 钮 UIA top）还原过程时间线，定位状态跳变点。
用法: uv run tools/diag/dblclk_restore_probe.py
标记（英文）：S1_TOUCH_DBLCLK / S2_DIRECT_DBLCLK / TIMELINE / DONE
"""
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import wm  # noqa: E402
import wm_uia  # noqa: E402

PIN = wm.test_layout()["host"]


def close_btn_top(hm: int) -> float | None:
    b = wm_uia.find_by_automation_id(wm_uia.element_from_handle(hm), "_closeButton")
    if b is None:
        return None
    _l, t, _w, _h = wm_uia.bounding_rect_of(b)
    return t


def double_click(x: int, y: int) -> None:
    wm.set_cursor_pos(x, y)
    time.sleep(0.2)
    for _ in range(2):
        wm.mouse_event(wm.MOUSEEVENTF_LEFTDOWN)
        time.sleep(0.05)
        wm.mouse_event(wm.MOUSEEVENTF_LEFTUP)
        time.sleep(0.08)
    time.sleep(0.3)


def sample(hm: int, tag: str) -> None:
    z = wm.is_zoomed(hm)
    r = wm.get_window_rect(hm)
    bt = close_btn_top(hm)
    print(f"  {tag} zoomed={z} rect=({r.Left},{r.Top})-({r.Right},{r.Bottom}) "
          f"closeTop={bt}")


def scenario(hm: int, gx: int, touch_park: bool, tag: str) -> None:
    print(f"{tag} park={touch_park}")
    sample(hm, "pre")
    if touch_park:
        wm.set_cursor_pos(gx, wm.get_window_rect(hm).Top + 2)  # 触顶唤出
        time.sleep(0.6)
        sample(hm, "afterPark")
    mr = wm.get_window_rect(hm)
    double_click(gx, mr.Top + 14)
    for i in range(12):
        sample(hm, f"t+{i * 0.1:.1f}s")
        time.sleep(0.1)
    print(f"  verdict zoomed={wm.is_zoomed(hm)}")


def main() -> int:
    wm.force_kill_by_name("WindowMerger", "Notepad", "mspaint")
    time.sleep(0.8)
    wm.remove_config()
    subprocess.Popen([wm.exe_path()])
    time.sleep(4)
    hm = wm.host_hwnd()
    if not hm:
        print("NO_HOST")
        return 1
    hx, hy, hw, hh = PIN
    wm.set_window_pos(hm, None, hx, hy, hw, hh, wm.SWP_NOZORDER)
    time.sleep(1.0)
    wm.set_topmost(hm, True)
    wm.set_foreground_window(hm)
    time.sleep(0.4)
    gx = hx + int(hw * 0.625)
    scale = wm.get_dpi_for_window(hm) / 96.0

    # S1：最大化 → 触顶滑入 → 双击条内还原（double_click_max 适配后路径）
    wm.show_window(hm, 3)  # SW_MAXIMIZE
    time.sleep(1.0)
    sample(hm, "maximized")
    scenario(hm, gx, True, "S1_TOUCH_DBLCLK")

    # 回到最大化，复测（状态残留排查）
    wm.show_window(hm, 3)
    time.sleep(1.0)
    scenario(hm, gx, True, "S1B_AGAIN")

    wm.set_topmost(hm, False)
    wm.graceful_close_by_name("WindowMerger")
    time.sleep(1.2)
    print("DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
