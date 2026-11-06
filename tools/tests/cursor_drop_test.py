# -*- coding: utf-8 -*-
"""光标落点判定回归：CASE B 拖到宿主外（光标在外、窗口中心在格内）必须不吸附——
旧中心逻辑会误吸；CASE A 拖到左格中心必须吸附。原 CursorDropTest.ps1。
用法: py tools\\tests\\cursor_drop_test.py [--exe 路径]
警告: 强杀所有实例 + 删 config.json（恢复默认布局）；注入拖动受前台锁干扰。
"""
import argparse
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import wm

GOLDEN_NOTEPAD_X, GOLDEN_NOTEPAD_Y = 320, 310  # notepad 初始标题条抓点


def notepad_state(tag: str) -> int:
    nps = wm.main_windows_by_name("Notepad")
    if not nps:
        print(f"{tag} NO_NOTEPAD")
        return 0
    h = nps[0][1]
    r = wm.get_window_rect(h)
    print(f"{tag}: tool={wm.is_toolwindow(h)} rect=({r.Left},{r.Top})-({r.Right},{r.Bottom})")
    return h


def focus_and_check(grab_x: int, grab_y: int, hwnd: int) -> bool:
    """ALT 技巧置前台后确认抓点命中 notepad（被盖时注入不可靠 → SKIP）。"""
    for _ in range(3):
        wm.keybd_event(0x12, 0, 0)
        wm.set_foreground_window(hwnd)
        wm.keybd_event(0x12, 0, 2)
        time.sleep(0.4)
        if wm.proc_name_of(wm.window_from_point(grab_x, grab_y)).lower() == "notepad":
            return True
    return False


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

    # 1. 全新环境（无 config → 默认比例 0.5）
    wm.force_kill_by_name("WindowMerger", "Notepad", "mspaint")
    time.sleep(0.8)
    wm.remove_config()
    t1 = Path(tempfile.gettempdir(), "wmt1.txt")
    t1.write_text("cursor-drop", encoding="ascii")
    subprocess.Popen(["notepad", str(t1)])
    time.sleep(1.5)
    subprocess.Popen([a.exe])
    time.sleep(4)
    hm = wm.host_hwnd()
    if not hm:
        print("NO_HOST")
        return 1
    hr = wm.get_window_rect(hm)
    print(f"HOST ({hr.Left},{hr.Top})-({hr.Right},{hr.Bottom})")

    # notepad 定位 (300,300) 500x400（NOZORDER|NOACTIVATE：notepad 保持前台）
    nps = wm.main_windows_by_name("Notepad")
    if not nps:
        print("NO_NOTEPAD")
        return 1
    nh = nps[0][1]
    wm.set_window_pos(nh, None, 300, 300, 500, 400, wm.SWP_NOZORDER | wm.SWP_NOACTIVATE)
    time.sleep(0.5)
    notepad_state("INIT")

    # 2. CASE B：拖标题 (320,310) → (500,700)。光标出宿主、中心在左格——必须不吸附
    if not focus_and_check(GOLDEN_NOTEPAD_X, GOLDEN_NOTEPAD_Y, nh):
        print("SKIP_COVERED")
        return 1
    drag(GOLDEN_NOTEPAD_X, GOLDEN_NOTEPAD_Y, 500, 700)
    notepad_state("CASE_B_NO_ATTACH_EXPECTED")

    # 3. CASE A：notepad 已到 (480,690)，拖新抓点 (500,700) → 左格中心 (959,696)
    if not focus_and_check(500, 700, nh):
        print("SKIP_CASE_A_COVERED")
        notepad_state("FINAL_STATE")
        return 1
    drag(500, 700, 959, 696)
    notepad_state("CASE_A_ATTACH_EXPECTED")
    print(f"LEFT_HIT={wm.proc_name_of(wm.window_from_point(959, 696))}")

    # 4. 清理
    wm.graceful_close_by_name("WindowMerger")
    time.sleep(1.2)
    wm.force_kill_by_name("Notepad", "mspaint")
    print("CURSOR_DROP_TEST_DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
