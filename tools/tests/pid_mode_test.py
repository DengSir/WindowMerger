# -*- coding: utf-8 -*-
"""CLI PID 模式端到端：自己拉起的 notepad（拿 PID）+ mspaint，混合 PID/名字吸附；
再给一个无窗口的 PID（本测试进程自身）走报因路径。原 PidModeTest.ps1。
用法: uv run tools/\tests\\pid_mode_test.py [--exe 路径]
警告: 会强杀所有 WindowMerger/Notepad/mspaint。
"""
import argparse
import os
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
    t1 = Path(tempfile.gettempdir(), "wmt1.txt")
    t1.write_text("pid-mode", encoding="ascii")

    # 自己拉起 notepad → PID 在手
    np = subprocess.Popen(["notepad", str(t1)])
    time.sleep(1.2)
    print(f"NOTEPAD_PID={np.pid}")
    subprocess.Popen(["mspaint"])
    time.sleep(1.5)

    # 混合：左按 PID、右按名字
    subprocess.Popen([a.exe, "--left", str(np.pid), "--right", "mspaint"])
    time.sleep(4)

    hm = wm.host_hwnd()
    if not hm:
        print("NO_HOST")
        return 1
    wm.set_window_pos(hm, None, *wm.test_layout()["host"], wm.SWP_NOZORDER)
    time.sleep(1.5)
    wm.set_topmost(hm, True)
    time.sleep(0.4)
    hr = wm.get_window_rect(hm)
    avail = hr.Right - hr.Left - 12
    mid_y = (hr.Top + hr.Bottom) // 2
    h1 = wm.window_from_point(int(hr.Left + 2 + avail * 0.35), mid_y)
    h2 = wm.window_from_point(int(hr.Left + 2 + avail * 0.75), mid_y)
    print(f"LEFT_HIT={wm.proc_name_of(h1)}")
    print(f"RIGHT_HIT={wm.proc_name_of(h2)}")
    hits_ok = (wm.proc_name_of(h1).lower() == "notepad"
               and wm.proc_name_of(h2).lower() == "mspaint")

    # 反例：无窗口的 PID（本 Python 进程自身）→ 报因路径，宿主不崩
    subprocess.Popen([a.exe, "--left", str(os.getpid())])
    time.sleep(3)
    print("NO_WINDOW_PID_TEST_DONE (second instance shows notice; check no crash)")
    wm.graceful_close_by_name("WindowMerger")
    time.sleep(1.2)
    wm.force_kill_by_name("Notepad", "mspaint")
    print("PID_MODE_TEST_DONE")
    print(f"RESULT {'PASS' if hits_ok else 'FAIL'}")
    return 0 if hits_ok else 1


if __name__ == "__main__":
    sys.exit(main())
