# -*- coding: utf-8 -*-
"""排除自身回归：实例 B 先起，实例 C 用 --left <B 的 PID> 抓 B——B 的宿主必须不被
吸附（无 TOOLWINDOW、矩形不动）。原 ExcludeSelfTest.ps1。
用法: py tools\\tests\\exclude_self_test.py [--exe 路径]
"""
import argparse
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import wm


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", default=wm.exe_path())
    a = ap.parse_args()

    # 清理（优雅关；实例可能持有用户窗口，不强杀）
    wm.graceful_close_by_name("WindowMerger")
    time.sleep(1.3)

    # 受害者：普通实例 B
    subprocess.Popen([a.exe])
    time.sleep(3)
    b_pids = [p for p in wm.pids_by_name("WindowMerger") if wm.main_windows_of_pid(p)]
    if not b_pids:
        print("FAIL_NO_B")
        return 1
    pid_b = b_pids[0]
    hb = wm.main_windows_of_pid(pid_b)[0]
    rb = wm.get_window_rect(hb)

    # 抓取者：实例 C 以 B 的 PID 为目标
    subprocess.Popen([a.exe, "--left", str(pid_b)])
    time.sleep(4)

    c_pids = [p for p in wm.pids_by_name("WindowMerger")
              if p != pid_b and wm.main_windows_of_pid(p)]
    if not c_pids:
        print("FAIL_NO_C")
        return 1

    tool = wm.is_toolwindow(hb)
    rb2 = wm.get_window_rect(hb)
    moved = rb2.Left != rb.Left or rb2.Top != rb.Top

    if not tool and not moved:
        print(f"PASS other-self not grabbed: B pid={pid_b} toolwindow={tool} moved={moved}")
    else:
        print(f"FAIL B was grabbed: toolwindow={tool} moved={moved}")

    # 清理（优雅关，两个实例干净退出）
    wm.graceful_close_by_name("WindowMerger")
    time.sleep(1.2)
    print("EXCLUDE_SELF_TEST_DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
