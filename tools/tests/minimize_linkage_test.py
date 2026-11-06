# -*- coding: utf-8 -*-
"""最小化联动回归：宿主最小化 → 吸附子窗口随动移出屏幕外（toolwindow 无任务栏按钮、
最小化会缩成标题条，故移到 -32000）；宿主还原 → 维护定时器把子窗口拉回格子。
用法: uv run tools/\tests\\minimize_linkage_test.py [--exe 路径]
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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", default=wm.exe_path())
    a = ap.parse_args()

    wm.force_kill_by_name("WindowMerger", "Notepad", "mspaint")
    time.sleep(0.8)
    wm.remove_config()
    t1 = Path(tempfile.gettempdir(), "wmt1.txt")
    t1.write_text("min-linkage", encoding="ascii")
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
    wm.set_window_pos(hm, None, 400, 150, 2200, 900, wm.SWP_NOZORDER)
    time.sleep(1.5)

    np_h = wm.main_windows_by_name("Notepad")[0][1]
    mp_h = wm.main_windows_by_name("mspaint")[0][1]
    np_r0 = wm.get_window_rect(np_h)
    mp_r0 = wm.get_window_rect(mp_h)
    print(f"ATTACHED notepad=({np_r0.Left},{np_r0.Top}) mspaint=({mp_r0.Left},{mp_r0.Top})")

    # 宿主最小化 → 子窗口移出屏外
    wm.show_window(hm, wm.SW_MINIMIZE)
    time.sleep(1.0)
    np_r1 = wm.get_window_rect(np_h)
    mp_r1 = wm.get_window_rect(mp_h)
    off_ok = np_r1.Left <= -30000 and mp_r1.Left <= -30000
    print(f"MINIMIZED notepad.Left={np_r1.Left} mspaint.Left={mp_r1.Left} "
          f"(expect ≤ -30000) {'OK' if off_ok else 'MISMATCH'}")

    # 宿主还原 → 子窗口拉回格子
    wm.show_window(hm, wm.SW_RESTORE)
    time.sleep(2.0)  # 维护定时器收敛
    np_r2 = wm.get_window_rect(np_h)
    mp_r2 = wm.get_window_rect(mp_h)
    back_ok = (abs(np_r2.Left - np_r0.Left) <= 10 and abs(np_r2.Top - np_r0.Top) <= 10
               and abs(mp_r2.Left - mp_r0.Left) <= 10 and abs(mp_r2.Top - mp_r0.Top) <= 10)
    print(f"RESTORED notepad=({np_r2.Left},{np_r2.Top}) mspaint=({mp_r2.Left},{mp_r2.Top}) "
          f"back_in_pane={'OK' if back_ok else 'MISMATCH'}")

    wm.graceful_close_by_name("WindowMerger")
    time.sleep(1.2)
    wm.force_kill_by_name("Notepad", "mspaint")
    print("MINIMIZE_LINKAGE_TEST_DONE")
    ok = off_ok and back_ok
    print(f"RESULT {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
