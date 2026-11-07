# -*- coding: utf-8 -*-
"""交换左右回归：CLI 吸附 notepad(左)+mspaint(右) → UIA Invoke 交换按钮 →
断言两侧命中互换（LEFT_HIT=mspaint、RIGHT_HIT=notepad）且子窗口矩形跟着搬。
固定布局：宿主钉主屏（wm.test_layout() 按工作区自适应），钉位后命中坐标静态推导。
用法: uv run tools/\tests\\swap_sides_test.py [--exe 路径]
警告: 强杀所有 WindowMerger/Notepad/mspaint + 删 config.json。
（notepad 仅作 CLI 吸附/命中探针，不参与拖动——拖动类测试一律 mspaint）
"""
import argparse
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import wm
import uiautomation as auto

HOST_RECT = wm.test_layout()["host"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", default=wm.exe_path())
    a = ap.parse_args()
    auto.SetGlobalSearchTimeout(5)

    wm.force_kill_by_name("WindowMerger", "Notepad", "mspaint")
    time.sleep(0.8)
    wm.remove_config()
    t1 = Path(tempfile.gettempdir(), "wmt1.txt")
    t1.write_text("swap-test", encoding="ascii")
    subprocess.Popen(["notepad", str(t1)])
    time.sleep(1.2)
    subprocess.Popen(["mspaint"])
    time.sleep(1.5)
    # 目标先存在，再带参启动宿主（吸附发生在 Loaded）
    subprocess.Popen([a.exe, "--left", "notepad", "--right", "mspaint"])
    time.sleep(4)
    hm = wm.host_hwnd()
    if not hm:
        print("NO_HOST")
        return 1

    hx, hy, hw, hh = HOST_RECT
    wm.set_window_pos(hm, None, hx, hy, hw, hh, wm.SWP_NOZORDER)
    time.sleep(1.5)  # 维护定时器把子窗口搬进新格子

    mid_y = hy + 45 + (hh - 48) // 2
    pane_w = (hw - 15) // 2
    lx = hx + 3 + pane_w // 2
    rx = hx + 3 + pane_w + 9 + pane_w // 2

    wm.set_topmost(hm, True)  # 命中探针不被前台窗口干扰
    time.sleep(0.4)
    pre_l = wm.proc_name_of(wm.window_from_point(lx, mid_y)).lower()
    pre_r = wm.proc_name_of(wm.window_from_point(rx, mid_y)).lower()
    print(f"PRE LEFT_HIT={pre_l} RIGHT_HIT={pre_r}")
    pre_ok = pre_l == "notepad" and pre_r == "mspaint"

    # UIA Invoke 交换按钮
    main_el = auto.ControlFromHandle(hm)
    btn = main_el.ButtonControl(AutomationId="_swapButton")
    if not btn.Exists(3, 0.5):
        print("NO_SWAP_BUTTON")
        return 1
    btn.GetInvokePattern().Invoke()
    time.sleep(1.5)  # 换侧 + 布局收敛

    post_l = wm.proc_name_of(wm.window_from_point(lx, mid_y)).lower()
    post_r = wm.proc_name_of(wm.window_from_point(rx, mid_y)).lower()
    print(f"POST LEFT_HIT={post_l} RIGHT_HIT={post_r}")
    wm.set_topmost(hm, False)

    wm.graceful_close_by_name("WindowMerger")
    time.sleep(1.2)
    wm.force_kill_by_name("Notepad", "mspaint")
    print("SWAP_SIDES_TEST_DONE")
    ok = pre_ok and post_l == "mspaint" and post_r == "notepad"
    print(f"RESULT {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
