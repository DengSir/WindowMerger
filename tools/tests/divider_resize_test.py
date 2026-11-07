# -*- coding: utf-8 -*-
"""分隔条拖动调比例 + 双击复位回归（注入拖动，固定布局）：
CLI 吸附两侧 → 注入拖分隔条右移 200px → 断言子窗口矩形跟随（右格变窄）→
双击分隔条 → 断言比例复位 0.5（子窗口矩形回到原位）→ 优雅关后 config Ratio==0.5。
用法: uv run tools/\tests\\divider_resize_test.py [--exe 路径]
警告: 强杀所有 WindowMerger/Notepad/mspaint + 删 config.json。
"""
import argparse
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import wm


def drag(from_x, from_y, to_x, to_y, steps=15):
    wm.set_cursor_pos(from_x, from_y)
    time.sleep(0.15)
    wm.mouse_event(wm.MOUSEEVENTF_LEFTDOWN)
    time.sleep(0.15)
    for i in range(1, steps + 1):
        wm.set_cursor_pos(from_x + int((to_x - from_x) * i / steps),
                          from_y + int((to_y - from_y) * i / steps))
        time.sleep(0.03)
    time.sleep(0.15)
    wm.mouse_event(wm.MOUSEEVENTF_LEFTUP)
    time.sleep(0.8)


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
    t1 = Path(tempfile.gettempdir(), "wmt1.txt")
    t1.write_text("divider-test", encoding="ascii")
    subprocess.Popen(["notepad", str(t1)])
    time.sleep(1.2)
    subprocess.Popen(["mspaint"])
    time.sleep(1.5)
    subprocess.Popen([a.exe, "--left", "notepad", "--right", "mspaint"])
    time.sleep(4)
    hm = wm.host_hwnd()
    if not hm:
        print("NO_HOST")
        return 1
    wm.set_window_pos(hm, None, *wm.test_layout()["host"], wm.SWP_NOZORDER)
    time.sleep(1.5)
    wm.set_topmost(hm, True)
    time.sleep(0.4)

    np_r = wm.get_window_rect(wm.main_windows_by_name("Notepad")[0][1])
    mp_r0 = wm.get_window_rect(wm.main_windows_by_name("mspaint")[0][1])
    # 分隔条中心 ≈ 两子窗口相对边缘的中点（各含 ~9px 隐形边外扩，中点即分隔条中线）
    div_x = (np_r.Right + mp_r0.Left) // 2
    mid_y = (mp_r0.Top + mp_r0.Bottom) // 2
    print(f"HOST pinned; divider center ~({div_x},{mid_y})")

    # 拖分隔条右移 200px → 左格变宽/右格变窄
    drag(div_x, mid_y, div_x + 200, mid_y)
    mp_r1 = wm.get_window_rect(wm.main_windows_by_name("mspaint")[0][1])
    moved = mp_r1.Left - mp_r0.Left
    resize_ok = 180 <= moved <= 220
    print(f"AFTER_DRAG mspaint Left {mp_r0.Left} -> {mp_r1.Left} (delta={moved}, expect ~+200) "
          f"{'OK' if resize_ok else 'MISMATCH'}")

    # 双击复位 0.5（先取新分隔条位置）
    div_x2 = (wm.get_window_rect(wm.main_windows_by_name("Notepad")[0][1]).Right + mp_r1.Left) // 2
    double_click(div_x2, mid_y)
    mp_r2 = wm.get_window_rect(wm.main_windows_by_name("mspaint")[0][1])
    back = abs(mp_r2.Left - mp_r0.Left) <= 15 and abs(mp_r2.Right - mp_r0.Right) <= 15
    print(f"AFTER_DBLCLICK mspaint rect=({mp_r2.Left},{mp_r2.Top})-({mp_r2.Right},{mp_r2.Bottom}) "
          f"back_to_50pct={'OK' if back else 'MISMATCH'}")

    # 优雅关 → config Ratio 应为 0.5
    wm.graceful_close_by_name("WindowMerger")
    time.sleep(1.5)
    try:
        ratio = float(wm.load_config().get("Ratio"))
        cfg_ok = abs(ratio - 0.5) < 0.02
    except Exception:
        cfg_ok = False
    print(f"CONFIG_RATIO={wm.load_config().get('Ratio')} {'OK' if cfg_ok else 'MISMATCH'}")
    wm.force_kill_by_name("Notepad", "mspaint")
    wm.set_topmost(hm, False)
    print("DIVIDER_RESIZE_TEST_DONE")
    ok = resize_ok and back and cfg_ok
    print(f"RESULT {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
