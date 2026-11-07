# -*- coding: utf-8 -*-
"""双击顶条最大化/还原回归（注入双击，固定布局）：双击顶条空白区 → 最大化
（只放大格子布局）→ 再双击 → 还原。原功能无脚本覆盖，2026-11 补。
用法: uv run tools/\tests\\double_click_max_test.py [--exe 路径]
警告: 强杀所有 WindowMerger/Notepad/mspaint + 删 config.json。
"""
import argparse
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import wm

PIN = wm.test_layout()["host"]


def double_click(x, y):
    wm.set_cursor_pos(x, y)
    time.sleep(0.2)
    for _ in range(2):
        wm.mouse_event(wm.MOUSEEVENTF_LEFTDOWN)
        time.sleep(0.05)
        wm.mouse_event(wm.MOUSEEVENTF_LEFTUP)
        time.sleep(0.08)
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
    hx, hy, hw, hh = PIN
    wm.set_window_pos(hm, None, hx, hy, hw, hh, wm.SWP_NOZORDER)
    time.sleep(1.0)
    wm.set_topmost(hm, True)
    wm.set_foreground_window(hm)
    time.sleep(0.4)

    # 双击顶条空白区（x=左起 600，避开左标签与右按钮组）；坐标按当前矩形算——
    # 最大化后顶条移到屏幕顶（y 0..42），沿用钉位 y 会点进格子（实测踩过）
    gx = hx + 600
    double_click(gx, hy + 14)
    max_ok = wm.is_zoomed(hm)
    print(f"AFTER_DBLCLICK zoomed={max_ok} {'OK' if max_ok else 'MISMATCH'}")

    hr_max = wm.get_window_rect(hm)
    double_click(gx, hr_max.Top + 14)
    restore_ok = not wm.is_zoomed(hm)
    r = wm.get_window_rect(hm)
    size_ok = abs(r.width - hw) <= 2 and abs(r.height - hh) <= 2
    print(f"AFTER_DBLCLICK2 zoomed={not restore_ok} size=({r.width}x{r.height}) "
          f"{'OK' if restore_ok and size_ok else 'MISMATCH'}")

    wm.set_topmost(hm, False)
    wm.graceful_close_by_name("WindowMerger")
    time.sleep(1.2)
    print("DOUBLE_CLICK_MAX_TEST_DONE")
    ok = max_ok and restore_ok and size_ok
    print(f"RESULT {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
