# -*- coding: utf-8 -*-
"""最大化拖顶条还原回归（**自动化**——固定布局 + 注入拖动）：
宿主钉主屏固定矩形 → 最大化 → 注入拖顶条（超过拖动阈值）→ 断言：
还原（非 zoomed）+ 落位 = 按光标占比锚点公式计算的期望矩形（StartMaxRestoreDrag 语义）。
原 manual/ManualDragTest.ps1 为人工操作+150ms 采样时间线；注入拖动在固定布局下可靠
（2026-11 实测），升级为自动回归，manual 原版保留作交互排查工具。
用法: py tools\\tests\\maximize_drag_test.py [--exe 路径]
警告: 强杀所有 WindowMerger/Notepad/mspaint + 删 config.json。
"""
import argparse
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import wm

PIN = (400, 150, 2200, 900)   # 钉位矩形（L,T,W,H 物理 px；RestoreBounds 来源）


def drag(from_x: int, from_y: int, to_x: int, to_y: int, steps: int = 20) -> None:
    wm.set_cursor_pos(from_x, from_y)
    time.sleep(0.15)
    wm.mouse_event(wm.MOUSEEVENTF_LEFTDOWN)
    time.sleep(0.15)
    for i in range(1, steps + 1):
        wm.set_cursor_pos(from_x + int((to_x - from_x) * i / steps),
                          from_y + int((to_y - from_y) * i / steps))
        time.sleep(0.025)
    time.sleep(0.2)
    wm.mouse_event(wm.MOUSEEVENTF_LEFTUP)
    time.sleep(1.0)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", default=wm.exe_path())
    a = ap.parse_args()

    wm.force_kill_by_name("WindowMerger", "Notepad", "mspaint")
    time.sleep(0.8)
    wm.remove_config()
    subprocess.Popen([a.exe])
    time.sleep(4)
    hm = wm.host_hwnd()
    if not hm:
        print("NO_HOST")
        return 1

    # 钉位（RestoreBounds = 该矩形）→ 最大化
    hx, hy, hw, hh = PIN
    wm.set_window_pos(hm, None, hx, hy, hw, hh, wm.SWP_NOZORDER)
    time.sleep(1.0)
    wm.show_window(hm, 3)  # SW_MAXIMIZE
    time.sleep(1.0)
    if not wm.is_zoomed(hm):
        print("FAIL_NOT_MAXIMIZED")
        return 1
    hr_max = wm.get_window_rect(hm)
    print(f"MAXIMIZED ({hr_max.Left},{hr_max.Top})-({hr_max.Right},{hr_max.Bottom})")

    # 顶条拖动：抓顶条中段（避开左标签/右按钮），拖 (+300,+250)
    scale = wm.get_dpi_for_window(hm) / 96.0
    gx, gy = hr_max.Left + 600, hr_max.Top + round(14 * scale)
    wm.set_topmost(hm, True)
    wm.set_foreground_window(hm)
    time.sleep(0.4)
    drag(gx, gy, gx + 300, gy + 250)

    # 期望落位（StartMaxRestoreDrag 公式）：光标钉在还原窗口的同一相对比例位置
    #   ratio = (抓点 DIP - 窗口左上 DIP) / 最大化窗口 DIP 尺寸
    #   expected Left = 光标终点 x - ratioX × rb.W × scale
    if wm.is_zoomed(hm):
        print("FAIL_STILL_MAXIMIZED (drag did not restore)")
        wm.set_topmost(hm, False)
        return 1
    grab_dip_x = (gx - hr_max.Left) / scale
    grab_dip_y = (gy - hr_max.Top) / scale
    max_dip_w, max_dip_h = hr_max.width / scale, hr_max.height / scale
    rb_w, rb_h = hw / scale, hh / scale  # RestoreBounds 尺寸（DIP）
    ratio_x = grab_dip_x / max_dip_w
    ratio_y = grab_dip_y / max_dip_h
    exp_left = (gx + 300) - ratio_x * rb_w * scale
    exp_top = (gy + 250) - ratio_y * rb_h * scale
    r = wm.get_window_rect(hm)
    print(f"RESTORED rect=({r.Left},{r.Top})-({r.Right},{r.Bottom}) "
          f"expect Left~{exp_left:.0f} Top~{exp_top:.0f} size {hw}x{hh}")
    wm.set_topmost(hm, False)

    ok = (abs(r.Left - exp_left) <= 40 and abs(r.Top - exp_top) <= 40
          and abs(r.width - hw) <= 2 and abs(r.height - hh) <= 2)

    wm.graceful_close_by_name("WindowMerger")
    time.sleep(1.2)
    print("MAXIMIZE_DRAG_TEST_DONE")
    print(f"RESULT {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
