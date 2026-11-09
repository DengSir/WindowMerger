# -*- coding: utf-8 -*-
"""PID 匹配三级回退 + 多候选取大 回归（HostWindow.Attach.cs FindWindowByArg）。
进程链现实（实测）：venv python.exe 是启动器，窗口属于其子进程（真实解释器）——
本测试进程天然就是"无窗口 stub"（AGENTS 记载的打包应用 stub 场景同构）：
  P1 回退 1·后代进程树：`--left <本测试进程PID>`（自己无顶层窗口）→
     后代（multi_win 靶的真实解释器）的窗口被吸附
  P2 回退 2·同名进程：无窗口 python（CREATE_NO_WINDOW sleep）的 PID → 精确匹配无窗口、
     无后代 → 按其进程名 "python" 匹配现存窗口（GetProcessById 活进程才走得到——
     PID 已死会 ArgumentException 落空，实测）
  P3 同候选多窗口取面积最大：`--left <真实解释器PID>`（精确命中，单进程双窗）→
     PickBestBy 吸附 800x500 大窗，500x300 小窗不动
用法: uv run tools\\tests\\pid_fallback_test.py [--exe 路径]
警告: 强杀所有 WindowMerger/Notepad + 清理靶/哨兵进程。
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

CREATE_NO_WINDOW = 0x08000000


def start_host(exe: str, *args: str) -> int:
    subprocess.Popen([exe, *args], env=wm.host_env())
    time.sleep(4)
    return wm.host_hwnd()


def kill_all() -> None:
    wm.graceful_close_by_name("WindowMerger")
    time.sleep(1.0)
    wm.force_kill_by_name("WindowMerger", "Notepad")
    time.sleep(0.5)


def windowed_descendant(launcher_pid: int) -> int:
    """启动器 pid 的后代里持有窗口的真实解释器 pid（venv 重定向产物）。"""
    for p in wm.pids_by_name("python"):
        if p != launcher_pid and wm.launched_by(p, launcher_pid, depth=2) \
                and wm.all_windows_of_pid(p):
            return p
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", default=wm.exe_path())
    a = ap.parse_args()
    failures: list[str] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        print(f"{name} {'OK' if ok else 'MISMATCH'} {detail}")
        if not ok:
            failures.append(name)

    kill_all()

    # ---------- 双窗靶（一个小窗 + 一个大窗，同一真实解释器进程） ----------
    target = subprocess.Popen([sys.executable,
                               str(Path(__file__).resolve().parents[1] / "targets" / "multi_win.py")])
    real_pid = 0

    def have_windows() -> bool:
        nonlocal real_pid
        real_pid = windowed_descendant(target.pid)
        return bool(real_pid)

    if not wm.wait_until(have_windows, 8000, 300) or not real_pid:
        print("FAIL_NO_TARGET_WINDOWS")
        target.kill()
        return 1
    wins = wm.top_windows_of_pids([real_pid])
    small = next((h for h in wins if wm.get_text(h) == "WM_MULTI_SMALL"), 0)
    big_h = next((h for h in wins if wm.get_text(h) == "WM_MULTI_BIG"), 0)
    if not (small and big_h):
        print(f"FAIL_TITLES wins={[wm.get_text(h) for h in wins]}")
        target.kill()
        return 1
    check("P0_TWO_WINDOWS", True)

    try:
        # ---------- P1 后代进程树（本测试进程 = 无窗口 stub） ----------
        hm = start_host(a.exe, "--left", str(os.getpid()))
        if not hm:
            check("P1_ATTACH", False, "no host")
        else:
            got = wm.wait_until(lambda: wm.is_toolwindow(big_h), 8000, 300)
            check("P1_ATTACH", got, f"big_tool={wm.is_toolwindow(big_h)} "
                  f"(stub_pid={os.getpid()} real={real_pid})")
            kill_all()

        # ---------- P2 同名进程兜底（无窗口活进程 PID） ----------
        sentinel = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"],
                                    creationflags=CREATE_NO_WINDOW)
        time.sleep(1.0)
        hm = start_host(a.exe, "--left", str(sentinel.pid))
        if not hm:
            check("P2_ATTACH", False, "no host")
        else:
            got = wm.wait_until(lambda: wm.is_toolwindow(big_h), 8000, 300)
            check("P2_ATTACH", got, f"sentinel={sentinel.pid} "
                  f"big_tool={wm.is_toolwindow(big_h)} small_tool={wm.is_toolwindow(small)}")
            kill_all()
            sentinel.kill()

        # ---------- P3 精确 PID + 同候选多窗口取面积最大 ----------
        r_small = wm.get_window_rect(small)
        r_big = wm.get_window_rect(big_h)
        hm = start_host(a.exe, "--left", str(real_pid))
        if not hm:
            check("P3_ATTACH", False, "no host")
        else:
            got = wm.wait_until(lambda: wm.is_toolwindow(big_h), 8000, 300)
            time.sleep(0.5)
            check("P3_ATTACH", got and not wm.is_toolwindow(small),
                  f"big_tool={wm.is_toolwindow(big_h)} small_tool={wm.is_toolwindow(small)} "
                  f"(area big={r_big.width * r_big.height} small={r_small.width * r_small.height})")
            kill_all()
    finally:
        target.kill()
        time.sleep(0.3)

    print(f"FAILURES {'; '.join(failures) if failures else 'NONE'}")
    print(f"RESULT {'FAIL' if failures else 'PASS'}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
