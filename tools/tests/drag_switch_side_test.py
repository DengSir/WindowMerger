# -*- coding: utf-8 -*-
"""拖到另一侧换侧回归（注入拖动，固定布局）：mspaint 吸附在左格 → 抓其标题条
（透过透明格子命中子窗口）拖到右格中心松手 → 吸附态整体换侧（TryAttach 换侧分支）。
用法: uv run tools/\tests\\drag_switch_side_test.py [--exe 路径]
警告: 强杀所有 WindowMerger/Notepad/mspaint + 删 config.json。
"""
import argparse
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import wm

HOST_RECT = wm.test_layout()["host"]


def drag(from_x, from_y, to_x, to_y, steps=20):
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
    time.sleep(1.2)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", default=wm.exe_path())
    a = ap.parse_args()

    wm.force_kill_by_name("WindowMerger", "Notepad", "mspaint")
    time.sleep(0.8)
    wm.remove_config()
    # 自写靶窗（tkinter，标题 WM_DRAG_TARGET）：零 Ribbon/零 PMv2，标题几何已知
    target = subprocess.Popen([sys.executable,
                               str(Path(__file__).resolve().parents[1] / "targets" / "drag_target.py")])
    time.sleep(1.8)
    th = wm.find_window_by_title("WM_DRAG_TARGET")
    if not th:
        print("FAIL_NO_TARGET")
        target.kill()
        return 1
    subprocess.Popen([a.exe, "--left", str(target.pid)])
    time.sleep(4)
    hm = wm.host_hwnd()
    if not hm:
        print("NO_HOST")
        return 1
    hx, hy, hw, hh = HOST_RECT
    wm.set_window_pos(hm, None, hx, hy, hw, hh, wm.SWP_NOZORDER)
    time.sleep(1.5)
    wm.set_topmost(hm, True)
    time.sleep(0.4)

    pane_w = (hw - 15) // 2
    left_cx = hx + 3 + pane_w // 2
    right_cx = hx + 3 + pane_w + 9 + pane_w // 2
    mid_y = hy + 45 + (hh - 48) // 2

    for _ in range(3):  # busy 桌面：topmost 别的窗口压住探点时重新置顶宿主再探
        pre_l = wm.proc_name_of(wm.window_from_point(left_cx, mid_y)).lower()
        if pre_l == "python":
            break
        wm.set_topmost(hm, True)
        time.sleep(0.4)
    print(f"PRE LEFT_HIT={pre_l}")
    if pre_l != "python":
        print("FAIL_NOT_ATTACHED_LEFT")
        return 1

    # 抓 mspaint 标题条（透过透明左格命中子窗口），拖到右格中心 → 换侧。
    # 最多重试 2 次（CI 拖动未生效时 rect 回到原格，原因待诊断——重试 + 置前 + 诊断）
    mp_r = wm.get_window_rect(wm.main_windows_by_name("mspaint")[0][1])
    grab_x = min(mp_r.Left + 60, hx + 100)  # 标题条内、避开图标
    grab_y = wm.title_grab_point(th)[1]
    if wm.proc_name_of(wm.window_from_point(grab_x, grab_y)).lower() != "mspaint":
        print("SKIP_COVERED_GRAB")
        return 1
    swapped = False
    for attempt in range(3):
        wm.keybd_event(0x12, 0, 0)
        wm.set_foreground_window(wm.main_windows_by_name("mspaint")[0][1])
        wm.keybd_event(0x12, 0, 2)
        time.sleep(0.3)
        drag(grab_x, grab_y, right_cx, mid_y)
        post_l_try = wm.proc_name_of(wm.window_from_point(left_cx, mid_y)).lower()
        if post_l_try != "mspaint":
            swapped = True
            break
            print(f"DIAG attempt{attempt}: target rect=({mp_r.Left},{mp_r.Top})-"
              f"({mp_r.Right},{mp_r.Bottom}) still attached left")

    post_l = wm.proc_name_of(wm.window_from_point(left_cx, mid_y)).lower()
    post_r = wm.proc_name_of(wm.window_from_point(right_cx, mid_y)).lower()
    still_tool = wm.is_toolwindow(th)
    print(f"POST LEFT_HIT={post_l} RIGHT_HIT={post_r} tool={still_tool}")
    wm.set_topmost(hm, False)

    wm.graceful_close_by_name("WindowMerger")
    time.sleep(1.2)
    target.kill()
    print("DRAG_SWITCH_SIDE_TEST_DONE")
    ok = swapped and post_r == "python" and still_tool
    print(f"RESULT {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
